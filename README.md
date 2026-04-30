# Pomodoro Inteligente

Timer Pomodoro que não interrompe você no meio de uma tarefa.
Detecta atividade real de mouse/teclado para decidir quando avisar sobre o descanso.

## Como funciona

1. Timer conta 25 min normalmente
2. Ao zerar: verifica se você está ativo (mouse/teclado)
3. Se ativo → entra em "extensão silenciosa" (ícone laranja no tray)
4. Quando você para por 8s → aparece notificação de descanso
5. Tempo de descanso = base + bônus proporcional ao tempo extra trabalhado

## Instalação — Windows

```powershell
pip install pynput pystray Pillow
python pomodoro_windows.py
```

## Instalação — Linux/Ubuntu

```bash
sudo apt install python3-tk python3-pip
pip install pynput pystray Pillow
python3 pomodoro_linux.py
```

### Problema de permissão (pynput no Linux)

Se aparecer erro de permissão nos hooks globais:

```bash
sudo usermod -aG input $USER
# Logout e login novamente, depois:
python3 pomodoro_linux.py
```

Alternativa rápida (sem logout):
```bash
sudo python3 pomodoro_linux.py
```

**Modo degradado:** se sem permissão, o app funciona como timer normal sem detecção de atividade.

## Configurações

| Campo | Padrão | Descrição |
|-------|--------|-----------|
| Foco (min) | 25 | Duração da sessão de foco |
| Descanso (min) | 5 | Tempo base de descanso |
| Fator bônus | 0.25 | Multiplicador do tempo extra (0.25 = 25%) |
| Inatividade (s) | 8 | Segundos sem atividade para acionar notificação |

Configurações salvas automaticamente em:
- Windows: `%APPDATA%\PomodoroInteligente\config.json`
- Linux: `~/.config/pomodoro_inteligente/config.json`

## Teste rápido

Configure Foco=0.1 min e Inatividade=3s, clique Resetar, e valide o fluxo completo em ~20 segundos.
