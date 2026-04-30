@echo off
echo Instalando dependencias...
pip install pyinstaller pillow -q

echo Gerando icone...
python create_icon.py

echo Compilando executavel...
pyinstaller --onefile --windowed ^
    --name "PomodoroInteligente" ^
    --icon "pomodoro.ico" ^
    --add-data "pomodoro.ico;." ^
    --add-data "logo.png;." ^
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
