@echo off
setlocal
cd /d "%~dp0"
py -3 -m venv .venv-build
if errorlevel 1 goto fail
.venv-build\Scripts\python -m pip install --requirement requirements-build.txt
if errorlevel 1 goto fail
.venv-build\Scripts\python -m unittest discover -s tests -v
if errorlevel 1 goto fail
.venv-build\Scripts\python -m PyInstaller --noconfirm --clean --onefile --windowed --name UCAS-Sign-in --add-data "LICENSE;." --add-data "NOTICE;." --add-data "LICENSES;LICENSES" app.py
if errorlevel 1 goto fail
.venv-build\Scripts\python verify_windows_build.py
if errorlevel 1 goto fail
echo Build complete: dist\UCAS-Sign-in.exe
exit /b 0
:fail
echo Build failed. See output above.
exit /b 1
