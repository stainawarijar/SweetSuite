# For use with Git Bash (MinGW) in Windows.
# Bundles the program and all its dependencies into a single executable file.
GREEN="\e[32m"
RESET="\e[0m"

echo -e "${GREEN}\nCreating virtual environment...${RESET}\n"
py -3.14 -m venv venv
source venv/Scripts/activate

echo -e "${GREEN}\nChecking required dependencies...${RESET}\n"
python.exe -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

echo -e "${GREEN}\nRunning PyInstaller...${RESET}\n"
VERSION=$(grep -oP '__version__\s*=\s*"\K[^"]+' sweet_suite/__init__.py)  # SweetSuite version number
APP_NAME="SweetSuite_v$VERSION"
pyinstaller \
  --onedir \
  --name "$APP_NAME" \
  --noconfirm \
  --clean \
  --windowed \
  --add-data "blocks;blocks" \
  --add-data "sweet_suite\gui\assets\google-material-icons\*.svg;sweet_suite\gui\assets\google-material-icons" \
  --add-data "sweet_suite\resources\templates\*.xlsx;sweet_suite\resources\templates" \
  --add-data "sweet_suite\resources\templates\*.block;sweet_suite\resources\templates" \
  --add-data "sweet_suite\resources\templates\*.csv;sweet_suite\resources\templates" \
  main.py
  
echo -e "${GREEN}\nCopying blocks folder...${RESET}\n"
cp -r blocks "dist/$APP_NAME/"

echo -e "${GREEN}\nDeactivating virtual environment...${RESET}\n"
deactivate

read -p "Press Enter to close..."
