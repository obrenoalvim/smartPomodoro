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


# ─── TimerEngine ──────────────────────────────────────────────────────────────
class TimerEngine:
    """
    Máquina de estados do timer. Roda em thread separada.
    Callbacks chamados na thread do engine — usar root.after() para UI.
    """

    def __init__(self, config: ConfigManager, monitor: ActivityMonitor):
        self._cfg = config
        self._monitor = monitor
        self._estado = Estado.FOCO
        self._estado_anterior = Estado.FOCO
        self._thread = None
        self._stop_evt = threading.Event()
        self._pause_evt = threading.Event()
        self._pause_evt.set()  # começa não-pausado

        self._segundos_restantes = 0
        self._segundos_extra = 0
        self._lock = threading.Lock()

        # Callbacks (atribuídos pela PomodoroApp)
        self.on_tick = None            # (estado, seg_restantes, seg_extra)
        self.on_inicio_extensao = None # ()
        self.on_notificar_descanso = None  # (seg_extra)
        self.on_fim_descanso = None    # ()

    # ── Propriedades ──────────────────────────────────────────────────────────
    @property
    def estado(self):
        with self._lock:
            return self._estado

    @property
    def segundos_restantes(self):
        with self._lock:
            return self._segundos_restantes

    @property
    def segundos_extra(self):
        with self._lock:
            return self._segundos_extra

    # ── Controle ──────────────────────────────────────────────────────────────
    def iniciar_foco(self):
        self._parar_thread()
        with self._lock:
            self._estado = Estado.FOCO
            self._segundos_restantes = int(self._cfg.get("foco_minutos") * 60)
            self._segundos_extra = 0
        self._stop_evt.clear()
        self._pause_evt.set()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def pausar(self):
        with self._lock:
            if self._estado in (Estado.FOCO, Estado.EXTENSAO, Estado.DESCANSO):
                self._estado_anterior = self._estado
                self._pause_evt.clear()
                self._estado = Estado.PAUSADO

    def retomar(self):
        with self._lock:
            if self._estado == Estado.PAUSADO:
                self._estado = self._estado_anterior
        self._pause_evt.set()

    def resetar(self):
        self._parar_thread()
        with self._lock:
            self._estado = Estado.FOCO
            self._segundos_restantes = int(self._cfg.get("foco_minutos") * 60)
            self._segundos_extra = 0

    def iniciar_descanso(self, segundos_extra):
        self._parar_thread()
        bonus = int(segundos_extra * self._cfg.get("fator_bonus"))
        base  = int(self._cfg.get("descanso_base_minutos") * 60)
        with self._lock:
            self._estado = Estado.DESCANSO
            self._segundos_restantes = base + bonus
            self._segundos_extra = 0
        self._stop_evt.clear()
        self._pause_evt.set()
        self._thread = threading.Thread(target=self._loop_descanso, daemon=True)
        self._thread.start()

    def _parar_thread(self):
        self._stop_evt.set()
        self._pause_evt.set()  # desbloqueia se pausado
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    # ── Loop principal (FOCO → EXTENSAO) ──────────────────────────────────────
    def _loop(self):
        inatividade_limite = self._cfg.get("inatividade_segundos")

        # Fase FOCO: contagem regressiva
        while not self._stop_evt.is_set():
            self._pause_evt.wait()
            if self._stop_evt.is_set():
                break
            with self._lock:
                if self._segundos_restantes <= 0:
                    break
                self._segundos_restantes -= 1
                snap_estado = self._estado
                snap_rest   = self._segundos_restantes
                snap_extra  = self._segundos_extra
            if self.on_tick:
                self.on_tick(snap_estado, snap_rest, snap_extra)
            self._stop_evt.wait(1)

        if self._stop_evt.is_set():
            return

        # Timer zerou — verificar atividade
        inativo = self._monitor.segundos_inativo
        if inativo >= inatividade_limite:
            # Já estava inativo — notificar imediatamente
            if self.on_notificar_descanso:
                self.on_notificar_descanso(0)
            return

        # Usuário ativo → EXTENSAO silenciosa
        with self._lock:
            self._estado = Estado.EXTENSAO
            self._estado_anterior = Estado.EXTENSAO
        if self.on_inicio_extensao:
            self.on_inicio_extensao()

        while not self._stop_evt.is_set():
            self._pause_evt.wait()
            if self._stop_evt.is_set():
                break
            with self._lock:
                self._segundos_extra += 1
                snap_estado = self._estado
                snap_rest   = self._segundos_restantes
                snap_extra  = self._segundos_extra
            if self.on_tick:
                self.on_tick(snap_estado, snap_rest, snap_extra)

            inativo = self._monitor.segundos_inativo
            if inativo >= inatividade_limite:
                # Usuário parou — notificar
                with self._lock:
                    seg_extra = self._segundos_extra
                if self.on_notificar_descanso:
                    self.on_notificar_descanso(seg_extra)
                return

            self._stop_evt.wait(1)

    # ── Loop descanso ─────────────────────────────────────────────────────────
    def _loop_descanso(self):
        while not self._stop_evt.is_set():
            self._pause_evt.wait()
            if self._stop_evt.is_set():
                break
            with self._lock:
                if self._segundos_restantes <= 0:
                    break
                self._segundos_restantes -= 1
                snap_estado = self._estado
                snap_rest   = self._segundos_restantes
                snap_extra  = self._segundos_extra
            if self.on_tick:
                self.on_tick(snap_estado, snap_rest, snap_extra)
            self._stop_evt.wait(1)

        if self._stop_evt.is_set():
            return
        if self.on_fim_descanso:
            self.on_fim_descanso()


if __name__ == "__main__":
    print("Módulo carregado com sucesso.")
