#!/bin/bash

echo "Note: this only works on Linux systems. On Windows or macOS, you'll have to delete the folder manually."
read -p "This will erase PythonOS and all data of PythonOS. Do you REALLY want to continue? [y/n] : " confirmation

# Conversion en minuscules pour simplifier la vérification
confirmation=${confirmation,,}

if [[ "$confirmation" =~ ^(yes|y)$ ]]; then
    echo "Uninstalling PythonOS..."
    rm -rf ../PythonOS/
else
    echo "PythonOS uninstallation cancelled."
    exit 1
fi
