# Contribuindo com o Pomodoro Inteligente

Obrigado pelo interesse em contribuir!

## Reportar um bug

Use o template **Bug Report** nas Issues do GitHub. Inclua:
- Sistema operacional e versão do Python
- Passos para reproduzir
- Comportamento esperado vs. atual
- Logs ou mensagens de erro (se houver)

## Sugerir uma feature

Use o template **Feature Request** nas Issues. Descreva o problema que a feature resolve.

## Rodar localmente

**Windows:**
```bash
pip install pynput pystray Pillow
pythonw pomodoro_windows.py
```

**Linux/Ubuntu:**
```bash
pip install pynput pystray Pillow
sudo apt install python3-tk
python3 pomodoro_linux.py
```

Para testar o fluxo completo em ~30 segundos, veja a seção **Quick Test** no README.

## Estilo de código

- PEP 8
- Comentários em português (PT-BR)
- Sem dependências além de `pynput`, `pystray`, `Pillow`
- UI apenas com `tkinter` (sem bibliotecas de widgets externas)
- Toda atualização de UI deve ocorrer na thread principal via `root.after(0, callback)`

## Pull Requests

1. Fork → branch com nome descritivo (`feat/minha-feature`)
2. Commits pequenos e focados
3. Teste o fluxo completo (Quick Test) antes de abrir o PR
4. Descreva o que mudou e por quê
