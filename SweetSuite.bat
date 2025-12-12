@echo off

@echo Creating virtual environment...
py -3.14 -m venv venv

echo(
@echo Activating virtual environment...
call venv\Scripts\activate

echo(
@echo Checking required dependencies...
echo.
python.exe -m pip install --upgrade pip
pip install -r requirements.txt

echo(
@echo Launching SweetSuite...
echo.
python main.py
