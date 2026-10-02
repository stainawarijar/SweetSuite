# For use with Git Bash (MinGW) in Windows.
# Bundles the program and all its dependencies into a single executable file.
GREEN="\e[32m"
RED="\e[31m"
RESET="\e[0m"

echo -e "${GREEN}\nCreating virtual environment...${RESET}\n"
py -3.14 -m venv venv
source venv/Scripts/activate

echo -e "${GREEN}\nChecking required dependencies...${RESET}\n"
python.exe -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
pip install pillow

echo -e "${GREEN}\nRunning PyInstaller...${RESET}\n"
VERSION=$(grep -oP '__version__\s*=\s*"\K[^"]+' sweet_suite/__init__.py)
APP_NAME="SweetSuite_v$VERSION"

# Convert PNG to ICO for embedding as the exe file icon
python -c "from PIL import Image; img = Image.open('sweet_suite/resources/images/logo_head.png'); img.save('sweet_suite/resources/images/logo_head.ico')"

if [ -d "dist/$APP_NAME" ] || [ -f "dist/$APP_NAME.exe" ]; then
  read -p "$(echo -e "${RED}dist/$APP_NAME already exists. Overwrite? (y/N): ${RESET}")" confirm
  if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}\nAborting. No files were changed.${RESET}\n"
    deactivate
    read -p "Press Enter to close..."
    exit 1
  fi
fi

# Bundle a startup hook that disables QuickEdit in the EXE's console.
# Keep console messages visible without changing users' registry settings.
mkdir -p build
QUICKEDIT_HOOK=$(mktemp "./build/quickedit_XXXXXX.py") || exit 1
trap 'rm -f "$QUICKEDIT_HOOK"' EXIT
cat > "$QUICKEDIT_HOOK" <<'PYTHON'
def disable_quick_edit():
    import sys
    if sys.platform != "win32":
        return

    import ctypes
    from ctypes import wintypes
    import warnings

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel32.GetStdHandle.restype = wintypes.HANDLE
    kernel32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetConsoleMode.restype = wintypes.BOOL
    kernel32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.SetConsoleMode.restype = wintypes.BOOL

    # STD_INPUT_HANDLE; explicit types preserve 64-bit Windows handles.
    handle = kernel32.GetStdHandle(wintypes.DWORD(-10))
    if handle in (None, 0, ctypes.c_void_p(-1).value):
        return
    mode = wintypes.DWORD()
    if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        return  # No console input buffer, for example when input is redirected.

    # Preserve other input modes, enable extended flags, and clear QuickEdit.
    new_mode = (mode.value | 0x0080) & ~0x0040
    if not kernel32.SetConsoleMode(handle, new_mode):
        warnings.warn(f"Could not disable console QuickEdit: {ctypes.WinError(ctypes.get_last_error())}")


disable_quick_edit()
del disable_quick_edit
PYTHON

pyinstaller \
  --onefile \
  --runtime-hook "$QUICKEDIT_HOOK" \
  --name "$APP_NAME" \
  --distpath "dist/$APP_NAME" \
  --noconfirm \
  --clean \
  --icon "sweet_suite\resources\images\logo_head.ico" \
  --add-data "sweet_suite\gui\assets\google-material-icons\*.svg;sweet_suite\gui\assets\google-material-icons" \
  --add-data "sweet_suite\resources\templates\*.xlsx;sweet_suite\resources\templates" \
  --add-data "sweet_suite\resources\templates\*.block;sweet_suite\resources\templates" \
  --add-data "sweet_suite\resources\templates\*.csv;sweet_suite\resources\templates" \
  --add-data "sweet_suite\resources\images\logo_head.png;sweet_suite\resources\images" \
  main.py

# Clean up temporary ICO file
rm -f sweet_suite/resources/images/logo_head.ico

echo -e "${GREEN}\nCopying blocks folder...${RESET}\n"
cp -r blocks "dist/$APP_NAME/"

echo -e "${GREEN}\nDeactivating virtual environment...${RESET}\n"
deactivate

# Clean up unused files
rm -f *.spec

read -p "Press Enter to close..."
