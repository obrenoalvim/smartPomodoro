@echo off
echo Instalando PyInstaller...
pip install pyinstaller

echo.
echo Compilando executavel...
pyinstaller --onefile --windowed ^
    --name "PomodoroInteligente" ^
    --hidden-import "pystray._win32" ^
    --hidden-import "pynput.keyboard._win32" ^
    --hidden-import "pynput.mouse._win32" ^
    --hidden-import "PIL._tkinter_finder" ^
    pomodoro_windows.py

echo.
if exist dist\PomodoroInteligente.exe (
    echo OK - Executavel gerado: dist\PomodoroInteligente.exe
) else (
    echo ERRO - Build falhou. Verifique as mensagens acima.
)
pause
