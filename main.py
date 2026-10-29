
import time
import json
import os
import re
import sys
import io
import importlib.util
import urllib.request
import urllib.error
import tempfile
import shutil
import zipfile
from contextlib import redirect_stdout
from random import randint

GITHUB_REPO = "UnknownDotOrg/PythonOS"
ACCOUNTS_FILE = "accounts.json"

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



def ask_yes_no(prompt):
    while True:
        answer = input(prompt).strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer y or n.")


def version_key(version):
    numbers = re.findall(r"\d+", str(version))
    return tuple(int(n) for n in numbers) if numbers else (0,)


def update_pythonos():
    print(f"Checking for updates on https://github.com/{GITHUB_REPO}...")
    # PythonOS currently publishes source through the repository's main branch,
    # not GitHub Releases. Read VERSION from the online main.py and download that
    # branch's ZIP if it is newer.
    version_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/main.py"
    archive_url = f"https://github.com/{GITHUB_REPO}/archive/refs/heads/main.zip"
    request = urllib.request.Request(
        version_url,
        headers={"User-Agent": "PythonOS-Updater"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            online_main = response.read().decode("utf-8")
        match = re.search("^VERSION\\s*=\\s*['\\\"]([^'\\\"]+)['\\\"]", online_main, re.MULTILINE)
        if not match:
            raise ValueError("The GitHub main.py does not define VERSION yet.")
        latest_version = match.group(1).strip()
        if not latest_version:
            raise ValueError("The GitHub main.py has an empty VERSION.")
    except urllib.error.HTTPError as error:
        print(f"Could not check GitHub (HTTP {error.code}).")
        return
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, ValueError) as error:
        print(f"Could not check for updates: {error}")
        return

    print(f"Current version: v{VERSION}")
    print(f"Latest version:  {latest_version.lstrip('vV')}")
    if version_key(latest_version) <= version_key(VERSION):
        print("PythonOS is already up to date!")
        return
    print("An update is available!")
    if not ask_yes_no("Download it? [y/n] "):
        print("Update cancelled.")
        return

    keep_accounts = ask_yes_no(
        "Keep current accounts in accounts.json and put them in the new version? [y/n] "
    )
    keep_packages = ask_yes_no(
        "Keep current PythonOS packages and put them in the new version? [y/n] "
    )

    base_dir = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory(prefix="pythonos-update-") as work:
        archive_path = os.path.join(work, "update.zip")
        extracted = os.path.join(work, "extracted")
        staged = os.path.join(work, "staged")
        backup = os.path.join(work, "backup")
        os.makedirs(extracted)
        os.makedirs(staged)
        os.makedirs(backup)

        try:
            print("Downloading update...")
            download_request = urllib.request.Request(
                archive_url, headers={"User-Agent": "PythonOS-Updater"}
            )
            with urllib.request.urlopen(download_request, timeout=60) as response:
                with open(archive_path, "wb") as output:
                    shutil.copyfileobj(response, output)

            with zipfile.ZipFile(archive_path, "r") as archive:
                if archive.testzip() is not None:
                    raise ValueError("ZIP integrity check failed.")
                root_real = os.path.realpath(extracted)
                for member in archive.infolist():
                    target = os.path.realpath(os.path.join(extracted, member.filename))
                    if os.path.commonpath([root_real, target]) != root_real:
                        raise ValueError("The archive contains an unsafe path.")
                archive.extractall(extracted)

            release_root = None
            for root, dirs, names in os.walk(extracted):
                if "main.py" in names and "README.txt" in names and "changelog" in names:
                    release_root = root
                    break
            if release_root is None:
                raise ValueError("This archive does not look like a PythonOS source release.")
            if not os.path.isdir(os.path.join(release_root, "modules")):
                raise ValueError("The release is missing its modules directory.")

            for name in ("main.py", "README.txt", "changelog"):
                shutil.copy2(os.path.join(release_root, name), os.path.join(staged, name))

            release_accounts = os.path.join(release_root, "accounts.json")
            current_accounts = os.path.join(base_dir, "accounts.json")
            if keep_accounts and os.path.isfile(current_accounts):
                shutil.copy2(current_accounts, os.path.join(staged, "accounts.json"))
            elif os.path.isfile(release_accounts):
                shutil.copy2(release_accounts, os.path.join(staged, "accounts.json"))
            else:
                with open(os.path.join(staged, "accounts.json"), "w", encoding="utf-8") as f:
                    json.dump({}, f, indent=4)

            current_modules = os.path.join(base_dir, "modules")
            release_modules = os.path.join(release_root, "modules")
            if keep_packages and os.path.isdir(current_modules):
                shutil.copytree(current_modules, os.path.join(staged, "modules"))
            else:
                shutil.copytree(release_modules, os.path.join(staged, "modules"))

            print("Download verified.")
            print("Backing up current installation...")
            managed = ["main.py", "README.txt", "changelog", "accounts.json", "modules"]
            existed = {}
            for name in managed:
                current = os.path.join(base_dir, name)
                existed[name] = os.path.exists(current)
                saved = os.path.join(backup, name)
                if os.path.isdir(current):
                    shutil.copytree(current, saved)
                elif os.path.isfile(current):
                    shutil.copy2(current, saved)
            print("Done!")
            print("Installing update...")
            try:
                # Install program files last, so main.py is replaced at the end.
                for name in ("modules", "accounts.json", "README.txt", "changelog", "main.py"):
                    current = os.path.join(base_dir, name)
                    prepared = os.path.join(staged, name)
                    if os.path.isdir(current):
                        shutil.rmtree(current)
                    elif os.path.isfile(current):
                        os.remove(current)
                    if os.path.isdir(prepared):
                        shutil.copytree(prepared, current)
                    else:
                        shutil.copy2(prepared, current)
            except Exception:
                print("Installation failed. Restoring the backup...")
                for name in managed:
                    current = os.path.join(base_dir, name)
                    if os.path.isdir(current):
                        shutil.rmtree(current)
                    elif os.path.isfile(current):
                        os.remove(current)
                    saved = os.path.join(backup, name)
                    if existed[name]:
                        if os.path.isdir(saved):
                            shutil.copytree(saved, current)
                        elif os.path.isfile(saved):
                            shutil.copy2(saved, current)
                print("Backup restored. Your previous PythonOS files were kept.")
                return

            print("Done!")
            print("Accounts preserved." if keep_accounts else "Previous accounts were not carried over.")
            print("Packages preserved." if keep_packages else "Previous modules were replaced.")
            print("Please restart PythonOS to use the update.")
        except (OSError, urllib.error.URLError, zipfile.BadZipFile, ValueError, shutil.Error) as error:
            print(f"Update failed: {error}")
            print("Your current installation has not been replaced.")

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

    if command == "update":
        update_pythonos()

    elif command == "help":
        print(" ")
        print("List of PythonOS commands")
        print(" ")
        print("help          - Prints a list of available commands")
        print("whoami        - Prints who the computer thinks you are.")
        print("about         - Prints things about the OS")
        print("update        - Checks GitHub for PythonOS updates")
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
        print("update        - Updated PythonOS to the newest version.")

    elif command == "whoami":
        print("root")

    elif command == "about":
        print(f"PythonOS v1.3")
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
