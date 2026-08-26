@echo off
setlocal

where python >nul 2>nul
if errorlevel 1 goto no_python

python -c "from PIL import Image, ImageTk" >nul 2>nul
if errorlevel 1 (
    echo Daily Dress Skin Styler needs the small Pillow image library.
    echo.
    choice /C YN /M "Install Pillow automatically now"
    if errorlevel 2 exit /b 1
    python -m pip install --user Pillow
    if errorlevel 1 (
        echo.
        echo Pillow could not be installed. Check the internet connection and try again.
        pause
        exit /b 1
    )
)

where pythonw >nul 2>nul
if errorlevel 1 (
    python "%~dp0skin_styler_gui.py"
) else (
    start "Daily Dress Skin Styler" pythonw "%~dp0skin_styler_gui.py"
)
exit /b 0

:no_python
echo Daily Dress Skin Styler needs Python 3.
echo Install Python from https://www.python.org/downloads/
echo During setup, enable "Add Python to PATH", then open this launcher again.
echo.
pause
exit /b 1
