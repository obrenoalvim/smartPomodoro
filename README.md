# 🍅 Pomodoro Inteligente

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey)](.)

> **PT:** Timer Pomodoro que detecta atividade real de mouse e teclado — só te interrompe quando você realmente parou de trabalhar.
>
> **EN:** Pomodoro timer that detects real mouse and keyboard activity — only notifies you when you've actually stopped working.

---

## ✨ Como funciona / How it works

| PT | EN |
|----|----|
| O timer de 25 min inicia normalmente | 25-min focus timer starts normally |
| Ao zerar, detecta se você ainda está ativo | When it ends, it checks if you're still active |
| Se ativo → modo **Extensão** (tempo extra acumula) | If active → **Extension** mode (extra time accumulates) |
| Ao parar por `N` segundos → notificação de descanso | After `N` seconds idle → break notification appears |
| Descanso = base + bônus proporcional ao tempo extra | Break = base + bonus proportional to extra time |

**Diferencial / What sets it apart:** A maioria dos apps Pomodoro interrompe você rigidamente no timer. Este espera você parar de verdade. / Most Pomodoro apps interrupt you exactly at the timer. This one waits until you actually stop.

---

## 📦 Instalação / Installation

### Windows

```bash
pip install pynput pystray Pillow
```

```bash
pythonw pomodoro_windows.py
```

### Linux / Ubuntu

```bash
pip install pynput pystray Pillow
sudo apt install python3-tk
python3 pomodoro_linux.py
```

> **Permissões pynput (se não funcionar) / pynput permissions (if not working):**
> ```bash
> sudo usermod -aG input $USER  # logout/login depois / after
> ```

---

## 🚀 Uso / Usage

- O app inicia minimizado na bandeja do sistema / App starts minimized in system tray
- Clique no ícone da bandeja para abrir / Click the tray icon to open
- Clique em **⚙** para abrir/fechar configurações / Click **⚙** to toggle settings
- O ícone muda de cor conforme o estado / Tray icon changes color by state:
  - 🔵 Foco / Focus
  - 🟠 Extensão / Extension
  - 🟢 Descanso / Break
  - ⚫ Pausado / Paused

---

## ⚙️ Configurações / Configuration

| Parâmetro / Parameter | Padrão / Default | Descrição PT | Description EN |
|----------------------|-----------------|--------------|----------------|
| `foco_minutos` | `25` | Duração do foco em minutos | Focus duration in minutes |
| `descanso_base_minutos` | `5` | Descanso base em minutos | Base break duration in minutes |
| `inatividade_segundos` | `8` | Segundos sem input para disparar descanso | Seconds without input to trigger break |
| `fator_bonus` | `0.25` | Multiplicador do tempo extra no descanso | Break bonus multiplier for extra time |
| `som_ativado` | `true` | Ativar/desativar som de notificação | Enable/disable notification sound |
| `minimizar_para_tray` | `true` | Fechar janela minimiza para bandeja | Close button minimizes to tray |

**Configurações salvas em / Config saved at:**
- Windows: `%APPDATA%\PomodoroInteligente\config.json`
- Linux: `~/.config/pomodoro_inteligente/config.json`

---

## 🧪 Teste rápido / Quick Test

PT: Para validar o fluxo completo sem esperar 25 minutos:  
EN: To validate the full flow without waiting 25 minutes:

1. Abra o app / Open the app
2. Clique ⚙ → **Foco (min):** `0.1` (= 6 segundos / 6 seconds)
3. **Inatividade (s):** `3`
4. Clique fora para salvar / Click outside to save
5. Clique **Resetar** / Click **Resetar**
6. Aguarde 6s → timer zera / Wait 6s → timer reaches zero
7. Mova o mouse → modo **Extensão** (ícone laranja) / Move mouse → **Extension** mode (orange icon)
8. Pare por 3s → janela de descanso aparece / Stop for 3s → break window appears
9. Clique **Começar descanso** → timer de descanso inicia / Click **Começar descanso** → break timer starts
10. Aguarde o descanso terminar → volta ao foco / Wait for break to end → returns to focus

---

## 🤝 Contribuindo / Contributing

Leia [CONTRIBUTING.md](CONTRIBUTING.md) para guias de contribuição.  
Read [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

---

## 📄 Licença / License

MIT — veja [LICENSE](LICENSE) para detalhes / see [LICENSE](LICENSE) for details.
