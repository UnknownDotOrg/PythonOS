
import time
import json
import os
import re
import sys
import io
import importlib.util
from contextlib import redirect_stdout
from random import randint

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

    elif command == "whoami":
        print("root")

    elif command == "about":
        print("PythonOS v1.1")
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
