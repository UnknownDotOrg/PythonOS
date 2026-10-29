"""Built-in package manager for PythonOS (.pyospkg packages)."""
import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

PACKAGE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
PACKAGE_EXT = ".pyospkg"


def _base_dir():
    return Path(__file__).resolve().parent


def _config_path():
    return _base_dir() / "pkglib" / "config.json"


def _download_dir():
    # Keep the requested directory name exactly as specified.
    return _base_dir() / "pkglib" / "downloaded-packaged"


def _modules_dir():
    return _base_dir() / "modules"


def _load_config():
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        _save_config({"repository_url": ""})
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("PkgLib config must be a JSON object.")
    data.setdefault("repository_url", "")
    return data


def _save_config(data):
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")


def _valid_id(package_id):
    return isinstance(package_id, str) and bool(PACKAGE_ID_RE.fullmatch(package_id))


def _read_index(source):
    source = source.strip()
    if not source:
        raise ValueError("No repository configured. Use: pkglib repo set <URL-or-file-path>")
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme in ("http", "https"):
        request = urllib.request.Request(source, headers={"User-Agent": "PyOS-PkgLib/0.1"})
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(2_000_000)
        index = json.loads(raw.decode("utf-8"))
        return index, source
    path = Path(source).expanduser()
    if not path.is_absolute():
        path = (_base_dir() / path).resolve()
    index = json.loads(path.read_text(encoding="utf-8"))
    return index, path.as_uri()


def _get_repository():
    config = _load_config()
    index, source = _read_index(str(config.get("repository_url", "")))
    if not isinstance(index, dict) or not isinstance(index.get("packages"), list):
        raise ValueError("Invalid repository index: expected an object with a 'packages' list.")
    return index["packages"], source


def _find_package(packages, package_id):
    for package in packages:
        if isinstance(package, dict) and package.get("id") == package_id:
            return package
    return None


def _resolve_package_url(package_url, index_source):
    parsed = urllib.parse.urlparse(package_url)
    if parsed.scheme in ("http", "https", "file"):
        return package_url
    source = urllib.parse.urlparse(index_source)
    if source.scheme in ("http", "https"):
        return urllib.parse.urljoin(index_source, package_url)
    index_path = Path(urllib.request.url2pathname(source.path))
    return (index_path.parent / package_url).resolve().as_uri()


def _read_url(url, max_bytes=50_000_000):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "file":
        path = Path(urllib.request.url2pathname(parsed.path))
        if path.stat().st_size > max_bytes:
            raise ValueError("Package file is too large.")
        return path.read_bytes()
    request = urllib.request.Request(url, headers={"User-Agent": "PyOS-PkgLib/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("Package file is too large.")
    return data


def _safe_archive_members(archive):
    members = archive.infolist()
    if len(members) > 500:
        raise ValueError("Package contains too many files.")
    total_size = 0
    clean = []
    for member in members:
        name = member.filename
        path = PurePosixPath(name)
        if not name or path.is_absolute() or ".." in path.parts or "\\" in name:
            raise ValueError(f"Unsafe path in package: {name!r}")
        if member.is_dir():
            continue
        total_size += member.file_size
        if total_size > 50_000_000:
            raise ValueError("Unpacked package is too large.")
        clean.append(member)
    return clean


def _inspect_package(package_path):
    with zipfile.ZipFile(package_path, "r") as archive:
        members = _safe_archive_members(archive)
        names = {member.filename for member in members}
        if "module.json" not in names:
            raise ValueError("Package is missing module.json at its root.")
        metadata = json.loads(archive.read("module.json").decode("utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("module.json must contain a JSON object.")
        for field in ("name", "description", "id", "version", "entry"):
            if not isinstance(metadata.get(field), str) or not metadata[field].strip():
                raise ValueError(f"module.json has a missing or invalid '{field}' field.")
        if not _valid_id(metadata["id"]):
            raise ValueError("Package has an invalid module ID.")
        entry = metadata["entry"]
        if entry in (".", "..") or PurePosixPath(entry).name != entry or entry not in names:
            raise ValueError("Package entry must be a file at the package root.")
        return metadata, members


def _download(package_id):
    if not _valid_id(package_id):
        raise ValueError("Invalid package ID. Use letters, numbers, underscores, and hyphens.")
    packages, index_source = _get_repository()
    item = _find_package(packages, package_id)
    if item is None:
        raise ValueError(f"Package '{package_id}' was not found in the repository.")
    package_url = item.get("url")
    if not isinstance(package_url, str) or not package_url:
        raise ValueError("Repository entry has no package URL.")
    version = str(item.get("version", "1.0.0"))
    filename = f"{package_id}-{version}{PACKAGE_EXT}"
    target_dir = _download_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    url = _resolve_package_url(package_url, index_source)
    data = _read_url(url)
    expected_hash = item.get("sha256")
    if expected_hash:
        actual_hash = hashlib.sha256(data).hexdigest()
        if not isinstance(expected_hash, str) or actual_hash.lower() != expected_hash.lower():
            raise ValueError("SHA-256 verification failed; package was not saved.")
    with tempfile.NamedTemporaryFile(dir=target_dir, prefix=".download-", delete=False) as tmp:
        temp_path = Path(tmp.name)
        tmp.write(data)
    try:
        # Validate the downloaded archive before giving it the .pyospkg name.
        metadata, _ = _inspect_package(temp_path)
        if metadata["id"] != package_id:
            raise ValueError("Downloaded package ID does not match the repository entry.")
        os.replace(temp_path, target)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    print(f"Downloaded: {target.relative_to(_base_dir())}")
    print("Package saved as a .pyospkg file. It has not been installed yet.")


def _install(argument):
    download_dir = _download_dir()
    if argument.endswith(PACKAGE_EXT):
        package_path = Path(argument).expanduser()
        if not package_path.is_absolute():
            package_path = (_base_dir() / package_path).resolve()
    else:
        if not _valid_id(argument):
            raise ValueError("Usage: pkglib install <package-id-or-.pyospkg-path>")
        if not download_dir.is_dir():
            raise ValueError(f"No downloaded packages found. Run 'pkglib download {argument}' first.")
        matches = sorted(download_dir.glob(f"{argument}-*{PACKAGE_EXT}"))
        if not matches:
            raise ValueError(f"No downloaded package for '{argument}'. Run 'pkglib download {argument}' first.")
        package_path = matches[-1]
    if not package_path.is_file() or package_path.suffix != PACKAGE_EXT:
        raise ValueError("Package file does not exist or does not end in .pyospkg.")

    metadata, members = _inspect_package(package_path)
    module_id = metadata["id"]
    destination_root = _modules_dir().resolve()
    destination = (destination_root / module_id).resolve()
    if destination.parent != destination_root:
        raise ValueError("Invalid module installation path.")
    if destination.exists():
        raise ValueError(f"Module '{module_id}' already exists. Remove it manually before replacing it.")

    destination_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{module_id}-install-", dir=destination_root))
    try:
        with zipfile.ZipFile(package_path, "r") as archive:
            safe_members = _safe_archive_members(archive)
            for member in safe_members:
                out_path = (temp_dir / PurePosixPath(member.filename)).resolve()
                if out_path != temp_dir and temp_dir not in out_path.parents:
                    raise ValueError("Package contains a path outside its installation directory.")
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as src, out_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        # Ensure manifest still matches the validated package.
        installed_manifest = json.loads((temp_dir / "module.json").read_text(encoding="utf-8"))
        if installed_manifest.get("id") != module_id or installed_manifest.get("entry") != metadata["entry"]:
            raise ValueError("Package metadata changed during installation.")
        os.replace(temp_dir, destination)
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
    print(f"Installed {metadata['name']} ({module_id} v{metadata['version']}).")
    print(f"Location: {destination}")
    print(f"Use 'import {module_id}' to load it in PythonOS.")
    print("Security note: installing a package does not make its Python code trustworthy.")


def _list_installed():
    root = _modules_dir()
    found = 0
    if root.is_dir():
        for folder in sorted(root.iterdir()):
            manifest = folder / "module.json"
            if folder.is_dir() and manifest.is_file():
                try:
                    data = json.loads(manifest.read_text(encoding="utf-8"))
                    print(f"{data.get('id', folder.name)}  v{data.get('version', '?')}  -  {data.get('name', folder.name)}")
                    found += 1
                except (OSError, json.JSONDecodeError):
                    print(f"{folder.name}  -  invalid module manifest")
    if not found:
        print("No installed modules found.")


def _search(term):
    packages, _ = _get_repository()
    term = term.casefold()
    found = 0
    for item in packages:
        if not isinstance(item, dict):
            continue
        haystack = " ".join(str(item.get(key, "")) for key in ("id", "name", "description", "author")).casefold()
        if term in haystack:
            print(f"{item.get('id', '?')}  v{item.get('version', '?')}  -  {item.get('name', '?')}")
            if item.get("description"):
                print(f"  {item['description']}")
            found += 1
    if not found:
        print("No matching packages found.")


def _info(package_id):
    packages, _ = _get_repository()
    item = _find_package(packages, package_id)
    if item is None:
        raise ValueError(f"Package '{package_id}' was not found in the repository.")
    for key in ("name", "id", "version", "author", "description", "url", "sha256"):
        if item.get(key):
            print(f"{key.capitalize()}: {item[key]}")


def handle_command(command):
    """Handle a PyTerminal command. Return True if it was a PkgLib command."""
    parts = command.strip().split()
    if not parts or parts[0] != "pkglib":
        return False
    if len(parts) == 1 or parts[1] in ("help", "-help", "--help"):
        print("PyOS PkgLib v0.1 - built-in package manager")
        print("pkglib repo set <URL-or-file-path>  Configure the JSON repository")
        print("pkglib search <term>               Search available packages")
        print("pkglib info <package-id>            Show package details")
        print("pkglib download <package-id>        Download a .pyospkg file")
        print("pkglib install <id-or-file>         Install a downloaded package")
        print("pkglib list                         List installed modules")
        print("pkglib downloaded                  List downloaded .pyospkg files")
        print("pkglib remove <module-id>           Remove an installed module")
        return True
    action = parts[1].lower()
    try:
        if action == "repo" and len(parts) >= 4 and parts[2].lower() == "set":
            source = command.strip().split(None, 3)[3].strip()
            config = _load_config()
            config["repository_url"] = source
            _save_config(config)
            print(f"Repository configured: {source}")
        elif action == "search" and len(parts) >= 3:
            _search(" ".join(parts[2:]))
        elif action == "info" and len(parts) == 3:
            _info(parts[2])
        elif action == "download" and len(parts) == 3:
            _download(parts[2])
        elif action == "install" and len(parts) == 3:
            _install(parts[2])
        elif action == "list" and len(parts) == 2:
            _list_installed()
        elif action == "downloaded" and len(parts) == 2:
            directory = _download_dir()
            files = sorted(directory.glob(f"*{PACKAGE_EXT}")) if directory.is_dir() else []
            if not files:
                print("No downloaded .pyospkg files found.")
            else:
                for path in files:
                    print(path.name)
        elif action == "remove" and len(parts) == 3:
            module_id = parts[2]
            if not _valid_id(module_id):
                raise ValueError("Invalid module ID.")
            target_root = _modules_dir().resolve()
            target = (target_root / module_id).resolve()
            if target.parent != target_root:
                raise ValueError("Invalid module path.")
            if not target.is_dir():
                raise ValueError(f"Installed module '{module_id}' was not found.")
            confirmation = input(f"Remove module '{module_id}'? Type yes to confirm: ")
            if confirmation.lower() == "yes":
                shutil.rmtree(target)
                print(f"Removed module '{module_id}'.")
                print("If it was already imported this session, restart PythonOS to unload it.")
            else:
                print("Cancelled.")
        else:
            print("Unknown or incomplete PkgLib command. Type 'pkglib help'.")
    except (OSError, ValueError, KeyError, json.JSONDecodeError, zipfile.BadZipFile, urllib.error.URLError, TimeoutError) as exc:
        print(f"PkgLib error: {exc}")
    except Exception as exc:
        print(f"PkgLib failed unexpectedly: {type(exc).__name__}: {exc}")
    return True
