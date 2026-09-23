import time
import json
import os
from random import randint

ACCOUNTS_FILE = "accounts.json"


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
        print("PythonOS v0.2.3")
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
        print("import -help")

    else:
        print(f"Command not found: {command}")
        print("Type 'help' for a list of available commands.")
