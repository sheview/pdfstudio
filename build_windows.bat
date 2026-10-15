@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ============================================
echo   PDF Governix - สร้างโปรแกรมติดตั้ง (Windows)
echo ============================================
where py >nul 2>nul || (echo ไม่พบ Python - ติดตั้ง Python 3.11/3.12 64-bit จาก python.org แล้วติ๊ก "Add to PATH" & pause & exit /b 1)

if not exist venv (
  echo [1/3] สร้าง virtual environment...
  py -3 -m venv venv || (pause & exit /b 1)
)
call venv\Scripts\activate.bat
echo [2/3] ติดตั้งไลบรารี...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt pyinstaller || (pause & exit /b 1)

echo [3/3] สร้างโปรแกรม...
python build_release.py
echo.
echo ถ้าขึ้นว่าไม่พบ Inno Setup ให้ติดตั้งจาก jrsoftware.org แล้วรันไฟล์นี้อีกครั้ง
echo (ทดลองใช้งานได้เลยที่ dist\PDF Governix\PDF Governix.exe)
pause
