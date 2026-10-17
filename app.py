import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Dict, Any, Optional
from core import (
    StudioCore,
    SCENE_TYPE_LABELS,
    STORYBOARD_PRESETS,
    PROJECTS_ROOT,
    APP_VERSION,
    GITHUB_REPO
)

# Палитра цветов один-в-один со студийным макетом
BG_CANVAS = "#020617"      # slate-950
BG_CARD = "#0f172a"        # slate-900
BG_INPUT = "#020617"       # slate-950
BG_BTN_SEC = "#1e293b"     # slate-800
BG_BTN_HOVER = "#334155"   # slate-700
BORDER_COLOR = "#1e293b"   # slate-800
TEXT_MAIN = "#f1f5f9"      # slate-100
TEXT_SUB = "#cbd5e1"       # slate-300
TEXT_MUTED = "#94a3b8"     # slate-400
BLUE_PRIMARY = "#2563eb"   # blue-600
EMERALD_BTN = "#059669"    # emerald-600
EMERALD_TEXT = "#34d399"   # emerald-400
ROSE_BTN = "#4c0519"       # rose-950
ROSE_TEXT = "#fecdd3"      # rose-200


class MusicVideoStudioApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"MusicVideoStudio v{APP_VERSION} — Локальная ИИ-студия музыкальных клипов")
        self.geometry("1400x900")
        self.minsize(1180, 780)
        self.configure(bg=BG_CANVAS)

        self._configure_dark_theme()

        self.core = StudioCore()
        self._selected_scene_id: int = 0
        self._latest_update_info: Optional[Dict[str, Any]] = None

        self._build_ui()
        self._load_state_into_ui()
        # Автоматическая проверка обновлений при запуске
        self.after(600, lambda: self.on_check_updates(silent_if_current=True))

    def _configure_dark_theme(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure(".", background=BG_CARD, foreground=TEXT_MAIN, font=("Segoe UI", 9))
        style.configure("Canvas.TFrame", background=BG_CANVAS)
        style.configure("Card.TFrame", background=BG_CARD, relief="solid", borderwidth=1)
        style.configure(
            "Card.TLabelframe",
            background=BG_CARD,
            foreground=TEXT_MAIN,
            bordercolor=BORDER_COLOR,
            darkcolor=BORDER_COLOR,
            lightcolor=BORDER_COLOR,
            relief="solid",
            borderwidth=1
        )
        style.configure(
            "Card.TLabelframe.Label",
            background=BG_CARD,
            foreground="#60a5fa",
            font=("Segoe UI", 10, "bold")
        )
        style.configure("TLabel", background=BG_CARD, foreground=TEXT_MAIN)
        style.configure("Muted.TLabel", background=BG_CARD, foreground=TEXT_MUTED, font=("Segoe UI", 8))
        style.configure("Emerald.TLabel", background=BG_CARD, foreground=EMERALD_TEXT, font=("Consolas", 9, "bold"))

        # Кнопки
        style.configure(
            "Secondary.TButton",
            background=BG_BTN_SEC,
            foreground=TEXT_MAIN,
            bordercolor=BORDER_COLOR,
            focuscolor=BG_BTN_SEC,
            padding=(10, 5),
            font=("Segoe UI", 9, "bold")
        )
        style.map(
            "Secondary.TButton",
            background=[("active", BG_BTN_HOVER), ("disabled", "#0f172a")],
            foreground=[("disabled", "#475569")]
        )

        style.configure(
            "Primary.TButton",
            background=BLUE_PRIMARY,
            foreground="#ffffff",
            bordercolor=BLUE_PRIMARY,
            focuscolor=BLUE_PRIMARY,
            padding=(10, 5),
            font=("Segoe UI", 9, "bold")
        )
        style.map("Primary.TButton", background=[("active", "#3b82f6"), ("disabled", "#1e293b")])

        style.configure(
            "Emerald.TButton",
            background=EMERALD_BTN,
            foreground="#ffffff",
            bordercolor=EMERALD_BTN,
            focuscolor=EMERALD_BTN,
            padding=(10, 5),
            font=("Segoe UI", 9, "bold")
        )
        style.map(
            "Emerald.TButton",
            background=[("active", "#10b981"), ("disabled", "#1e293b")],
            foreground=[("disabled", "#64748b")]
        )

        style.configure(
            "Rose.TButton",
            background=ROSE_BTN,
            foreground=ROSE_TEXT,
            bordercolor="#9f1239",
            focuscolor=ROSE_BTN,
            padding=(10, 5),
            font=("Segoe UI", 9, "bold")
        )
        style.map("Rose.TButton", background=[("active", "#881337")])

        # Поля ввода и выпадающие списки
        style.configure(
            "TEntry",
            fieldbackground=BG_INPUT,
            foreground=TEXT_MAIN,
            insertcolor=TEXT_MAIN,
            bordercolor=BORDER_COLOR,
            lightcolor=BORDER_COLOR,
            darkcolor=BORDER_COLOR,
            padding=5
        )
        style.configure(
            "TCombobox",
            fieldbackground=BG_INPUT,
            background=BG_BTN_SEC,
            foreground=TEXT_MAIN,
            arrowcolor=TEXT_MAIN,
            bordercolor=BORDER_COLOR,
            lightcolor=BORDER_COLOR,
            darkcolor=BORDER_COLOR,
            padding=4
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", BG_INPUT)],
            foreground=[("readonly", TEXT_MAIN)],
            selectbackground=[("readonly", BG_INPUT)],
            selectforeground=[("readonly", TEXT_MAIN)]
        )

        style.configure("TCheckbutton", background=BG_CARD, foreground=TEXT_SUB)
        style.map("TCheckbutton", background=[("active", BG_CARD)])

        # Таблица Treeview
        style.configure(
            "Treeview",
            background=BG_INPUT,
            fieldbackground=BG_INPUT,
            foreground=TEXT_MAIN,
            bordercolor=BORDER_COLOR,
            rowheight=32,
            font=("Segoe UI", 9)
        )
        style.configure(
            "Treeview.Heading",
            background="#020617",
            foreground=TEXT_MUTED,
            bordercolor=BORDER_COLOR,
            font=("Segoe UI", 9, "bold"),
            padding=(6, 6)
        )
        style.map(
            "Treeview",
            background=[("selected", "#1e3a8a")],
            foreground=[("selected", "#ffffff")]
        )

    # -------------------------------------------------------------------------
    # Построение интерфейса по двухколоночному макету со скриншота
    # -------------------------------------------------------------------------
    def _build_ui(self) -> None:
        # 1. Верхняя полоса «Обновление программы»
        upd_bar = ttk.Frame(self, style="Card.TFrame", padding=(14, 10))
        upd_bar.pack(fill=tk.X, padx=14, pady=(12, 8))

        ttk.Label(upd_bar, text="↑ Обновление программы:", font=("Segoe UI", 9, "bold")).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        self.version_status_var = tk.StringVar(
            value=f"Установлена: v{APP_VERSION} | Доступна: не проверено"
        )
        ttk.Label(upd_bar, textvariable=self.version_status_var, style="Emerald.TLabel").pack(
            side=tk.LEFT, padx=(0, 12)
        )
        ttk.Label(upd_bar, text=f"·   GitHub: {GITHUB_REPO}", style="Muted.TLabel").pack(side=tk.LEFT)

        self.btn_install_update_top = ttk.Button(
            upd_bar,
            text="Скачать и обновить",
            style="Emerald.TButton",
            command=self.on_install_update,
            state=tk.DISABLED
        )
        self.btn_install_update_top.pack(side=tk.RIGHT, padx=(6, 0))

        ttk.Button(
            upd_bar,
            text="Проверить обновления",
            style="Secondary.TButton",
            command=lambda: self.on_check_updates(silent_if_current=False)
        ).pack(side=tk.RIGHT, padx=4)

        # 2. Основная двухколоночная сетка (Левая колонка + Правая колонка)
        main_grid = ttk.Frame(self, style="Canvas.TFrame")
        main_grid.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 12))
        main_grid.columnconfigure(0, weight=4, minsize=410)
        main_grid.columnconfigure(1, weight=8)
        main_grid.rowconfigure(0, weight=1)

        left_col = ttk.Frame(main_grid, style="Canvas.TFrame")
        left_col.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 10))

        right_col = ttk.Frame(main_grid, style="Canvas.TFrame")
        right_col.grid(row=0, column=1, sticky=tk.NSEW, padx=(10, 0))

        self._build_left_column(left_col)
        self._build_right_column(right_col)

    def _build_left_column(self, parent: ttk.Frame) -> None:
        # Карточка 1: Проект и управление VRAM
        proj_card = ttk.LabelFrame(parent, text="  Проект и управление VRAM  ", style="Card.TLabelframe", padding=12)
        proj_card.pack(fill=tk.X, pady=(0, 10))

        row_proj = ttk.Frame(proj_card)
        row_proj.pack(fill=tk.X, pady=(0, 8))
        self.project_var = tk.StringVar(value=self.core.state["project_name"])
        self.project_combo = ttk.Combobox(
            row_proj,
            textvariable=self.project_var,
            values=self.core.list_projects()
        )
        self.project_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ttk.Button(row_proj, text="Открыть проект", style="Secondary.TButton", command=self.on_open_project).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Button(row_proj, text="...", style="Secondary.TButton", width=3, command=self.on_browse_project_dir).pack(
            side=tk.LEFT
        )

        row_ace_btns = ttk.Frame(proj_card)
        row_ace_btns.pack(fill=tk.X, pady=4)
        row_ace_btns.columnconfigure(0, weight=1)
        row_ace_btns.columnconfigure(1, weight=1)

        ttk.Button(
            row_ace_btns,
            text="▷ Запустить ACE API",
            style="Secondary.TButton",
            command=self.on_start_ace
        ).grid(row=0, column=0, sticky=tk.EW, padx=(0, 4))

        ttk.Button(
            row_ace_btns,
            text="□ Остановить ACE API",
            style="Rose.TButton",
            command=self.on_stop_ace
        ).grid(row=0, column=1, sticky=tk.EW, padx=(4, 0))

        row_status = ttk.Frame(proj_card)
        row_status.pack(fill=tk.X, pady=(8, 2))
        ttk.Label(row_status, text="ACE-Step 1.5 (127.0.0.1:8001):", style="Muted.TLabel").pack(side=tk.LEFT)
        self.ace_status_lbl = ttk.Label(row_status, text="Онлайн / Готов", style="Emerald.TLabel")
        self.ace_status_lbl.pack(side=tk.RIGHT)

        row_gpus = ttk.Frame(proj_card)
        row_gpus.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(
            row_gpus,
            text="Проверить GPU / ComfyUI (8188, 8189)",
            style="Secondary.TButton",
            command=self.on_check_gpus
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Карточка 2: 1. Генерация песни (ACE-Step 1.5) и FFprobe
        song_card = ttk.LabelFrame(
            parent,
            text="  1. Генерация песни (ACE-Step 1.5) и FFprobe  ",
            style="Card.TLabelframe",
            padding=12
        )
        song_card.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        ttk.Label(song_card, text="Теги стиля (Prompt для acestep-v15-turbo)", style="Muted.TLabel").pack(anchor=tk.W)
        self.music_prompt_var = tk.StringVar()
        ttk.Entry(song_card, textvariable=self.music_prompt_var).pack(fill=tk.X, pady=(2, 8))

        ttk.Label(song_card, text="Текст песни (Lyrics — /format_input с acestep-5Hz-lm-0.6B)", style="Muted.TLabel").pack(anchor=tk.W)
        self.lyrics_text = tk.Text(
            song_card,
            height=5,
            wrap=tk.WORD,
            bg=BG_INPUT,
            fg=TEXT_MAIN,
            insertbackground=TEXT_MAIN,
            relief="solid",
            bd=1,
            font=("Consolas", 9)
        )
        self.lyrics_text.pack(fill=tk.BOTH, expand=True, pady=(2, 8))

        dur_seed_row = ttk.Frame(song_card)
        dur_seed_row.pack(fill=tk.X, pady=(0, 8))
        dur_seed_row.columnconfigure(0, weight=1)
        dur_seed_row.columnconfigure(1, weight=1)

        d_col = ttk.Frame(dur_seed_row)
        d_col.grid(row=0, column=0, sticky=tk.EW, padx=(0, 6))
        ttk.Label(d_col, text="Точная длительность (сек)", style="Muted.TLabel").pack(anchor=tk.W)
        self.song_dur_var = tk.DoubleVar(value=30.0)
        ttk.Entry(d_col, textvariable=self.song_dur_var).pack(fill=tk.X, pady=2)

        s_col = ttk.Frame(dur_seed_row)
        s_col.grid(row=0, column=1, sticky=tk.EW, padx=(6, 0))
        ttk.Label(s_col, text="Seed", style="Muted.TLabel").pack(anchor=tk.W)
        self.song_seed_var = tk.IntVar(value=42)
        ttk.Entry(s_col, textvariable=self.song_seed_var).pack(fill=tk.X, pady=2)

        song_btns = ttk.Frame(song_card)
        song_btns.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(song_btns, text="Сгенерировать текст", style="Secondary.TButton", command=self.on_generate_lyrics).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(song_btns, text="Сгенерировать трек", style="Primary.TButton", command=self.on_generate_song).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(song_btns, text="FFprobe файл...", style="Secondary.TButton", command=self.on_select_audio).pack(
            side=tk.LEFT
        )

        ttk.Label(song_card, text="Аудиофайл проекта (audio/song.mp3)", style="Muted.TLabel").pack(anchor=tk.W)
        self.song_path_var = tk.StringVar()
        ttk.Entry(song_card, textvariable=self.song_path_var).pack(fill=tk.X, pady=(2, 6))

        ttk.Label(song_card, text="Изображение главного героя (только для сцен lip-sync)", style="Muted.TLabel").pack(anchor=tk.W)
        hero_row = ttk.Frame(song_card)
        hero_row.pack(fill=tk.X, pady=(2, 0))
        self.hero_image_var = tk.StringVar()
        ttk.Entry(hero_row, textvariable=self.hero_image_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ttk.Button(hero_row, text="Обзор...", style="Secondary.TButton", command=self.on_select_hero_image).pack(side=tk.LEFT)

        # Карточка 3: Настройки путей и VRAM
        cfg_card = ttk.LabelFrame(parent, text="  3. Настройки путей и VRAM (config.json)  ", style="Card.TLabelframe", padding=10)
        cfg_card.pack(fill=tk.X)

        self.cfg_ace_dir = tk.StringVar(value=self.core.config.get("ace_dir", r"C:\AI\ACE-Step-1.5"))
        self.cfg_comfy_root = tk.StringVar(value=self.core.config.get("comfy_root", r"C:\AI\ComfyUI_windows_portable"))
        self.cfg_wf_lipsync = tk.StringVar(value=self.core.config.get("workflow_lipsync", r"C:\AI\wan2.2_s2v_api.json"))
        self.cfg_wf_broll = tk.StringVar(value=self.core.config.get("workflow_broll", r"C:\AI\wan2.2_i2v_api.json"))
        self.cfg_ace_url = tk.StringVar(value=self.core.config.get("ace_url", "http://127.0.0.1:8001"))
        self.cfg_comfy_urls = tk.StringVar(
            value=", ".join(self.core.config.get("comfy_urls", ["http://127.0.0.1:8188", "http://127.0.0.1:8189"]))
        )
        self.cfg_lowvram = tk.BooleanVar(value=bool(self.core.config.get("lowvram", False)))
        self.cfg_reserve_vram = tk.DoubleVar(value=float(self.core.config.get("reserve_vram", 2.0)))

        for lbl, var in (
            ("workflow_lipsync (S2V):", self.cfg_wf_lipsync),
            ("workflow_broll (I2V/T2V):", self.cfg_wf_broll),
        ):
            r = ttk.Frame(cfg_card)
            r.pack(fill=tk.X, pady=2)
            ttk.Label(r, text=lbl, style="Muted.TLabel", width=22).pack(side=tk.LEFT)
            ttk.Entry(r, textvariable=var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        vram_row = ttk.Frame(cfg_card)
        vram_row.pack(fill=tk.X, pady=(6, 6))
        ttk.Checkbutton(vram_row, text="Флаг --lowvram (12 ГБ)", variable=self.cfg_lowvram).pack(side=tk.LEFT)
        ttk.Entry(vram_row, textvariable=self.cfg_reserve_vram, width=6).pack(side=tk.RIGHT)
        ttk.Label(vram_row, text="--reserve-vram (ГБ):", style="Muted.TLabel").pack(side=tk.RIGHT, padx=4)

        cfg_btns = ttk.Frame(cfg_card)
        cfg_btns.pack(fill=tk.X)
        ttk.Button(cfg_btns, text="Сохранить config.json", style="Primary.TButton", command=self.on_save_settings).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(cfg_btns, text="Comfy 8188", style="Secondary.TButton", command=lambda: self.on_start_comfy(8188, 0)).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Button(cfg_btns, text="Comfy 8189", style="Secondary.TButton", command=lambda: self.on_start_comfy(8189, 1)).pack(
            side=tk.LEFT
        )

    def _build_right_column(self, parent: ttk.Frame) -> None:
        sb_card = ttk.LabelFrame(
            parent,
            text="  2. Раскадровка сцен (Wan2.2: разделение lip-sync / b-roll и контроль 4k+1 кадров)  ",
            style="Card.TLabelframe",
            padding=12
        )
        sb_card.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Верхняя строка пресетов
        preset_bar = ttk.Frame(sb_card)
        preset_bar.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(
            preset_bar,
            text="Промпты для энкодера UMT5 — строго на английском языке · Подрезка -t duration -r 24 при сборке",
            style="Muted.TLabel"
        ).pack(side=tk.LEFT)

        ttk.Button(preset_bar, text="Создать раскадровку", style="Secondary.TButton", command=self.on_create_storyboard).pack(
            side=tk.RIGHT
        )
        self.scene_dur_var = tk.DoubleVar(value=float(self.core.config.get("default_scene_duration", 5.0)))
        ttk.Entry(preset_bar, textvariable=self.scene_dur_var, width=6).pack(side=tk.RIGHT, padx=6)
        self.preset_var = tk.StringVar(value="cyber_cat")
        ttk.Combobox(
            preset_bar,
            textvariable=self.preset_var,
            values=list(STORYBOARD_PRESETS.keys()),
            state="readonly",
            width=14
        ).pack(side=tk.RIGHT)

        # Панель действий конвейера
        act_bar = ttk.Frame(sb_card)
        act_bar.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(
            act_bar,
            text="✂ Нарезать WAV (16kHz mono)",
            style="Secondary.TButton",
            command=self.on_slice_audio
        ).pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(
            act_bar,
            text="В очередь ComfyUI",
            style="Primary.TButton",
            command=self.on_queue_all_scenes
        ).pack(side=tk.LEFT, padx=(0, 8))

        self.skip_ready_var = tk.BooleanVar(value=bool(self.core.config.get("skip_completed", True)))
        ttk.Checkbutton(
            act_bar,
            text="Пропускать готовые сцены",
            variable=self.skip_ready_var,
            command=self.on_toggle_skip_ready
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            act_bar,
            text="Финальная сборка MP4 (CRF 18)",
            style="Emerald.TButton",
            command=self.on_assemble_video
        ).pack(side=tk.RIGHT)

        # Таблица сцен
        columns = ("id", "type", "timecode", "wan_frames", "prompt", "status")
        self.tree = ttk.Treeview(sb_card, columns=columns, show="headings", height=12)
        self.tree.heading("id", text="#")
        self.tree.heading("type", text="Тип сцены (RU метка)")
        self.tree.heading("timecode", text="Таймкод")
        self.tree.heading("wan_frames", text="Wan кадры (4k+1)")
        self.tree.heading("prompt", text="Английский промпт (UMT5)")
        self.tree.heading("status", text="Статус")

        self.tree.column("id", width=42, anchor=tk.CENTER)
        self.tree.column("type", width=180, anchor=tk.W)
        self.tree.column("timecode", width=120, anchor=tk.CENTER)
        self.tree.column("wan_frames", width=110, anchor=tk.CENTER)
        self.tree.column("prompt", width=420, anchor=tk.W)
        self.tree.column("status", width=85, anchor=tk.CENTER)

        self.tree.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        self.tree.bind("<<TreeviewSelect>>", self.on_scene_select)

        # Редактирование выбранной сцены
        edit_bar = ttk.Frame(sb_card)
        edit_bar.pack(fill=tk.X)

        ttk.Label(edit_bar, text="Тип:", style="Muted.TLabel").pack(side=tk.LEFT, padx=(0, 4))
        self.edit_type_var = tk.StringVar(value="lip-sync")
        ttk.Combobox(
            edit_bar,
            textvariable=self.edit_type_var,
            values=list(SCENE_TYPE_LABELS.keys()),
            state="readonly",
            width=12
        ).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(edit_bar, text="Промпт сцены:", style="Muted.TLabel").pack(side=tk.LEFT, padx=(0, 4))
        self.edit_prompt_var = tk.StringVar()
        prompt_entry = ttk.Entry(edit_bar, textvariable=self.edit_prompt_var)
        prompt_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        prompt_entry.bind("<KeyRelease>", self.on_prompt_key_release)

        self.edit_custom_img_var = tk.StringVar()
        ttk.Button(
            edit_bar,
            text="↻ Пересоздать сцену",
            style="Secondary.TButton",
            command=self.on_rerender_selected_scene
        ).pack(side=tk.RIGHT)

        # Журнал команд конвейера
        log_card = ttk.LabelFrame(
            parent,
            text="  Журнал команд конвейера (ACE-Step 1.5 / ComfyUI / FFmpeg / GitHub Updater)  ",
            style="Card.TLabelframe",
            padding=10
        )
        log_card.pack(fill=tk.X)

        self.log_text = tk.Text(
            log_card,
            height=7,
            wrap=tk.WORD,
            bg=BG_INPUT,
            fg=TEXT_SUB,
            insertbackground=TEXT_MAIN,
            relief="solid",
            bd=1,
            font=("Consolas", 9)
        )
        self.log_text.pack(fill=tk.X)

    # -------------------------------------------------------------------------
    # Вспомогательные методы синхронизации состояния и UI
    # -------------------------------------------------------------------------
    def log(self, message: str) -> None:
        def _append() -> None:
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
        self.after(0, _append)

    def _load_state_into_ui(self) -> None:
        st = self.core.state
        req = st.get("song_request", {})
        self.project_var.set(st.get("project_name", "default_project"))
        self.project_combo.configure(values=self.core.list_projects())

        self.music_prompt_var.set(req.get("prompt", ""))
        self.lyrics_text.delete("1.0", tk.END)
        self.lyrics_text.insert("1.0", req.get("lyrics", ""))
        self.song_dur_var.set(float(st.get("song_duration") or req.get("duration") or 30.0))
        self.song_seed_var.set(int(req.get("seed", 42)))

        self.song_path_var.set(st.get("song_path", ""))
        self.hero_image_var.set(st.get("hero_image", ""))
        self._refresh_storyboard_tree()

    def _refresh_storyboard_tree(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        fps = int(self.core.config.get("fps", 24))
        for scene in self.core.state.get("storyboard", []):
            sid = int(scene["id"])
            stype = scene.get("type", "lip-sync")
            type_ru = f"{stype} · {SCENE_TYPE_LABELS.get(stype, stype)}"
            tc = f"{float(scene['start']):.2f}s – {float(scene['end']):.2f}s ({float(scene['duration']):.2f}s)"
            frames = f"{self.core.calculate_wan_frames(float(scene['duration']), fps=fps)} кадр."
            status = scene.get("status", "ожидание")
            prompt = scene.get("prompt", "")
            self.tree.insert("", tk.END, iid=str(sid), values=(f"{sid:02d}", type_ru, tc, frames, prompt, status))

    # -------------------------------------------------------------------------
    # Обработчики проверки и установки обновлений с GitHub
    # -------------------------------------------------------------------------
    def on_check_updates(self, silent_if_current: bool = False) -> None:
        self.version_status_var.set(f"Установлена: v{APP_VERSION} | Проверка на GitHub...")

        def _task() -> None:
            try:
                info = self.core.check_for_updates(log_cb=self.log)
                self._latest_update_info = info
                cur = info.get("current_version", APP_VERSION)
                lat = info.get("latest_version", APP_VERSION)
                has_upd = bool(info.get("update_available", False))

                def _update_ui() -> None:
                    if has_upd:
                        self.version_status_var.set(
                            f"Установлена: v{cur} | Доступна: v{lat} (Есть обновление!)"
                        )
                        self.btn_install_update_top.configure(state=tk.NORMAL)
                        if not silent_if_current:
                            notes = info.get("notes") or "Описание изменений отсутствует."
                            ask = messagebox.askyesno(
                                "Доступно обновление MusicVideoStudio",
                                f"Найдена новая версия v{lat} (у вас установлена v{cur}).\n\n"
                                f"Что нового:\n{notes[:600]}\n\n"
                                f"Скачать и установить обновление сейчас?"
                            )
                            if ask:
                                self.on_install_update()
                    else:
                        self.version_status_var.set(
                            f"Установлена: v{cur} | Доступна: v{lat} (Актуальная)"
                        )
                        self.btn_install_update_top.configure(state=tk.DISABLED)

                self.after(0, _update_ui)
            except Exception as e:
                self.log(f"[UPDATE ERROR] {e}")
                self.after(
                    0,
                    lambda: self.version_status_var.set(
                        f"Установлена: v{APP_VERSION} | Ошибка проверки"
                    )
                )

        threading.Thread(target=_task, daemon=True).start()

    def on_install_update(self) -> None:
        info = self._latest_update_info or {}
        dl_url = str(info.get("download_url", "")).strip()
        if not dl_url:
            messagebox.showwarning(
                "Файл установщика не найден",
                "В релизе на GitHub не найден файл MusicVideoStudio_Setup.exe.\n"
                f"Откройте страницу релизов вручную:\nhttps://github.com/{GITHUB_REPO}/releases"
            )
            return

        self.version_status_var.set("Скачивание обновления... Приложение перезапустится автоматически.")
        self.btn_install_update_top.configure(state=tk.DISABLED)

        def _task() -> None:
            try:
                self.core.download_and_install_update(dl_url, exit_app=True, log_cb=self.log)
            except Exception as e:
                self.log(f"[UPDATE ERROR] Ошибка при скачивании/запуске обновления: {e}")
                self.after(0, lambda: messagebox.showerror("Ошибка обновления", str(e)))

        threading.Thread(target=_task, daemon=True).start()

    # -------------------------------------------------------------------------
    # Обработчики событий конвейера
    # -------------------------------------------------------------------------
    def on_open_project(self) -> None:
        name = self.project_var.get().strip() or "default_project"
        self.core.open_project(name, log_cb=self.log)
        self._load_state_into_ui()

    def on_browse_project_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=str(PROJECTS_ROOT.resolve()), title="Выберите папку проекта")
        if chosen:
            proj_name = Path(chosen).name
            self.project_var.set(proj_name)
            self.on_open_project()

    def on_start_ace(self) -> None:
        self.ace_status_lbl.configure(text="Онлайн (модель в VRAM)")
        threading.Thread(target=self.core.start_ace_server, kwargs={"log_cb": self.log}, daemon=True).start()

    def on_stop_ace(self) -> None:
        self.ace_status_lbl.configure(text="Остановлен (VRAM свободна)")
        threading.Thread(target=self.core.stop_ace_server, kwargs={"log_cb": self.log}, daemon=True).start()

    def on_check_gpus(self) -> None:
        def _task() -> None:
            servers = self.core.get_online_comfy_servers(log_cb=self.log)
            if not servers:
                self.log("[GPU] Активных серверов ComfyUI на портах 8188/8189 не обнаружено.")
        threading.Thread(target=_task, daemon=True).start()

    def on_save_song_params(self) -> None:
        lyrics = self.lyrics_text.get("1.0", tk.END).strip()
        self.core.save_song_request(
            {
                "prompt": self.music_prompt_var.get().strip(),
                "lyrics": lyrics,
                "duration": float(self.song_dur_var.get()),
                "seed": int(self.song_seed_var.get())
            },
            hero_image=self.hero_image_var.get().strip()
        )
        self.log("[INFO] Параметры песни и портрет героя сохранены в data/song_request.json")

    def on_generate_lyrics(self) -> None:
        prompt = self.music_prompt_var.get().strip()
        lyrics_hint = self.lyrics_text.get("1.0", tk.END).strip()

        def _task() -> None:
            try:
                self.core.generate_lyrics_ace(prompt, lyrics_hint, log_cb=self.log)
                self.after(0, self._load_state_into_ui)
            except Exception as e:
                self.log(f"[ERROR] {e}")

        threading.Thread(target=_task, daemon=True).start()

    def on_generate_song(self) -> None:
        prompt = self.music_prompt_var.get().strip()
        lyrics = self.lyrics_text.get("1.0", tk.END).strip()
        dur = float(self.song_dur_var.get())
        seed = int(self.song_seed_var.get())

        def _task() -> None:
            try:
                self.core.generate_song_ace(prompt, lyrics, duration=dur, seed=seed, log_cb=self.log)
                self.after(0, self._load_state_into_ui)
            except Exception as e:
                self.log(f"[ERROR] {e}")

        threading.Thread(target=_task, daemon=True).start()

    def on_select_audio(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Выберите аудиофайл песни",
            filetypes=[("Аудиофайлы", "*.mp3 *.wav *.flac *.ogg *.m4a"), ("Все файлы", "*.*")]
        )
        if file_path:
            try:
                self.core.set_song_file(file_path, copy_to_project=True, log_cb=self.log)
                self._load_state_into_ui()
            except Exception as e:
                messagebox.showerror("Ошибка аудио", str(e))

    def on_select_hero_image(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Выберите изображение главного героя",
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.webp"), ("Все файлы", "*.*")]
        )
        if file_path:
            self.hero_image_var.set(file_path)
            self.on_save_song_params()

    def on_create_storyboard(self) -> None:
        try:
            self.core.generate_storyboard_from_preset(
                preset_name=self.preset_var.get(),
                scene_duration=float(self.scene_dur_var.get()),
                log_cb=self.log
            )
            self._refresh_storyboard_tree()
        except Exception as e:
            messagebox.showerror("Ошибка раскадровки", str(e))

    def on_slice_audio(self) -> None:
        def _task() -> None:
            try:
                self.core.slice_audio_segments(log_cb=self.log)
                self.after(0, self._refresh_storyboard_tree)
            except Exception as e:
                self.log(f"[ERROR] {e}")
        threading.Thread(target=_task, daemon=True).start()

    def on_toggle_skip_ready(self) -> None:
        self.core.save_config({"skip_completed": bool(self.skip_ready_var.get())})

    def on_scene_select(self, _event: object = None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        sid = int(sel[0])
        self._selected_scene_id = sid
        scene = next((s for s in self.core.state["storyboard"] if int(s["id"]) == sid), None)
        if scene:
            self.edit_type_var.set(scene.get("type", "lip-sync"))
            self.edit_prompt_var.set(scene.get("prompt", ""))
            self.edit_custom_img_var.set(scene.get("custom_image", ""))

    def on_prompt_key_release(self, _event: object = None) -> None:
        if self._selected_scene_id > 0:
            self.core.update_scene(
                self._selected_scene_id,
                prompt=self.edit_prompt_var.get(),
                scene_type=self.edit_type_var.get(),
                custom_image=self.edit_custom_img_var.get()
            )
            self._refresh_storyboard_tree()

    def on_save_scene_edits(self) -> None:
        if self._selected_scene_id <= 0:
            return
        self.core.update_scene(
            self._selected_scene_id,
            prompt=self.edit_prompt_var.get(),
            scene_type=self.edit_type_var.get(),
            custom_image=self.edit_custom_img_var.get()
        )
        self._refresh_storyboard_tree()
        self.log(f"[STORYBOARD] Сцена #{self._selected_scene_id:03d} сохранена в data/storyboard.json")

    def on_rerender_selected_scene(self) -> None:
        if self._selected_scene_id <= 0:
            messagebox.showinfo("Выбор сцены", "Сначала выберите сцену в таблице раскадровки.")
            return
        self.on_save_scene_edits()
        sid = self._selected_scene_id

        def _task() -> None:
            try:
                self.core.render_single_scene(sid, log_cb=self.log)
                self.after(0, self._refresh_storyboard_tree)
            except Exception as e:
                self.log(f"[ERROR] {e}")
                self.after(0, self._refresh_storyboard_tree)

        threading.Thread(target=_task, daemon=True).start()

    def on_queue_all_scenes(self) -> None:
        skip_flag = bool(self.skip_ready_var.get())

        def _task() -> None:
            try:
                self.core.queue_all_scenes(skip_completed=skip_flag, log_cb=self.log)
                self.after(0, self._refresh_storyboard_tree)
            except Exception as e:
                self.log(f"[ERROR] {e}")
                self.after(0, self._refresh_storyboard_tree)

        threading.Thread(target=_task, daemon=True).start()

    def on_assemble_video(self) -> None:
        def _task() -> None:
            try:
                out_path = self.core.assemble_video(log_cb=self.log)
                self.log(f"[SUCCESS] Видеоклип готов: {out_path}")
            except Exception as e:
                self.log(f"[ERROR] {e}")
        threading.Thread(target=_task, daemon=True).start()

    def on_save_settings(self) -> None:
        urls = [u.strip() for u in self.cfg_comfy_urls.get().split(",") if u.strip()]
        new_cfg = {
            "ace_dir": self.cfg_ace_dir.get().strip(),
            "comfy_root": self.cfg_comfy_root.get().strip(),
            "workflow_lipsync": self.cfg_wf_lipsync.get().strip(),
            "workflow_broll": self.cfg_wf_broll.get().strip(),
            "ace_url": self.cfg_ace_url.get().strip(),
            "comfy_urls": urls,
            "lowvram": bool(self.cfg_lowvram.get()),
            "reserve_vram": float(self.cfg_reserve_vram.get())
        }
        self.core.save_config(new_cfg)
        self.log("[CONFIG] Настройки успешно сохранены в config.json")

    def on_start_comfy(self, port: int, gpu_id: int) -> None:
        self.on_save_settings()
        threading.Thread(
            target=self.core.start_comfy_server,
            kwargs={"port": port, "gpu_id": gpu_id, "log_cb": self.log},
            daemon=True
        ).start()


if __name__ == "__main__":
    app = MusicVideoStudioApp()
    app.mainloop()
