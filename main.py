
import time
import json
import os
import re
import sys
import io
import importlib.util
import tempfile
import shutil
import zipfile
import urllib.request
import urllib.error
from contextlib import redirect_stdout
from random import randint

import pkglib

VERSION = "1.4.0"
ACCOUNTS_FILE = "accounts.json"


# Update metadata. Bump VERSION for each public release.
VERSION = "1.3.0"
GITHUB_REPO = "UnknownDotOrg/PythonOS"
GITHUB_RAW_MAIN = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/main.py"
GITHUB_SOURCE_ZIP = f"https://github.com/{GITHUB_REPO}/archive/refs/heads/main.zip"


def _version_tuple(version):
    """Turn a dotted version into a tuple of integers for comparison."""
    try:
        return tuple(int(part) for part in version.strip().split("."))
    except (AttributeError, TypeError, ValueError):
        return ()


def _ask_yes_no(prompt, default=False):
    suffix = " [Y/n]: " if default else " [y/N]: "
    answer = input(prompt + suffix).strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def update_pythonos():
    """Check GitHub for a newer version and safely overlay its project files."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"Checking GitHub for PythonOS updates (current version: {VERSION})...")

    try:
        request = urllib.request.Request(
            GITHUB_RAW_MAIN,
            headers={"User-Agent": "PythonOS-Updater"}
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            remote_main = response.read(2_000_000).decode("utf-8")

        match = re.search(
            r'^\s*VERSION\s*=\s*["\']([0-9]+(?:\.[0-9]+)*)["\']',
            remote_main,
            re.MULTILINE
        )
        if not match:
            print("Could not find VERSION in the GitHub main.py.")
            print("The repository must contain the updater-enabled version before updates can be checked.")
            return

        latest_version = match.group(1)
        current_key = _version_tuple(VERSION)
        latest_key = _version_tuple(latest_version)

        if not current_key or not latest_key:
            print("Could not compare version numbers.")
            return
        if latest_key <= current_key:
            if latest_key == current_key:
                print(f"PythonOS {VERSION} is already up to date.")
            else:
                print(f"GitHub reports {latest_version}, which is not newer than {VERSION}.")
            return

        print(f"A newer version is available: PythonOS {latest_version}.")
        if not _ask_yes_no("Download and install this update?"):
            print("Update cancelled.")
            return

        keep_accounts = _ask_yes_no("Preserve your accounts.json file?", default=True)
        keep_modules = _ask_yes_no("Preserve installed modules/packages in modules/?", default=True)

        # These PkgLib settings and downloaded .pyospkg files are always preserved.
        preserved = {"pkglib/config.json", "pkglib/downloaded-packaged"}
        if keep_accounts:
            preserved.add("accounts.json")
        if keep_modules:
            preserved.add("modules")

        with tempfile.TemporaryDirectory(prefix="pythonos-update-") as temp_dir:
            temp_root = os.path.abspath(temp_dir)
            archive_path = os.path.join(temp_root, "source.zip")
            extract_dir = os.path.join(temp_root, "source")
            os.makedirs(extract_dir)

            request = urllib.request.Request(
                GITHUB_SOURCE_ZIP,
                headers={"User-Agent": "PythonOS-Updater"}
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                archive_bytes = response.read(100_000_000 + 1)
            if len(archive_bytes) > 100_000_000:
                print("Update archive is too large; installation cancelled.")
                return
            with open(archive_path, "wb") as archive_file:
                archive_file.write(archive_bytes)

            with zipfile.ZipFile(archive_path, "r") as archive:
                bad_member = archive.testzip()
                if bad_member:
                    print(f"Archive verification failed at {bad_member}; installation cancelled.")
                    return

                # Reject absolute paths and parent-directory traversal before extraction.
                for member in archive.infolist():
                    name = member.filename.replace("\\", "/")
                    parts = name.split("/")
                    if name.startswith("/") or any(part == ".." for part in parts):
                        print("The update archive contains an unsafe path; installation cancelled.")
                        return

                archive.extractall(extract_dir)

            # GitHub's branch ZIP has a generated top-level directory.
            candidates = []
            for root, dirs, files in os.walk(extract_dir):
                if "main.py" in files:
                    candidates.append(root)
            if len(candidates) != 1:
                print("Could not identify one PythonOS source folder in the archive.")
                return
            source_root = candidates[0]

            staged_main = os.path.join(source_root, "main.py")
            staged_text = open(staged_main, "r", encoding="utf-8").read()
            staged_match = re.search(
                r'^\s*VERSION\s*=\s*["\']([0-9]+(?:\.[0-9]+)*)["\']',
                staged_text,
                re.MULTILINE
            )
            if not staged_match or staged_match.group(1) != latest_version:
                print("The repository changed while downloading; please try again.")
                return

            # Copy updated files into a staging folder first. Existing unrelated files
            # are left untouched; preserved user data is not copied over.
            stage_dir = os.path.join(temp_root, "staged")
            os.makedirs(stage_dir)
            for root, dirs, files in os.walk(source_root):
                dirs[:] = [d for d in dirs if d != "__pycache__" and d != ".git"]
                rel_root = os.path.relpath(root, source_root)
                for filename in files:
                    if filename.endswith(".pyc"):
                        continue
                    source_file = os.path.join(root, filename)
                    rel_path = os.path.normpath(os.path.join(rel_root, filename))
                    if rel_path == ".":
                        rel_path = filename
                    rel_posix = rel_path.replace(os.sep, "/")
                    if any(
                        rel_posix == item or rel_posix.startswith(item.rstrip("/") + "/")
                        for item in preserved
                    ):
                        continue
                    destination = os.path.join(stage_dir, rel_path)
                    os.makedirs(os.path.dirname(destination), exist_ok=True)
                    shutil.copy2(source_file, destination)

            # Back up every file that will be overwritten. Roll back if any replacement fails.
            backup_dir = os.path.join(temp_root, "backup")
            os.makedirs(backup_dir)
            changes = []
            for root, dirs, files in os.walk(stage_dir):
                for filename in files:
                    staged_file = os.path.join(root, filename)
                    rel_path = os.path.relpath(staged_file, stage_dir)
                    target_file = os.path.join(base_dir, rel_path)
                    backup_file = os.path.join(backup_dir, rel_path)
                    os.makedirs(os.path.dirname(target_file), exist_ok=True)
                    if os.path.isfile(target_file):
                        os.makedirs(os.path.dirname(backup_file), exist_ok=True)
                        shutil.copy2(target_file, backup_file)
                        existed = True
                    else:
                        existed = False
                    changes.append((staged_file, target_file, backup_file, existed))

            installed = []
            try:
                # main.py is installed last so the updater can finish running first.
                changes.sort(key=lambda item: (os.path.basename(item[1]) == "main.py", item[1]))
                for staged_file, target_file, backup_file, existed in changes:
                    shutil.copy2(staged_file, target_file)
                    installed.append((target_file, backup_file, existed))
            except Exception:
                for target_file, backup_file, existed in reversed(installed):
                    try:
                        if existed and os.path.isfile(backup_file):
                            shutil.copy2(backup_file, target_file)
                        elif os.path.exists(target_file):
                            os.remove(target_file)
                    except OSError:
                        pass
                print("Update failed. The updater attempted to restore the previous files.")
                return

        print(f"PythonOS was updated to v{latest_version}!")
        print("Restart PythonOS to use the new version.")
        print("Your preserved accounts, installed modules, and PkgLib data were kept.")
    except (OSError, urllib.error.URLError, TimeoutError, zipfile.BadZipFile) as error:
        print(f"Update failed: {error}")
        print("Your existing PythonOS files have not been intentionally removed.")


# Modules successfully imported during this PythonOS session.
loaded_modules = {}


def load_accounts():
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, "r") as file:
            return json.load(file)

    return {}


def save_accounts(accounts):
    with open(ACCOUNTS_FILE, "w") as file:
        json.dump(accounts, file, indent=4)


def generate_account_id(accounts):
    while True:
        account_id = f"{randint(1000, 9999)}-{randint(1000, 9999)}"

        if account_id not in accounts:
            return account_id


def import_module(module_id):
    # Only allow simple module IDs.
    if not re.fullmatch(r"[A-Za-z0-9_-]+", module_id):
        print("Invalid module ID.")
        return

    if module_id in loaded_modules:
        print(f"Module '{module_id}' is already imported.")
        return

    # Find modules relative to this main.py file.
    base_dir = os.path.dirname(os.path.abspath(__file__))
    module_dir = os.path.realpath(
        os.path.join(base_dir, "modules", module_id)
    )
    modules_dir = os.path.realpath(
        os.path.join(base_dir, "modules")
    )

    # Ensure the module directory stays inside modules/.
    if os.path.commonpath([modules_dir, module_dir]) != modules_dir:
        print("Invalid module directory.")
        return

    manifest_path = os.path.join(module_dir, "module.json")

    if not os.path.isfile(manifest_path):
        print(f"Module '{module_id}' not found.")
        return

    # Read the module metadata.
    try:
        with open(manifest_path, "r", encoding="utf-8") as file:
            metadata = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        print(f"Could not read module metadata: {error}")
        return

    if not isinstance(metadata, dict):
        print("Invalid module metadata: expected a JSON object.")
        return

    required_fields = ("name", "description", "id", "version", "entry")

    for field in required_fields:
        if not isinstance(metadata.get(field), str) or not metadata[field]:
            print(f"Invalid module metadata: missing or invalid '{field}'.")
            return

    if metadata["id"] != module_id:
        print("Module ID does not match the requested ID.")
        return

    # Entry files must be filenames inside the module directory.
    entry = metadata["entry"]

    if entry in (".", "..") or os.path.basename(entry) != entry:
        print("Invalid module entry filename.")
        return

    entry_path = os.path.realpath(os.path.join(module_dir, entry))

    if os.path.commonpath([module_dir, entry_path]) != module_dir:
        print("Module entry points outside its directory.")
        return

    if not os.path.isfile(entry_path):
        print(f"Module entry file not found: {entry}")
        return

    # Prepare the Python module.
    python_name = f"_pyos_module_{module_id}"

    try:
        spec = importlib.util.spec_from_file_location(
            python_name, entry_path
        )

        if spec is None or spec.loader is None:
            print("Could not create a module loader.")
            return

        module = importlib.util.module_from_spec(spec)
        sys.modules[python_name] = module

        try:
            spec.loader.exec_module(module)

            on_import = getattr(module, "on_import", None)

            if on_import is not None and not callable(on_import):
                raise TypeError("on_import must be a function.")

            # Capture initialization output so a failed initialization
            # doesn't print a misleading success message first.
            output = io.StringIO()

            if on_import is not None:
                with redirect_stdout(output):
                    on_import()

        except Exception:
            sys.modules.pop(python_name, None)
            raise

    except Exception as error:
        print(f"Module import failed: {error}")
        return

    # Register only after loading and initialization succeed.
    loaded_modules[module_id] = {
        "module": module,
        "metadata": metadata,
        "python_name": python_name,
    }

    print("Imported module successfully!")
    print(f"Name: {metadata['name']}")
    print(f"Description: {metadata['description']}")
    print(f"ID: {metadata['id']}")
    print(f"Version: {metadata['version']}")
    print("-------------------------------------------")
    print("on_import() COMMAND :")

    if on_import is not None:
        print(output.getvalue(), end="")
    else:
        print("No on_import() function found.")


accounts = load_accounts()
current_account = None


print("Starting PythonOS...")
time.sleep(3)

print("PythonOS booted successfully.")
time.sleep(1)

print("Loading PyTerminal...")
time.sleep(3)

print("PyTerminal loaded successfully.")
time.sleep(1)
print("Welcome to PythonOS.")
print("Type 'help' for a list of available commands.")

while True:
    command = input("root@pythonos> ")

    if command == "help":
        print(" ")
        print("List of PythonOS commands")
        print(" ")
        print("help          - Prints a list of available commands")
        print("whoami        - Prints who the computer thinks you are.")
        print("about         - Prints things about the OS")
        print("other         - Prints other projects I made")
        print("exit          - Shuts down PythonOS")
        print("user          - See PyOS Account details")
        print("user create   - Create a PyOS Account")
        print("user login    - Log into a PyOS Account")
        print("user logout   - Log out of the current account")
        print("user rename   - Change your PyOS Account name")
        print("rannum        - Prints a random number from 1 to 100")
        print("clear         - Clears the screen")
        print("!!            - Activates the emergency protocol.")
        print("import -help  - Prints help about the import command")
        print("what          - WHAT")
        print("pkglib        - PyOS PkgLib package manager (type 'pkglib help')")
        print("update        - Check GitHub for a newer PythonOS version")

    elif command == "whoami":
        print("root")

    elif command == "about":
        print("PythonOS v1.3")
        print("PythonOS is powered by PyTerminal.")
        print("PythonOS made by UnknownDotOrg.")

    elif command == "exit":
        print("Shutting down PythonOS...")
        break

    elif command == "other":
        print("Other projects I made")
        print("NEON RHYTHM - A rhythm game entirely using Python and Pygame.")
        print("useless - A useless Python module.")
        print("amogus - It's a Python module. Why did I make this? I have no idea.")

    elif command == "user":
        if current_account is None:
            print("No PyOS Account is currently logged in.")
        else:
            print("PyOS Account details")
            print(f"Username : {current_account['username']}")
            print(f"Account ID : {current_account['id']}")

    elif command == "user create":
        if current_account is not None:
            print("You are already logged into a PyOS Account.")
        else:
            username = input("Choose a username: ")
            password = input("Choose a password: ")

            if username == "":
                print("Username cannot be empty.")
            elif password == "":
                print("Password cannot be empty.")
            else:
                account_id = generate_account_id(accounts)

                accounts[account_id] = {
                    "id": account_id,
                    "username": username,
                    "password": password
                }

                save_accounts(accounts)
                current_account = accounts[account_id]

                print(" ")
                print("PyOS Account created successfully!")
                print(f"Username : {username}")
                print(f"Account ID : {account_id}")

    elif command == "user login":
        if current_account is not None:
            print("You are already logged into a PyOS Account.")
        else:
            account_id = input("Enter your Account ID: ")

            if account_id in accounts:
                password = input("Enter your password: ")

                if password == accounts[account_id]["password"]:
                    current_account = accounts[account_id]
                    print(f"Welcome back, {current_account['username']}!")
                else:
                    print("Incorrect password.")
            else:
                print("Account not found.")
                print("Please check your Account ID and try again.")

    elif command == "user logout":
        if current_account is None:
            print("You are not logged into a PyOS Account.")
        else:
            print(f"Goodbye, {current_account['username']}!")
            current_account = None

    elif command == "user rename":
        if current_account is None:
            print("You must be logged into a PyOS Account.")
        else:
            print(f"Current username: {current_account['username']}")
            new_username = input("Enter your new username: ")

            if new_username == "":
                print("Username cannot be empty.")
            else:
                current_account["username"] = new_username
                save_accounts(accounts)

                print("Username changed successfully!")
                print(f"New username: {new_username}")

    elif command == "rannum":
        print(randint(1, 100))

    elif command == "clear":
        if os.name == "nt":
            os.system("cls")
        else:
            os.system("clear")

    elif command == "!!":
        print("! EMERGENCY PROTOCOL ACTIVATED !")
        print("Shutting down PythonOS...")
        break

    elif command == "import -help":
        print("import COMMAND HELP")
        print("import <module_id> - Imports a module from the modules folder.")
        print("Example: import test")

    elif command == "import" or command.startswith("import "):
        parts = command.split(maxsplit=1)

        if len(parts) != 2 or not parts[1].strip():
            print("Usage: import <module_id>")
        else:
            import_module(parts[1].strip())

    elif command == "what":
        print("WHAT")

    elif command == "update":
        update_pythonos()

    elif command == "pkglib" or command.startswith("pkglib "):
        pkglib.handle_command(command)

    else:
        # Built-in commands above always take priority.
        if command in loaded_modules:
            module = loaded_modules[command]["module"]
            run_function = getattr(module, "run", None)

            if not callable(run_function):
                print(f"Module '{command}' has no run() function.")
            else:
                try:
                    run_function()
                except Exception as error:
                    print(f"Module execution failed: {error}")
        else:
            print(f"Command not found: {command}")
            print("Type 'help' for a list of available commands.")
