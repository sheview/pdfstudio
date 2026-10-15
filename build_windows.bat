@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ============================================
echo   PDF Studio - สร้างโปรแกรมติดตั้ง (Windows)
echo ============================================
where py >nul 2>nul || (echo ไม่พบ Python - ติดตั้ง Python 3.11/3.12 64-bit จาก python.org แล้วติ๊ก "Add to PATH" & pause & exit /b 1)

if not exist venv (
  echo [1/4] สร้าง virtual environment...
  py -3 -m venv venv || (pause & exit /b 1)
)
call venv\Scripts\activate.bat
echo [2/4] ติดตั้งไลบรารี...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt pyinstaller || (pause & exit /b 1)

echo [3/4] สร้างไอคอน...
python make_icon.py

echo [4/4] สร้างไฟล์ .exe ด้วย PyInstaller...
pyinstaller --noconfirm --clean --windowed --name "PDF Studio" ^
  --icon assets\icon.ico --add-data "assets;assets" ^
  --collect-all qtawesome --collect-all pymupdf ^
  --exclude-module tkinter --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtQml ^
  --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtMultimedia ^
  main.py || (pause & exit /b 1)

echo.
echo เสร็จแล้ว: dist\PDF Studio\PDF Studio.exe  (ลองดับเบิลคลิกทดสอบได้เลย)
echo ถ้าต้องการตัวติดตั้ง Setup.exe ให้เปิด installer.iss ด้วย Inno Setup (jrsoftware.org) แล้วกด Compile
pause
