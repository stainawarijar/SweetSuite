# For use with Git Bash (MinGW) in Windows.
# Bundles the program and all its dependencies into a single executable file.

echo -e "\nCreating virtual environment...\n"
py -3.14 -m venv venv
source venv/Scripts/activate

echo -e "\nChecking required dependencies...\n"
python.exe -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

echo -e "\nRunning PyInstaller...\n"
pyinstaller --onefile \
  --splash "sweet_suite\gui\assets\sweetsuite_loading.png" \
  --add-data "sweet_suite\gui\assets\google-material-icons\*.svg;sweet_suite\gui\assets\google-material-icons" \
  --add-data "sweet_suite\resources\templates\*.xlsx;sweet_suite\resources\templates" \
  --add-data "sweet_suite\resources\templates\*.block;sweet_suite\resources\templates" \
  --add-data "sweet_suite\resources\templates\*.csv;sweet_suite\resources\templates" \
  main.py

echo -e "\nDeactivating virtual environment...\n"
deactivate

read -p "Press Enter to close..."