@echo off
echo === Pomodoro Inteligente — Build Instalador ===
echo.

echo [1/4] Instalando dependencias...
pip install pyinstaller pillow -q

echo [2/4] Gerando icone...
python create_icon.py
if not exist pomodoro.ico (
    echo ERRO: pomodoro.ico nao foi gerado. Verifique logo.png.
    pause & exit /b 1
)

echo [3/4] Compilando executavel...
pyinstaller --onedir --windowed ^
    --name "Pomodoro Inteligente" ^
    --icon "pomodoro.ico" ^
    --add-data "pomodoro.ico;." ^
    --add-data "logo.png;." ^
    --hidden-import "pystray._win32" ^
    --hidden-import "pynput.keyboard._win32" ^
    --hidden-import "pynput.mouse._win32" ^
    --hidden-import "PIL._tkinter_finder" ^
    pomodoro_windows.py
if not exist "dist\Pomodoro Inteligente\Pomodoro Inteligente.exe" (
    echo ERRO: PyInstaller falhou.
    pause & exit /b 1
)

echo [4/4] Gerando instalador...
set ISCC=
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set ISCC=C:\Program Files\Inno Setup 6\ISCC.exe

if "%ISCC%"=="" (
    echo.
    echo ATENCAO: Inno Setup nao encontrado.
    echo   Instale com: winget install JRSoftware.InnoSetup
    echo   Depois execute este script novamente.
    echo.
    echo O executavel esta disponivel em: "dist\Pomodoro Inteligente\"
    pause & exit /b 0
)

"%ISCC%" PomodoroInteligente.iss
if exist Output\PomodoroInteligente_Setup.exe (
    echo.
    echo OK - Instalador: Output\PomodoroInteligente_Setup.exe
) else (
    echo ERRO - Inno Setup falhou.
)
pause
