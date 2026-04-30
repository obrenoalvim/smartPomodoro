#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pomodoro Inteligente - Linux/Ubuntu
Detecta atividade real de mouse/teclado para não interromper o usuário.
Requer: pip install pynput pystray Pillow
        sudo apt install python3-tk  (Ubuntu)

Permissões pynput (se não funcionar):
    sudo usermod -aG input $USER   (logout/login necessário)
    ou: sudo python3 pomodoro_linux.py
"""

import os
import json
import time
import enum
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox

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
CONFIG_PATH = os.path.expanduser("~/.config/pomodoro_inteligente/config.json")
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
        except PermissionError:
            print(
                "[ActivityMonitor] Sem permissão. Execute:\n"
                "  sudo usermod -aG input $USER\n"
                "  (logout e login novamente)\n"
                "  ou rode com: sudo python3 pomodoro_linux.py"
            )
            return False
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


# ─── TrayManager ──────────────────────────────────────────────────────────────
class TrayManager:
    """Gerencia o ícone na bandeja do sistema (system tray)."""

    def __init__(self, app_ref):
        self._app = app_ref  # referência à PomodoroApp
        self._tray = None
        self._thread = None

    def _criar_imagem(self, cor, tamanho=64):
        img  = Image.new("RGBA", (tamanho, tamanho), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, tamanho - 4, tamanho - 4], fill=cor)
        return img

    def _criar_menu(self):
        return pystray.Menu(
            pystray.MenuItem("Mostrar / Ocultar", lambda: self._app.toggle_janela()),
            pystray.MenuItem("Pausar / Retomar",  lambda: self._app.toggle_pausa()),
            pystray.MenuItem("Resetar",            lambda: self._app.resetar()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sair",               lambda: self._app.sair()),
        )

    def iniciar(self):
        if not PYSTRAY_OK:
            return
        img = self._criar_imagem(COR_FOCO)
        menu = self._criar_menu()
        self._tray = pystray.Icon(APP_NAME, img, APP_NAME, menu)
        self._tray.on_double_click = lambda _icon, _btn: self._app.toggle_janela()

        self._thread = threading.Thread(target=self._tray.run, daemon=True)
        self._thread.start()

    def atualizar(self, estado, texto_tooltip):
        if not self._tray:
            return
        cores = {
            Estado.FOCO:     COR_FOCO,
            Estado.EXTENSAO: COR_EXTENSAO,
            Estado.DESCANSO: COR_DESCANSO,
            Estado.PAUSADO:  COR_PAUSADO,
        }
        cor = cores.get(estado, COR_PAUSADO)
        try:
            self._tray.icon  = self._criar_imagem(cor)
            self._tray.title = f"{APP_NAME} - {texto_tooltip}"
        except Exception:
            pass

    def parar(self):
        try:
            if self._tray:
                self._tray.stop()
        except Exception:
            pass


# ─── NotificationWindow ───────────────────────────────────────────────────────
class NotificationWindow(tk.Toplevel):
    """
    Janela de descanso. Aparece na frente de tudo, centralizada.
    Exibe tempo de descanso calculado e timer countdown.
    """

    def __init__(self, parent, segundos_extra, config,
                 on_iniciar_descanso, on_pular):
        super().__init__(parent)
        self._cfg = config
        self._on_iniciar_descanso = on_iniciar_descanso
        self._on_pular = on_pular

        bonus_seg   = int(segundos_extra * config.get("fator_bonus"))
        base_seg    = int(config.get("descanso_base_minutos") * 60)
        self._total = base_seg + bonus_seg
        self._restante = self._total
        self._rodando  = False
        self._seg_extra = segundos_extra

        self._construir_ui(segundos_extra, bonus_seg, base_seg)
        self._centralizar()
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._pular)

    def _fmt(self, s):
        return f"{s // 60:02d}:{s % 60:02d}"

    def _construir_ui(self, seg_extra, bonus_seg, base_seg):
        self.title("Hora de descansar!")
        self.configure(bg=COR_BG)

        pad = {"padx": 20, "pady": 8}

        tk.Label(self, text="🎉 Ótimo trabalho!", font=("Segoe UI", 16, "bold"),
                 bg=COR_BG, fg=COR_FG).pack(**pad)

        foco_min  = seg_extra // 60
        foco_seg  = seg_extra % 60
        bonus_min = bonus_seg // 60
        bonus_sec = bonus_seg % 60
        base_min  = base_seg  // 60

        info = (
            f"Você trabalhou:\n"
            f"  {self._cfg.get('foco_minutos')} min + "
            f"{foco_min}m{foco_seg:02d}s extras"
        )
        tk.Label(self, text=info, font=("Segoe UI", 11),
                 bg=COR_BG, fg=COR_FG, justify="left").pack(**pad)

        tk.Label(self, text="Tempo de descanso:", font=("Segoe UI", 11),
                 bg=COR_BG, fg=COR_FG).pack(pady=(12, 2))

        self._prog = ttk.Progressbar(self, length=240, maximum=self._total,
                                     value=self._total, mode="determinate")
        self._prog.pack(padx=20, pady=4)

        self._lbl_timer = tk.Label(self, text=self._fmt(self._total),
                                   font=("Segoe UI", 28, "bold"),
                                   bg=COR_BG, fg=COR_DESCANSO)
        self._lbl_timer.pack(**pad)

        detalhe = (
            f"({base_min} min base + "
            f"{bonus_min}m{bonus_sec:02d}s bônus)"
        )
        tk.Label(self, text=detalhe, font=("Segoe UI", 9),
                 bg=COR_BG, fg="#888").pack(pady=(0, 12))

        tk.Button(self, text="  Começar descanso  ", font=("Segoe UI", 11),
                  bg=COR_DESCANSO, fg="white", relief="flat",
                  command=self._iniciar).pack(padx=20, pady=4, fill="x")

        tk.Button(self, text="Pular", font=("Segoe UI", 10),
                  bg="#333", fg=COR_FG, relief="flat",
                  command=self._pular).pack(padx=20, pady=(0, 16), fill="x")

    def _centralizar(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"+{x}+{y}")

    def _iniciar(self):
        if not self._rodando:
            self._rodando = True
            self._tick()
            self._on_iniciar_descanso(self._seg_extra)

    def _tick(self):
        if not self._rodando or not self.winfo_exists():
            return
        if self._restante > 0:
            self._restante -= 1
            self._lbl_timer.config(text=self._fmt(self._restante))
            self._prog.config(value=self._restante)
            self.after(1000, self._tick)
        else:
            self._concluir()

    def _concluir(self):
        self._rodando = False
        self._lbl_timer.config(text="00:00", fg=COR_FOCO)
        messagebox.showinfo("Pomodoro", "Pronto para focar novamente! 🍅",
                            parent=self)
        self.destroy()

    def _pular(self):
        self._rodando = False
        self._on_pular()
        self.destroy()


# ─── PomodoroApp ──────────────────────────────────────────────────────────────
class PomodoroApp(tk.Tk):
    """Janela principal. Orquestra todas as classes."""

    def __init__(self):
        super().__init__()
        self._cfg     = ConfigManager()
        self._monitor = ActivityMonitor()
        self._engine  = TimerEngine(self._cfg, self._monitor)
        self._tray    = TrayManager(self)
        self._notif_win = None
        self._seg_extra_snapshot = 0

        self._configurar_janela()
        self._construir_ui()
        self._ligar_engine()
        self._monitor.iniciar()
        self._tray.iniciar()
        self._engine.iniciar_foco()
        self._atualizar_ui_loop()

        if not PYNPUT_OK:
            messagebox.showwarning(
                APP_NAME,
                "pynput não instalado. Detecção de atividade desabilitada.\n"
                "pip install pynput\n\n"
                "Se tiver erro de permissão:\n"
                "sudo usermod -aG input $USER"
            )

    # ── Janela ────────────────────────────────────────────────────────────────
    def _configurar_janela(self):
        self.title(APP_NAME)
        self.geometry("320x420")
        self.resizable(False, False)
        self.configure(bg=COR_BG)
        self.protocol("WM_DELETE_WINDOW", self._ao_fechar)

    def _ao_fechar(self):
        if self._cfg.get("minimizar_para_tray") and PYSTRAY_OK:
            self.withdraw()
        else:
            resp = messagebox.askyesno(APP_NAME, "Deseja fechar o Pomodoro?")
            if resp:
                self.sair()

    def toggle_janela(self):
        if self.winfo_viewable():
            self.withdraw()
        else:
            self.deiconify()
            self.lift()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _construir_ui(self):
        tk.Label(self, text=f"🍅 {APP_NAME}", font=("Segoe UI", 13, "bold"),
                 bg=COR_BG, fg=COR_FG).pack(pady=(12, 4))

        self._frame_timer = tk.Frame(self, bg=COR_BG, bd=2, relief="groove")
        self._frame_timer.pack(fill="x", padx=16, pady=8)

        self._lbl_estado = tk.Label(self._frame_timer, text="FOCO",
                                    font=("Segoe UI", 11, "bold"),
                                    bg=COR_BG, fg=COR_FOCO)
        self._lbl_estado.pack(pady=(10, 2))

        self._lbl_tempo = tk.Label(self._frame_timer, text="25:00",
                                   font=("Segoe UI", 36, "bold"),
                                   bg=COR_BG, fg=COR_FOCO)
        self._lbl_tempo.pack()

        self._prog = ttk.Progressbar(self._frame_timer, length=260,
                                     maximum=100, value=100,
                                     mode="determinate")
        self._prog.pack(pady=(4, 8), padx=12)

        self._lbl_extra = tk.Label(self._frame_timer, text="",
                                   font=("Segoe UI", 9),
                                   bg=COR_BG, fg=COR_EXTENSAO)
        self._lbl_extra.pack(pady=(0, 8))

        frame_btn = tk.Frame(self, bg=COR_BG)
        frame_btn.pack(pady=4)
        self._btn_pausar = tk.Button(frame_btn, text="  Pausar  ",
                                     font=("Segoe UI", 10),
                                     bg="#333", fg=COR_FG, relief="flat",
                                     command=self.toggle_pausa)
        self._btn_pausar.pack(side="left", padx=6)
        tk.Button(frame_btn, text="  Resetar  ", font=("Segoe UI", 10),
                  bg="#333", fg=COR_FG, relief="flat",
                  command=self.resetar).pack(side="left", padx=6)

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=16, pady=8)

        tk.Label(self, text="Configurações", font=("Segoe UI", 10, "bold"),
                 bg=COR_BG, fg=COR_FG).pack(anchor="w", padx=16)

        self._vars_cfg = {}
        campos = [
            ("foco_minutos",          "Foco (min):"),
            ("descanso_base_minutos", "Descanso (min):"),
            ("fator_bonus",           "Fator bônus:"),
            ("inatividade_segundos",  "Inatividade (s):"),
        ]
        frame_cfg = tk.Frame(self, bg=COR_BG)
        frame_cfg.pack(fill="x", padx=16, pady=4)

        for chave, label in campos:
            row = tk.Frame(frame_cfg, bg=COR_BG)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, font=("Segoe UI", 9),
                     bg=COR_BG, fg=COR_FG, width=18, anchor="w").pack(side="left")
            var = tk.StringVar(value=str(self._cfg.get(chave)))
            self._vars_cfg[chave] = var
            entry = tk.Entry(row, textvariable=var, width=7,
                             font=("Segoe UI", 9), bg="#333", fg=COR_FG,
                             insertbackground=COR_FG, relief="flat")
            entry.pack(side="left")
            entry.bind("<FocusOut>", lambda e, k=chave: self._salvar_campo(k))
            entry.bind("<Return>",   lambda e, k=chave: self._salvar_campo(k))

    def _salvar_campo(self, chave):
        try:
            raw = self._vars_cfg[chave].get()
            val = float(raw) if "." in raw else int(raw)
            self._cfg.set(chave, val)
        except ValueError:
            self._vars_cfg[chave].set(str(self._cfg.get(chave)))

    # ── Engine callbacks ──────────────────────────────────────────────────────
    def _ligar_engine(self):
        self._engine.on_tick               = self._cb_tick
        self._engine.on_inicio_extensao    = self._cb_extensao
        self._engine.on_notificar_descanso = self._cb_notificar_descanso
        self._engine.on_fim_descanso       = self._cb_fim_descanso

    def _cb_tick(self, estado, seg_rest, seg_extra):
        self.after(0, self._aplicar_tick, estado, seg_rest, seg_extra)

    def _cb_extensao(self):
        self.after(0, self._aplicar_extensao)

    def _cb_notificar_descanso(self, seg_extra):
        self._seg_extra_snapshot = seg_extra
        self.after(0, self._mostrar_notificacao, seg_extra)

    def _cb_fim_descanso(self):
        self.after(0, self._fim_descanso)

    # ── Aplicadores de estado na UI (thread UI) ───────────────────────────────
    def _aplicar_tick(self, estado, seg_rest, seg_extra):
        cores = {
            Estado.FOCO:     COR_FOCO,
            Estado.EXTENSAO: COR_EXTENSAO,
            Estado.DESCANSO: COR_DESCANSO,
            Estado.PAUSADO:  COR_PAUSADO,
        }
        labels = {
            Estado.FOCO:     "FOCO",
            Estado.EXTENSAO: "⚡ EXTENDENDO",
            Estado.DESCANSO: "DESCANSO",
            Estado.PAUSADO:  "PAUSADO",
        }
        cor   = cores.get(estado, COR_PAUSADO)
        label = labels.get(estado, "")

        self._lbl_estado.config(text=label, fg=cor)
        self._lbl_tempo.config(fg=cor)
        self._frame_timer.config(highlightbackground=cor, highlightthickness=2)

        if estado in (Estado.FOCO, Estado.PAUSADO):
            total = int(self._cfg.get("foco_minutos") * 60)
            pct   = (seg_rest / total * 100) if total else 0
            self._lbl_tempo.config(text=self._fmt(seg_rest))
            self._prog.config(value=pct)
            self._lbl_extra.config(text="")
        elif estado == Estado.EXTENSAO:
            self._lbl_tempo.config(text=self._fmt(seg_extra))
            self._prog.config(value=100)
            self._lbl_extra.config(text=f"⚡ +{self._fmt(seg_extra)} extra")
        elif estado == Estado.DESCANSO:
            total = int((self._cfg.get("descanso_base_minutos") * 60) +
                         int(self._seg_extra_snapshot * self._cfg.get("fator_bonus")))
            pct   = (seg_rest / total * 100) if total else 0
            self._lbl_tempo.config(text=self._fmt(seg_rest))
            self._prog.config(value=pct)
            self._lbl_extra.config(text="")

        tooltip = f"{label}: {self._fmt(seg_extra if estado == Estado.EXTENSAO else seg_rest)}"
        self._tray.atualizar(estado, tooltip)

    def _aplicar_extensao(self):
        self._lbl_estado.config(text="⚡ EXTENDENDO", fg=COR_EXTENSAO)
        self._lbl_tempo.config(fg=COR_EXTENSAO)

    def _mostrar_notificacao(self, seg_extra):
        self._tocar_som()
        if self._notif_win and self._notif_win.winfo_exists():
            return
        self._notif_win = NotificationWindow(
            self,
            seg_extra,
            self._cfg,
            on_iniciar_descanso=self._iniciar_descanso_engine,
            on_pular=self.resetar,
        )

    def _iniciar_descanso_engine(self, seg_extra):
        self._seg_extra_snapshot = seg_extra
        self._engine.iniciar_descanso(seg_extra)

    def _fim_descanso(self):
        self._tocar_som()
        self.resetar()

    # ── Controles públicos ────────────────────────────────────────────────────
    def toggle_pausa(self):
        estado = self._engine.estado
        if estado == Estado.PAUSADO:
            self._engine.retomar()
            self._btn_pausar.config(text="  Pausar  ")
        elif estado in (Estado.FOCO, Estado.EXTENSAO, Estado.DESCANSO):
            self._engine.pausar()
            self._btn_pausar.config(text="  Retomar  ")

    def resetar(self):
        self._engine.resetar()
        self._engine.iniciar_foco()
        self._btn_pausar.config(text="  Pausar  ")
        self._lbl_tempo.config(
            text=self._fmt(int(self._cfg.get("foco_minutos") * 60)),
            fg=COR_FOCO
        )
        self._lbl_estado.config(text="FOCO", fg=COR_FOCO)
        self._lbl_extra.config(text="")

    def sair(self):
        self._engine.resetar()
        self._monitor.parar()
        self._tray.parar()
        self.destroy()

    # ── Utilitários ───────────────────────────────────────────────────────────
    @staticmethod
    def _fmt(s):
        return f"{s // 60:02d}:{s % 60:02d}"

    def _tocar_som(self):
        if not self._cfg.get("som_ativado"):
            return
        try:
            cmd = None
            if shutil.which("paplay"):
                cmd = ["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"]
            elif shutil.which("aplay"):
                cmd = ["aplay", "/usr/share/sounds/alsa/Front_Center.wav"]
            if cmd:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def _atualizar_ui_loop(self):
        self.after(500, self._atualizar_ui_loop)


# ─── TESTE RÁPIDO ─────────────────────────────────────────────────────────────
# Para validar o fluxo completo sem esperar 25 minutos:
#
#   1. Abra o app normalmente
#   2. No campo "Foco (min):" coloque 0.1  (= 6 segundos)
#   3. No campo "Inatividade (s):" coloque 3
#   4. Clique fora do campo para salvar
#   5. Clique "Resetar"
#   6. Aguarde 6s → timer zera
#   7. Mexa o mouse → modo EXTENSAO (ícone laranja)
#   8. Pare de mexer por 3s → janela de descanso aparece
#   9. Clique "Começar descanso" → timer de descanso inicia
#  10. Aguarde o descanso terminar → volta ao foco


if __name__ == "__main__":
    app = PomodoroApp()
    app.mainloop()
