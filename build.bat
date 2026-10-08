@echo off
REM Lumen - build dev
setlocal
cd /d "%~dp0"
where python >nul 2>nul || (echo [ERRO] Python nao encontrado.& exit /b 1)
python -m pip install -r requirements.txt || exit /b 1
python -m PyInstaller --noconfirm --windowed --name Lumen-dev --icon assets\icon.ico --add-data "assets;assets" main.py || exit /b 1
echo.
echo [OK] Executavel em dist\Lumen-dev.exe
