#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pomodoro Inteligente - Windows
Detecta atividade real de mouse/teclado para não interromper o usuário.
Requer: pip install pynput pystray Pillow
"""

import os
import sys
import json
import time
import enum
import threading
import tkinter as tk
from tkinter import messagebox
import sqlite3
import statistics
from datetime import date, datetime, timedelta

def _resource(rel):
    """Resolve caminho de recurso — dev ou bundle PyInstaller."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)
try:
    import winsound
    WINSOUND_OK = True
except ImportError:
    WINSOUND_OK = False

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
DB_PATH = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "PomodoroInteligente",
    "sessions.db"
)
CONFIG_DEFAULT = {
    "foco_minutos": 25,
    "descanso_base_minutos": 5,
    "fator_bonus": 0.25,
    "inatividade_segundos": 8,
    "som_ativado": True,
    "minimizar_para_tray": True,
}
COR_BG       = "#1C1C1E"
COR_SURFACE  = "#2C2C2E"
COR_BORDER   = "#3A3A3C"
COR_FG       = "#EBEBF5"
COR_FG2      = "#8E8E93"
COR_FOCO     = "#0A84FF"
COR_EXTENSAO = "#FF9F0A"
COR_DESCANSO = "#30D158"
COR_PAUSADO  = "#636366"

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


# ─── SessionStore ─────────────────────────────────────────────────────────────
class SessionStore:
    """Persiste sessões em SQLite para cálculo de estatísticas de foco."""

    def __init__(self, db_path=DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._db = db_path
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self._db)

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at      TEXT NOT NULL,
                    configured_mins REAL NOT NULL,
                    focus_mins      REAL NOT NULL DEFAULT 0,
                    extension_mins  REAL NOT NULL DEFAULT 0,
                    completed       INTEGER NOT NULL DEFAULT 0
                )
            """)

    def record_start(self, configured_mins) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO sessions (started_at, configured_mins) VALUES (?, ?)",
                (datetime.utcnow().isoformat(), float(configured_mins)),
            )
            return cur.lastrowid

    def record_end(self, session_id, focus_mins, extension_mins):
        with self._conn() as conn:
            conn.execute(
                "UPDATE sessions SET focus_mins=?, extension_mins=?, completed=1 WHERE id=?",
                (float(focus_mins), float(extension_mins), session_id),
            )

    def record_abandon(self, session_id):
        with self._conn() as conn:
            conn.execute(
                "UPDATE sessions SET completed=0 WHERE id=?",
                (session_id,),
            )

    def get_stats(self) -> dict:
        empty = {
            "avg_real_focus": 0.0,
            "avg_extension":  0.0,
            "total_sessions": 0,
            "sessions_today": 0,
            "streak_days":    0,
            "last_7_days":    [],
            "suggestion_mins": None,
        }
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT configured_mins, focus_mins, extension_mins, started_at "
                "FROM sessions WHERE completed=1 ORDER BY started_at"
            ).fetchall()

        if not rows:
            return empty

        real_focus_vals = [r[1] + r[2] for r in rows]
        avg_real = statistics.mean(real_focus_vals)
        avg_ext  = statistics.mean(r[2] for r in rows)
        total    = len(rows)

        today_str      = date.today().isoformat()
        sessions_today = sum(1 for r in rows if r[3].startswith(today_str))

        # consecutive-day streak ending today
        dates  = sorted(set(r[3][:10] for r in rows))
        streak = 0
        check  = date.today()
        for _ in range(len(dates) + 1):
            if check.isoformat() in dates:
                streak += 1
                check -= timedelta(days=1)
            else:
                break

        # last 7 calendar days → [("DD", count), ...]
        last_7 = []
        for i in range(6, -1, -1):
            d     = (date.today() - timedelta(days=i)).isoformat()
            count = sum(1 for r in rows if r[3].startswith(d))
            last_7.append((d[8:], count))

        # calibration suggestion: nearest 5 min, only if diverges >2 min
        last_configured = rows[-1][0]
        suggestion = None
        if abs(avg_real - last_configured) > 2:
            suggestion = max(1, round(avg_real / 5) * 5)

        return {
            "avg_real_focus": avg_real,
            "avg_extension":  avg_ext,
            "total_sessions": total,
            "sessions_today": sessions_today,
            "streak_days":    streak,
            "last_7_days":    last_7,
            "suggestion_mins": suggestion,
        }


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
            pystray.MenuItem("Mostrar / Ocultar", lambda: self._app.after(0, self._app.toggle_janela)),
            pystray.MenuItem("Pausar / Retomar",  lambda: self._app.after(0, self._app.toggle_pausa)),
            pystray.MenuItem("Resetar",            lambda: self._app.after(0, self._app.resetar)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sair",               lambda: self._app.after(0, self._app.sair)),
        )

    def iniciar(self):
        if not PYSTRAY_OK:
            return
        img = self._criar_imagem(COR_FOCO)
        menu = self._criar_menu()
        self._tray = pystray.Icon(APP_NAME, img, APP_NAME, menu)
        self._tray.on_double_click = lambda _icon, _btn: self._app.after(0, self._app.toggle_janela)

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
        self.title("Pomodoro")
        self.configure(bg=COR_BG)
        self.geometry("280x340")

        # Titlebar
        bar = tk.Frame(self, bg=COR_SURFACE, height=36)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text="Hora de descansar",
                 font=("Segoe UI", 9, "bold"),
                 bg=COR_SURFACE, fg=COR_FG2).pack(expand=True)
        tk.Frame(self, bg=COR_BORDER, height=1).pack(fill="x")

        body = tk.Frame(self, bg=COR_BG)
        body.pack(fill="both", expand=True, padx=14, pady=(10, 14))

        tk.Label(body, text="🎉", font=("Segoe UI", 22),
                 bg=COR_BG).pack()
        tk.Label(body, text="Ótimo trabalho!",
                 font=("Segoe UI", 12, "bold"),
                 bg=COR_BG, fg=COR_FG).pack(pady=(2, 0))

        foco_min = seg_extra // 60
        foco_seg = seg_extra % 60
        info = (f"{self._cfg.get('foco_minutos')} min foco\n"
                f"+ {foco_min}m{foco_seg:02d}s extra")
        tk.Label(body, text=info, font=("Segoe UI", 9),
                 bg=COR_BG, fg=COR_FG2, justify="center").pack(pady=(2, 8))

        self._canvas = tk.Canvas(body, width=160, height=120,
                                  bg=COR_BG, highlightthickness=0)
        self._canvas.pack()
        self._desenhar_mini_anel(self._total)

        tk.Button(body, text="Começar descanso",
                  font=("Segoe UI", 10, "bold"),
                  bg=COR_DESCANSO, fg="white", relief="flat", bd=0,
                  activebackground="#28b84e", activeforeground="white",
                  command=self._iniciar).pack(fill="x", ipady=7, pady=(10, 5))

        tk.Button(body, text="Pular",
                  font=("Segoe UI", 9),
                  bg=COR_BG, fg=COR_PAUSADO, relief="flat", bd=0,
                  highlightbackground=COR_BORDER, highlightthickness=1,
                  activebackground=COR_BORDER, activeforeground=COR_FG,
                  command=self._pular).pack(fill="x", ipady=5)

    def _desenhar_mini_anel(self, restante):
        pct = (restante / self._total) if self._total else 0
        cx, cy, r, w = 80, 60, 48, 7

        self._canvas.delete("all")

        self._canvas.create_arc(
            cx - r, cy - r, cx + r, cy + r,
            start=90, extent=-359.9, style="arc",
            outline=COR_BORDER, width=w,
        )

        extent = -max(int(pct * 359.9), 1) if pct > 0 else 0
        if extent:
            self._canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=90, extent=extent, style="arc",
                outline=COR_DESCANSO, width=w,
            )

        self._canvas.create_text(cx, cy - 16, text="DESCANSO",
                                  font=("Segoe UI", 7, "bold"),
                                  fill=COR_DESCANSO)
        self._canvas.create_text(cx, cy + 8, text=self._fmt(restante),
                                  font=("Segoe UI", 20),
                                  fill="#FFFFFF")

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
            self._desenhar_mini_anel(self._restante)
            self.after(1000, self._tick)
        else:
            self._concluir()

    def _concluir(self):
        self._rodando = False
        self._desenhar_mini_anel(0)
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
        self._store = SessionStore()
        self._session_id: int | None = None
        self._stats_visivel = False
        self._suggestion_visible = False
        self._suggestion_mins: int | None = None

        self._configurar_janela()
        self._construir_ui()
        self._ligar_engine()
        self._monitor.iniciar()
        self._tray.iniciar()
        self._engine.iniciar_foco()
        self._session_id = self._store.record_start(self._cfg.get("foco_minutos"))
        self._atualizar_ui_loop()

        if not PYNPUT_OK:
            messagebox.showwarning(
                APP_NAME,
                "pynput não instalado. Detecção de atividade desabilitada.\n"
                "pip install pynput"
            )

    # ── Janela ────────────────────────────────────────────────────────────────
    def _configurar_janela(self):
        self.title(APP_NAME)
        self.geometry("300x340")
        self.resizable(False, False)
        self.configure(bg=COR_BG)
        self.protocol("WM_DELETE_WINDOW", self._ao_fechar)
        try:
            self.iconbitmap(_resource("pomodoro.ico"))
        except Exception:
            pass

    def _ao_fechar(self):
        self.sair()

    def toggle_janela(self):
        if self.winfo_viewable():
            self.withdraw()
        else:
            self.deiconify()
            self.lift()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _construir_ui(self):
        # Titlebar
        bar = tk.Frame(self, bg=COR_SURFACE, height=36)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text=f"🍅 {APP_NAME}",
                 font=("Segoe UI", 9, "bold"),
                 bg=COR_SURFACE, fg=COR_FG2).pack(side="left", expand=True)
        self._btn_gear = tk.Button(
            bar, text="⚙", font=("Segoe UI", 12),
            bg=COR_SURFACE, fg=COR_FG2, relief="flat", bd=0,
            activebackground=COR_SURFACE, activeforeground=COR_FG,
            command=self._toggle_config, cursor="hand2",
        )
        self._btn_gear.pack(side="right", padx=8)
        self._btn_stats = tk.Button(
            bar, text="📊", font=("Segoe UI", 11),
            bg=COR_SURFACE, fg=COR_FG2, relief="flat", bd=0,
            activebackground=COR_SURFACE, activeforeground=COR_FG,
            command=self._toggle_stats, cursor="hand2",
        )
        self._btn_stats.pack(side="right", padx=(0, 4))
        tk.Frame(self, bg=COR_BORDER, height=1).pack(fill="x")

        # Ring canvas
        self._canvas = tk.Canvas(self, width=300, height=170,
                                  bg=COR_BG, highlightthickness=0)
        self._canvas.pack()

        # Buttons
        frame_btn = tk.Frame(self, bg=COR_BG)
        frame_btn.pack(pady=(0, 12), padx=14, fill="x")
        self._btn_pausar = tk.Button(
            frame_btn, text="Pausar",
            font=("Segoe UI", 9, "bold"),
            bg=COR_SURFACE, fg=COR_FG, relief="flat", bd=0,
            highlightbackground=COR_BORDER, highlightthickness=1,
            activebackground=COR_BORDER, activeforeground=COR_FG,
            command=self.toggle_pausa,
        )
        self._btn_pausar.pack(side="left", expand=True, fill="x",
                               padx=(0, 4), ipady=6)
        tk.Button(
            frame_btn, text="Resetar",
            font=("Segoe UI", 9, "bold"),
            bg=COR_SURFACE, fg=COR_FG, relief="flat", bd=0,
            highlightbackground=COR_BORDER, highlightthickness=1,
            activebackground=COR_BORDER, activeforeground=COR_FG,
            command=self.resetar,
        ).pack(side="left", expand=True, fill="x", padx=(4, 0), ipady=6)

        # Config frame (collapsible)
        self._config_visivel = False
        self._frame_cfg = tk.Frame(self, bg=COR_SURFACE,
                                    highlightbackground=COR_BORDER,
                                    highlightthickness=1)
        tk.Label(self._frame_cfg, text="CONFIGURAÇÕES",
                 font=("Segoe UI", 7, "bold"),
                 bg=COR_SURFACE, fg=COR_FG2).pack(anchor="w", padx=10, pady=(8, 4))

        self._vars_cfg = {}
        campos = [
            ("foco_minutos",          "Foco (min)"),
            ("descanso_base_minutos", "Descanso (min)"),
            ("inatividade_segundos",  "Inatividade (s)"),
            ("fator_bonus",           "Fator bônus"),
        ]
        for chave, label in campos:
            row = tk.Frame(self._frame_cfg, bg=COR_SURFACE)
            row.pack(fill="x", padx=10, pady=2)
            tk.Label(row, text=label, font=("Segoe UI", 9),
                     bg=COR_SURFACE, fg=COR_FG2).pack(side="left")
            var = tk.StringVar(value=str(self._cfg.get(chave)))
            self._vars_cfg[chave] = var
            entry = tk.Entry(row, textvariable=var, width=6,
                             font=("Segoe UI", 9), bg=COR_BORDER, fg=COR_FG,
                             insertbackground=COR_FG, relief="flat",
                             highlightthickness=0)
            entry.pack(side="right")
            entry.bind("<FocusOut>", lambda e, k=chave: self._salvar_campo(k))
            entry.bind("<Return>",   lambda e, k=chave: self._salvar_campo(k))
        tk.Frame(self._frame_cfg, bg=COR_SURFACE, height=8).pack()

        # Initial ring draw
        total = int(self._cfg.get("foco_minutos") * 60)
        self._desenhar_anel(Estado.FOCO, 1.0, self._fmt(total), "FOCO")
        self._construir_stats_panel()

    def _desenhar_anel(self, estado, pct, texto, chip_label):
        cores = {
            Estado.FOCO:     COR_FOCO,
            Estado.EXTENSAO: COR_EXTENSAO,
            Estado.DESCANSO: COR_DESCANSO,
            Estado.PAUSADO:  COR_PAUSADO,
        }
        cor = cores.get(estado, COR_PAUSADO)
        cx, cy, r, w = 150, 87, 68, 9

        self._canvas.delete("all")

        # Track (full grey ring)
        self._canvas.create_arc(
            cx - r, cy - r, cx + r, cy + r,
            start=90, extent=-359.9, style="arc",
            outline=COR_BORDER, width=w,
        )

        # Fill arc
        if estado == Estado.EXTENSAO:
            # Accumulating amber arc growing clockwise as extra seconds increase
            max_ext = 600
            ext_pct = min(pct / max_ext, 1.0) if max_ext > 0 else 0
            extent = -max(int(ext_pct * 359.9), 1) if pct > 0 else 0
            if extent:
                self._canvas.create_arc(
                    cx - r, cy - r, cx + r, cy + r,
                    start=90, extent=extent, style="arc",
                    outline=cor, width=w,
                )
        else:
            extent = -max(int(pct * 359.9), 1) if pct > 0 else 0
            if extent:
                self._canvas.create_arc(
                    cx - r, cy - r, cx + r, cy + r,
                    start=90, extent=extent, style="arc",
                    outline=cor, width=w,
                )

        # Chip label (state name)
        self._canvas.create_text(
            cx, cy - 24,
            text=chip_label,
            font=("Segoe UI", 8, "bold"),
            fill=cor,
        )

        # Timer number
        timer_y = cy + 4 if estado != Estado.EXTENSAO else cy
        self._canvas.create_text(
            cx, timer_y,
            text=texto,
            font=("Segoe UI", 28),
            fill="#FFFFFF",
        )

        # Sub-text only for extension state
        if estado == Estado.EXTENSAO:
            self._canvas.create_text(
                cx, cy + 26,
                text="além do foco",
                font=("Segoe UI", 8),
                fill=COR_EXTENSAO,
            )

    def _toggle_config(self):
        if self._config_visivel:
            self._frame_cfg.pack_forget()
            self._btn_gear.config(fg=COR_FG2)
        else:
            self._frame_cfg.pack(fill="x", padx=14, pady=(0, 4))
            # Re-pack stats after config to keep config-above-stats order
            if self._stats_visivel:
                self._frame_stats.pack_forget()
                self._frame_stats.pack(fill="x", padx=14, pady=(0, 14))
            self._btn_gear.config(fg=COR_FOCO)
        self._config_visivel = not self._config_visivel
        self._recalcular_altura()

    def _recalcular_altura(self):
        h = 340
        if self._config_visivel:
            h += 120
        if self._stats_visivel:
            h += 200
            if self._suggestion_visible:
                h += 80
        self.geometry(f"300x{h}")

    def _construir_stats_panel(self):
        self._frame_stats = tk.Frame(
            self, bg=COR_SURFACE,
            highlightbackground=COR_BORDER, highlightthickness=1,
        )

        tk.Label(self._frame_stats, text="📊 SUAS ESTATÍSTICAS",
                 font=("Segoe UI", 7, "bold"),
                 bg=COR_SURFACE, fg=COR_FG2).pack(anchor="w", padx=10, pady=(8, 4))

        def _row(label, color=COR_FG):
            row = tk.Frame(self._frame_stats, bg=COR_SURFACE)
            row.pack(fill="x", padx=10, pady=1)
            tk.Label(row, text=label, font=("Segoe UI", 9),
                     bg=COR_SURFACE, fg=COR_FG2).pack(side="left")
            lbl = tk.Label(row, text="—", font=("Segoe UI", 9, "bold"),
                           bg=COR_SURFACE, fg=color)
            lbl.pack(side="right")
            return lbl

        self._lbl_avg_focus = _row("Foco real médio", COR_FOCO)
        self._lbl_avg_ext   = _row("Extensão média",   COR_EXTENSAO)
        self._lbl_sessions  = _row("Sessões hoje / total")
        self._lbl_streak    = _row("Streak")

        self._canvas_chart = tk.Canvas(
            self._frame_stats, width=276, height=50,
            bg=COR_SURFACE, highlightthickness=0,
        )
        self._canvas_chart.pack(padx=10, pady=(6, 2))

        tk.Frame(self._frame_stats, bg=COR_BORDER, height=1).pack(fill="x", padx=10)

        # Suggestion area — packed only when suggestion_mins is not None
        self._frame_suggestion = tk.Frame(self._frame_stats, bg=COR_SURFACE)
        self._lbl_suggestion = tk.Label(
            self._frame_suggestion,
            text="", font=("Segoe UI", 8), wraplength=240, justify="left",
            bg="#1A2A3A", fg=COR_FG, padx=7, pady=5,
        )
        self._lbl_suggestion.pack(fill="x", padx=10, pady=(6, 4))
        self._btn_ajustar = tk.Button(
            self._frame_suggestion,
            text="", font=("Segoe UI", 9, "bold"),
            bg=COR_FOCO, fg="white", relief="flat", bd=0,
            activebackground="#0070E0", activeforeground="white",
            command=self._aplicar_sugestao,
        )
        self._btn_ajustar.pack(fill="x", padx=10, ipady=6, pady=(0, 6))

        tk.Frame(self._frame_stats, bg=COR_SURFACE, height=6).pack()

    def _toggle_stats(self):
        if self._stats_visivel:
            self._frame_stats.pack_forget()
            self._btn_stats.config(fg=COR_FG2)
        else:
            self._frame_stats.pack(fill="x", padx=14, pady=(0, 14))
            self._btn_stats.config(fg=COR_FOCO)
            self._atualizar_stats()
        self._stats_visivel = not self._stats_visivel
        self._recalcular_altura()

    def _desenhar_barras(self, last_7_days):
        c = self._canvas_chart
        c.delete("all")
        if not last_7_days:
            return
        max_count = max(count for _, count in last_7_days) or 1
        bar_w   = 28
        gap     = (276 - 7 * bar_w) // 8
        chart_h = 36

        for i, (day_label, count) in enumerate(last_7_days):
            x     = gap + i * (bar_w + gap)
            bar_h = max(int((count / max_count) * chart_h), 2) if count > 0 else 2
            y_top = chart_h + 2 - bar_h
            y_bot = chart_h + 2
            bar_color = "#4DA3FF" if i == 6 else COR_FOCO
            c.create_rectangle(x, y_top, x + bar_w, y_bot, fill=bar_color, outline="")
            c.create_text(x + bar_w // 2, 47,
                          text=day_label, font=("Segoe UI", 6), fill=COR_FG2)

    def _atualizar_stats(self):
        stats = self._store.get_stats()

        if stats["total_sessions"] > 0:
            self._lbl_avg_focus.config(text=f"{stats['avg_real_focus']:.0f} min")
            self._lbl_avg_ext.config(text=f"+{stats['avg_extension']:.0f} min")
        else:
            self._lbl_avg_focus.config(text="—")
            self._lbl_avg_ext.config(text="—")

        self._lbl_sessions.config(
            text=f"{stats['sessions_today']} / {stats['total_sessions']}"
        )
        streak = stats["streak_days"]
        self._lbl_streak.config(
            text=f"{streak} dias {'🔥' if streak >= 3 else ''}"
        )

        self._desenhar_barras(stats["last_7_days"])

        sug = stats["suggestion_mins"]
        if sug is not None:
            avg = stats["avg_real_focus"]
            self._lbl_suggestion.config(
                text=f"💡 Seu foco real é ~{avg:.0f}min. Considere ajustar para {sug}min."
            )
            self._btn_ajustar.config(text=f"Ajustar para {sug}min")
            self._suggestion_mins = sug
            if not self._suggestion_visible:
                self._frame_suggestion.pack(fill="x")
                self._suggestion_visible = True
                self._recalcular_altura()
        else:
            self._suggestion_mins = None
            if self._suggestion_visible:
                self._frame_suggestion.pack_forget()
                self._suggestion_visible = False
                self._recalcular_altura()

    def _aplicar_sugestao(self):
        if self._suggestion_mins is not None:
            self._vars_cfg["foco_minutos"].set(str(self._suggestion_mins))
            self._salvar_campo("foco_minutos")
            self._suggestion_mins = None
            if self._suggestion_visible:
                self._frame_suggestion.pack_forget()
                self._suggestion_visible = False
                self._recalcular_altura()

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
        self.after(0, self._mostrar_notificacao, seg_extra)

    def _cb_fim_descanso(self):
        self.after(0, self._fim_descanso)

    # ── Aplicadores de estado na UI (thread UI) ───────────────────────────────
    def _aplicar_tick(self, estado, seg_rest, seg_extra):
        labels = {
            Estado.FOCO:     "FOCO",
            Estado.EXTENSAO: "⚡ EXTRA",
            Estado.DESCANSO: "DESCANSO",
            Estado.PAUSADO:  "PAUSADO",
        }
        chip = labels.get(estado, "")

        if estado in (Estado.FOCO, Estado.PAUSADO):
            total = int(self._cfg.get("foco_minutos") * 60)
            pct = (seg_rest / total) if total else 0
            self._desenhar_anel(estado, pct, self._fmt(seg_rest), chip)
        elif estado == Estado.EXTENSAO:
            self._desenhar_anel(estado, seg_extra, self._fmt(seg_extra), chip)
        elif estado == Estado.DESCANSO:
            total = int(
                self._cfg.get("descanso_base_minutos") * 60
                + int(self._seg_extra_snapshot * self._cfg.get("fator_bonus"))
            )
            pct = (seg_rest / total) if total else 0
            self._desenhar_anel(estado, pct, self._fmt(seg_rest), chip)

        tooltip = f"{chip}: {self._fmt(seg_extra if estado == Estado.EXTENSAO else seg_rest)}"
        self._tray.atualizar(estado, tooltip)

    def _aplicar_extensao(self):
        pass  # next tick redraws ring with EXTENSAO state

    def _mostrar_notificacao(self, seg_extra):
        if self._session_id is not None:
            self._store.record_end(
                self._session_id,
                self._cfg.get("foco_minutos"),
                seg_extra / 60,
            )
            self._session_id = None
            if self._stats_visivel:
                self._atualizar_stats()
        self._seg_extra_snapshot = seg_extra
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
            self._btn_pausar.config(text="Pausar")
        elif estado in (Estado.FOCO, Estado.EXTENSAO, Estado.DESCANSO):
            self._engine.pausar()
            self._btn_pausar.config(text="Retomar")

    def resetar(self):
        if self._session_id is not None:
            self._store.record_abandon(self._session_id)
            self._session_id = None
        self._engine.resetar()
        self._engine.iniciar_foco()
        self._session_id = self._store.record_start(self._cfg.get("foco_minutos"))
        self._btn_pausar.config(text="Pausar")
        total = int(self._cfg.get("foco_minutos") * 60)
        self._desenhar_anel(Estado.FOCO, 1.0, self._fmt(total), "FOCO")

    def sair(self):
        if self._session_id is not None:
            self._store.record_abandon(self._session_id)
            self._session_id = None
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
            if WINSOUND_OK:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass

    def _atualizar_ui_loop(self):
        if not self.winfo_exists():
            return
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
