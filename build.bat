@echo off
setlocal
python -m PyInstaller --noconfirm --clean --onefile --windowed --name EtherDrop --manifest EtherDrop.manifest --add-data "RELEASE_NOTES.md:." etherdrop.py
if errorlevel 1 (
  echo.
  echo Build failed.
  exit /b 1
)
echo.
echo Built successfully: dist\EtherDrop.exe
