@echo off
REM Lumen - build release otimizado: dist\Lumen.exe + .zip (~25MB)
REM Usa Lumen.spec (excludes PySide6 + UPX). NAO usa --collect-all PySide6
REM (isso puxava QtWebEngine 193MB e gerava ~235MB).
setlocal
cd /d "%~dp0"
where python >nul 2>nul || (echo [ERRO] Python nao encontrado.& exit /b 1)
echo [1/5] Instalando dependencias...
python -m pip install -r requirements.txt || exit /b 1
echo [2/5] Verificando UPX (compressao extra)...
where upx >nul 2>nul
if errorlevel 1 (
    echo [AVISO] UPX nao encontrado no PATH - tentando pasta local tools\upx...
    if exist "tools\upx\upx.exe" (
        set "PATH=%~dp0tools\upx;%PATH%"
        echo [OK] UPX local ativado.
    ) else (
        echo [AVISO] Sem UPX: o .exe sai ~35-40MB em vez de ~25MB. Baixe em https://github.com/upx/upx/releases e coloque upx.exe em tools\upx\ ou no PATH.
    )
) else (
    echo [OK] UPX encontrado.
)
echo [3/5] Limpando builds anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo [4/5] Compilando com spec otimizado...
python -m PyInstaller --noconfirm --clean Lumen.spec || exit /b 1
if not exist "dist\Lumen.exe" (echo [ERRO] Falha na compilacao.& exit /b 1)
echo [5/5] Gerando zip...
powershell -NoProfile -Command "Compress-Archive -Force 'dist\Lumen.exe' 'dist\Lumen.zip'"
echo.
echo [OK] dist\Lumen.exe gerado com sucesso.
dir dist
