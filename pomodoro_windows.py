#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pomodoro Inteligente - Windows
Detecta atividade real de mouse/teclado para não interromper o usuário.
Requer: pip install pynput pystray Pillow
"""

import os
import json
import time
import enum
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import winsound

try:
    from pynput import mouse, keyboard
    PYNPUT_OK = True
except ImportError:
    PYNPUT_OK = False

try:
    import pystray
    from PIL import Image, ImageDraw
    PYSTRAY_OK = True
except ImportError:
    PYSTRAY_OK = False

# ─── Constantes ───────────────────────────────────────────────────────────────
APP_NAME = "Pomodoro Inteligente"
CONFIG_PATH = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "PomodoroInteligente",
    "config.json"
)
CONFIG_DEFAULT = {
    "foco_minutos": 25,
    "descanso_base_minutos": 5,
    "fator_bonus": 0.25,
    "inatividade_segundos": 8,
    "som_ativado": True,
    "minimizar_para_tray": True,
}
COR_FOCO     = "#4CAF50"
COR_EXTENSAO = "#FF9800"
COR_DESCANSO = "#2196F3"
COR_PAUSADO  = "#9E9E9E"
COR_BG       = "#1E1E2E"
COR_FG       = "#CDD6F4"

class Estado(enum.Enum):
    FOCO     = "foco"
    EXTENSAO = "extensao"
    DESCANSO = "descanso"
    PAUSADO  = "pausado"


# ─── ConfigManager ────────────────────────────────────────────────────────────
class ConfigManager:
    """Carrega e salva configurações em JSON no diretório do usuário."""

    def __init__(self):
        self._cfg = dict(CONFIG_DEFAULT)
        self._carregar()

    def _carregar(self):
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                self._cfg.update(dados)
        except Exception:
            pass  # usa padrão se arquivo corrompido

    def salvar(self):
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._cfg, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get(self, chave):
        return self._cfg.get(chave, CONFIG_DEFAULT[chave])

    def set(self, chave, valor):
        self._cfg[chave] = valor
        self.salvar()


# ─── ActivityMonitor ──────────────────────────────────────────────────────────
class ActivityMonitor:
    """
    Monitora atividade global de mouse e teclado via pynput.
    Roda em threads separadas em segundo plano.
    """

    def __init__(self):
        self._ultimo = time.time()
        self._lock = threading.Lock()
        self._mouse_listener = None
        self._kb_listener = None
        self._ativo = False

    def iniciar(self):
        if not PYNPUT_OK:
            return False
        try:
            def _atividade(*args, **kwargs):
                with self._lock:
                    self._ultimo = time.time()

            self._mouse_listener = mouse.Listener(
                on_move=_atividade,
                on_click=_atividade,
                on_scroll=_atividade,
                daemon=True,
            )
            self._kb_listener = keyboard.Listener(
                on_press=_atividade,
                daemon=True,
            )
            self._mouse_listener.start()
            self._kb_listener.start()
            self._ativo = True
            return True
        except Exception as e:
            print(f"[ActivityMonitor] Falha ao iniciar: {e}")
            return False

    def parar(self):
        try:
            if self._mouse_listener:
                self._mouse_listener.stop()
            if self._kb_listener:
                self._kb_listener.stop()
        except Exception:
            pass
        self._ativo = False

    @property
    def segundos_inativo(self) -> float:
        with self._lock:
            return time.time() - self._ultimo

    @property
    def esta_ativo(self) -> bool:
        return self._ativo


if __name__ == "__main__":
    print("Módulo carregado com sucesso.")
