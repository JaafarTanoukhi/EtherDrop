@echo off
setlocal
python -m PyInstaller --noconfirm --clean --onefile --windowed --name EtherDrop --icon "assets\etherdrop.ico" --manifest EtherDrop.manifest --add-data "RELEASE_NOTES.md:." --add-data "assets:assets" etherdrop.py
if errorlevel 1 (
  echo.
  echo Build failed.
  exit /b 1
)
echo.
echo Built successfully: dist\EtherDrop.exe
