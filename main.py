import time
import json
import os
import importlib.util
from random import randint

ACCOUNTS_FILE = "accounts.json"
MODULES_FOLDER = "modules"


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


def load_module(module_name):
    module_folder = os.path.join(MODULES_FOLDER, module_name)
    module_file = os.path.join(module_folder, "module.json")

    if not os.path.exists(module_file):
        return None

    try:
        with open(module_file, "r") as file:
            module_data = json.load(file)

        return module_data

    except json.JSONDecodeError:
        print(f"Error: Module '{module_name}' has invalid JSON.")
        return None

    except OSError as error:
        print(f"Error loading module '{module_name}': {error}")
        return None


def execute_module(module_name, module_data):
    module_folder = os.path.join(MODULES_FOLDER, module_name)

    if "entry" not in module_data:
        print(f"Error: Module '{module_name}' does not specify an entry file.")
        return None

    entry_file = os.path.join(module_folder, module_data["entry"])

    if not os.path.exists(entry_file):
        print(f"Error: Entry file '{module_data['entry']}' was not found.")
        return None

    try:
        spec = importlib.util.spec_from_file_location(
            f"pyos_module_{module_name}",
            entry_file
        )

        if spec is None or spec.loader is None:
            print(f"Error: Could not load module '{module_name}'.")
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        return module

    except Exception as error:
        print(f"Error while loading module '{module_name}': {error}")
        return None


def list_modules():
    if not os.path.exists(MODULES_FOLDER):
        return []

    modules = []

    for module_name in os.listdir(MODULES_FOLDER):
        module_folder = os.path.join(MODULES_FOLDER, module_name)

        if not os.path.isdir(module_folder):
            continue

        module_file = os.path.join(module_folder, "module.json")

        if os.path.exists(module_file):
            modules.append(module_name)

    return sorted(modules)


os.makedirs(MODULES_FOLDER, exist_ok=True)


accounts = load_accounts()
current_account = None
imported_modules = {}


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
    command = input("root@pythonOS> ")

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
        print("!!            - Activates the emergency protocol. Run this command only in cases of emergencys.")
        print("import -help  - Prints help about the import command")

    elif command == "whoami":
        print("root")

    elif command == "about":
        print("PythonOS v0.4")
        print("PythonOS is powered by PyTerminal (aka your terminal).")
        print("PythonOS made by UnknownDotOrg.")

    elif command == "exit":
        print("Shutting down PythonOS...")
        break

    elif command == "other":
        print("Other projects I made.")
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
        print(" ")
        print("import COMMAND HELP")
        print(" ")
        print("import <module>  - Imports a local PyOS module")
        print("import -list     - Lists installed PyOS modules")
        print("import -help     - Prints this help")
        print(" ")

    elif command == "import -list":
        modules = list_modules()

        print(" ")
        print("Installed PyOS modules")
        print(" ")

        if len(modules) == 0:
            print("No modules are installed.")
        else:
            for module_name in modules:
                print(f"- {module_name}")

        print(" ")

    elif command.startswith("import "):
        module_name = command[7:].strip()

        if module_name == "":
            print("Usage: import <module>")
        else:
            print(f"Searching for module '{module_name}'...")

            module_data = load_module(module_name)

            if module_data is None:
                print(f"Module '{module_name}' was not found in the modules/ folder.")
                print("")
                continue

            print(f"Module '{module_name}' found!")
            print("Loading module...")

            module = execute_module(module_name, module_data)

            if module is None:
                print(f"Module '{module_name}' could not be loaded.")
                print("")
                continue

            imported_modules[module_name] = module

            if hasattr(module, "on_import"):
                try:
                    module.on_import()
                except Exception as error:
                    print(f"Error in module on_import(): {error}")

            print(f"Module '{module_name}' imported successfully!")

            if "name" in module_data:
                print(f"Name        : {module_data['name']}")

            if "version" in module_data:
                print(f"Version     : {module_data['version']}")

            if "author" in module_data:
                print(f"Author      : {module_data['author']}")

            if "description" in module_data:
                print(f"Description : {module_data['description']}")

    else:
        if command in imported_modules:
            module = imported_modules[command]

            if hasattr(module, "run"):
                try:
                    module.run()
                except Exception as error:
                    print(f"Error while running module '{command}': {error}")
            else:
                print(f"Module '{command}' does not have a run() function.")
        else:
            print(f"Command not found: {command}")
            print("Type 'help' for a list of available commands.")

