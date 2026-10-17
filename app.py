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


class MusicVideoStudioApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Локальная ИИ-студия музыкальных клипов (MusicVideoStudio v{APP_VERSION})")
        self.geometry("1320x880")
        self.minsize(1140, 760)

        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")

        self.core = StudioCore()
        self._selected_scene_id: int = 0
        self._latest_update_info: Optional[Dict[str, Any]] = None

        self._build_ui()
        self._load_state_into_ui()

    # -------------------------------------------------------------------------
    # Построение интерфейса
    # -------------------------------------------------------------------------
    def _build_ui(self) -> None:
        # Верхняя панель проекта, сервисов и блока автообновления в правом верхнем углу
        header_container = ttk.Frame(self)
        header_container.pack(fill=tk.X, padx=10, pady=(8, 4))

        top_frame = ttk.LabelFrame(header_container, text="Проект и управление серверами / VRAM", padding=8)
        top_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        ttk.Label(top_frame, text="Папка проекта:").grid(row=0, column=0, sticky=tk.W, padx=4)
        self.project_var = tk.StringVar(value=self.core.state["project_name"])
        self.project_combo = ttk.Combobox(
            top_frame,
            textvariable=self.project_var,
            values=self.core.list_projects(),
            width=20
        )
        self.project_combo.grid(row=0, column=1, padx=4)

        ttk.Button(top_frame, text="Открыть проект", command=self.on_open_project).grid(row=0, column=2, padx=3)
        ttk.Button(top_frame, text="Обзор...", command=self.on_browse_project_dir).grid(row=0, column=3, padx=3)

        ttk.Separator(top_frame, orient=tk.VERTICAL).grid(row=0, column=4, sticky=tk.NS, padx=6)

        ttk.Button(top_frame, text="Запустить ACE API", command=self.on_start_ace).grid(row=0, column=5, padx=3)
        ttk.Button(top_frame, text="Остановить ACE API (освободить VRAM)", command=self.on_stop_ace).grid(row=0, column=6, padx=3)
        ttk.Button(top_frame, text="Проверить GPU", command=self.on_check_gpus).grid(row=0, column=7, padx=3)

        # Блок «Обновление программы» в правом верхнем углу шапки
        update_top_frame = ttk.LabelFrame(header_container, text="Обновление программы", padding=8)
        update_top_frame.pack(side=tk.RIGHT, fill=tk.Y)

        self.version_status_var = tk.StringVar(
            value=f"Установлена версия: v{APP_VERSION} | Доступна: не проверено"
        )
        ttk.Label(update_top_frame, textvariable=self.version_status_var, font=("Segoe UI", 9, "bold")).pack(
            side=tk.LEFT, padx=(4, 8)
        )
        ttk.Button(update_top_frame, text="Проверить обновления", command=self.on_check_updates).pack(
            side=tk.LEFT, padx=3
        )
        self.btn_install_update_top = ttk.Button(
            update_top_frame,
            text="Скачать и обновить",
            command=self.on_install_update,
            state=tk.DISABLED
        )
        self.btn_install_update_top.pack(side=tk.LEFT, padx=3)

        # Вкладки основного рабочего процесса
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        self.tab_song = ttk.Frame(self.notebook, padding=10)
        self.tab_storyboard = ttk.Frame(self.notebook, padding=10)
        self.tab_settings = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.tab_song, text="1. Песня и герой (ACE-Step 1.5)")
        self.notebook.add(self.tab_storyboard, text="2. Раскадровка и рендер (ComfyUI + FFmpeg)")
        self.notebook.add(self.tab_settings, text="3. Настройки путей, VRAM и Обновление")

        self._build_song_tab()
        self._build_storyboard_tab()
        self._build_settings_tab()

        # Журнал событий внизу окна
        log_frame = ttk.LabelFrame(self, text="Журнал операций", padding=6)
        log_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=(4, 8))

        self.log_text = tk.Text(log_frame, height=8, wrap=tk.WORD, font=("Consolas", 9))
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_song_tab(self) -> None:
        left = ttk.LabelFrame(self.tab_song, text="Параметры генерации песни (ACE-Step 1.5)", padding=10)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        ttk.Label(left, text="Музыкальный стиль / теги (Prompt):").pack(anchor=tk.W)
        self.music_prompt_var = tk.StringVar()
        ttk.Entry(left, textvariable=self.music_prompt_var).pack(fill=tk.X, pady=(2, 8))

        ttk.Label(left, text="Текст песни (Lyrics):").pack(anchor=tk.W)
        self.lyrics_text = tk.Text(left, height=14, wrap=tk.WORD, font=("Consolas", 10))
        self.lyrics_text.pack(fill=tk.BOTH, expand=True, pady=(2, 8))

        params_row = ttk.Frame(left)
        params_row.pack(fill=tk.X, pady=4)

        ttk.Label(params_row, text="Длительность (сек):").pack(side=tk.LEFT)
        self.song_dur_var = tk.DoubleVar(value=30.0)
        ttk.Entry(params_row, textvariable=self.song_dur_var, width=10).pack(side=tk.LEFT, padx=(4, 16))

        ttk.Label(params_row, text="Seed:").pack(side=tk.LEFT)
        self.song_seed_var = tk.IntVar(value=42)
        ttk.Entry(params_row, textvariable=self.song_seed_var, width=12).pack(side=tk.LEFT, padx=4)

        btn_row = ttk.Frame(left)
        btn_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btn_row, text="Сгенерировать текст (/format_input)", command=self.on_generate_lyrics).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Сгенерировать трек (/release_task)", command=self.on_generate_song).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_row, text="Сохранить параметры", command=self.on_save_song_params).pack(side=tk.LEFT, padx=6)

        right = ttk.LabelFrame(self.tab_song, text="Аудиофайл проекта и изображение главного героя", padding=10)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False, ipadx=10)

        ttk.Label(right, text="Текущий аудиофайл (song.mp3 / WAV):").pack(anchor=tk.W)
        self.song_path_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.song_path_var, width=48).pack(fill=tk.X, pady=2)
        ttk.Button(right, text="Выбрать готовый аудиофайл (авто-FFprobe)...", command=self.on_select_audio).pack(anchor=tk.W, pady=(2, 10))

        self.probed_dur_label = ttk.Label(right, text="Точная длительность (FFprobe): 0.00 сек", font=("Segoe UI", 10, "bold"))
        self.probed_dur_label.pack(anchor=tk.W, pady=(0, 14))

        ttk.Separator(right, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        ttk.Label(right, text="Изображение главного героя (для сцен lip-sync):").pack(anchor=tk.W)
        self.hero_image_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.hero_image_var, width=48).pack(fill=tk.X, pady=2)
        ttk.Button(right, text="Выбрать портрет героя...", command=self.on_select_hero_image).pack(anchor=tk.W, pady=(2, 12))

        ttk.Button(right, text="Нарезать аудио на сегменты (16kHz mono WAV)", command=self.on_slice_audio).pack(fill=tk.X, pady=6)

    def _build_storyboard_tab(self) -> None:
        toolbar = ttk.Frame(self.tab_storyboard)
        toolbar.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(toolbar, text="Пресет раскадровки:").pack(side=tk.LEFT)
        self.preset_var = tk.StringVar(value="cyber_cat")
        ttk.Combobox(
            toolbar,
            textvariable=self.preset_var,
            values=list(STORYBOARD_PRESETS.keys()),
            state="readonly",
            width=16
        ).pack(side=tk.LEFT, padx=6)

        ttk.Label(toolbar, text="Длина сцены (сек):").pack(side=tk.LEFT, padx=(8, 2))
        self.scene_dur_var = tk.DoubleVar(value=float(self.core.config.get("default_scene_duration", 5.0)))
        ttk.Entry(toolbar, textvariable=self.scene_dur_var, width=7).pack(side=tk.LEFT, padx=4)

        ttk.Button(toolbar, text="Создать раскадровку", command=self.on_create_storyboard).pack(side=tk.LEFT, padx=6)
        ttk.Button(toolbar, text="Нарезать WAV-сегменты", command=self.on_slice_audio).pack(side=tk.LEFT, padx=6)

        self.skip_ready_var = tk.BooleanVar(value=bool(self.core.config.get("skip_completed", True)))
        ttk.Checkbutton(
            toolbar,
            text="Пропускать готовые сцены",
            variable=self.skip_ready_var,
            command=self.on_toggle_skip_ready
        ).pack(side=tk.LEFT, padx=10)

        ttk.Button(toolbar, text="Отправить все сцены в ComfyUI", command=self.on_queue_all_scenes).pack(side=tk.LEFT, padx=6)
        ttk.Button(toolbar, text="Финальная сборка MP4", command=self.on_assemble_video).pack(side=tk.RIGHT, padx=4)

        # Таблица сцен
        columns = ("id", "type", "type_ru", "timecode", "duration", "wan_frames", "status", "prompt")
        self.tree = ttk.Treeview(self.tab_storyboard, columns=columns, show="headings", height=13)
        self.tree.heading("id", text="#")
        self.tree.heading("type", text="Тип")
        self.tree.heading("type_ru", text="Описание типа")
        self.tree.heading("timecode", text="Таймкод")
        self.tree.heading("duration", text="Длит. (с)")
        self.tree.heading("wan_frames", text="Кадры (4k+1)")
        self.tree.heading("status", text="Статус")
        self.tree.heading("prompt", text="Английский промпт (UMT5 Wan2.2)")

        self.tree.column("id", width=45, anchor=tk.CENTER)
        self.tree.column("type", width=85, anchor=tk.CENTER)
        self.tree.column("type_ru", width=190, anchor=tk.W)
        self.tree.column("timecode", width=120, anchor=tk.CENTER)
        self.tree.column("duration", width=80, anchor=tk.CENTER)
        self.tree.column("wan_frames", width=95, anchor=tk.CENTER)
        self.tree.column("status", width=95, anchor=tk.CENTER)
        self.tree.column("prompt", width=480, anchor=tk.W)

        self.tree.pack(fill=tk.BOTH, expand=True, pady=4)
        self.tree.bind("<<TreeviewSelect>>", self.on_scene_select)

        # Панель редактирования выбранной сцены
        edit_frame = ttk.LabelFrame(self.tab_storyboard, text="Редактирование и перегенерация выбранной сцены", padding=8)
        edit_frame.pack(fill=tk.X, pady=(6, 0))

        row1 = ttk.Frame(edit_frame)
        row1.pack(fill=tk.X, pady=2)

        ttk.Label(row1, text="Тип сцены:").pack(side=tk.LEFT)
        self.edit_type_var = tk.StringVar(value="lip-sync")
        self.edit_type_combo = ttk.Combobox(
            row1,
            textvariable=self.edit_type_var,
            values=list(SCENE_TYPE_LABELS.keys()),
            state="readonly",
            width=14
        )
        self.edit_type_combo.pack(side=tk.LEFT, padx=6)

        ttk.Label(row1, text="Своя картинка сцены (опционально для B-Roll):").pack(side=tk.LEFT, padx=(12, 4))
        self.edit_custom_img_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.edit_custom_img_var, width=38).pack(side=tk.LEFT, padx=4)
        ttk.Button(row1, text="Обзор...", command=self.on_browse_scene_image).pack(side=tk.LEFT, padx=4)

        ttk.Button(row1, text="Пересоздать сцену в ComfyUI", command=self.on_rerender_selected_scene).pack(side=tk.RIGHT, padx=4)
        ttk.Button(row1, text="Сохранить сцену в storyboard.json", command=self.on_save_scene_edits).pack(side=tk.RIGHT, padx=6)

        ttk.Label(edit_frame, text="Английский видео-промпт сцены (сохраняется на диск сразу):").pack(anchor=tk.W, pady=(4, 2))
        self.edit_prompt_var = tk.StringVar()
        prompt_entry = ttk.Entry(edit_frame, textvariable=self.edit_prompt_var)
        prompt_entry.pack(fill=tk.X, pady=2)
        prompt_entry.bind("<KeyRelease>", self.on_prompt_key_release)

    def _build_settings_tab(self) -> None:
        form = ttk.LabelFrame(self.tab_settings, text="Пути к компонентам и параметры VRAM (config.json)", padding=12)
        form.pack(fill=tk.BOTH, expand=True)

        self.cfg_ace_dir = tk.StringVar(value=self.core.config.get("ace_dir", r"C:\AI\ACE-Step-1.5"))
        self.cfg_comfy_root = tk.StringVar(value=self.core.config.get("comfy_root", r"C:\AI\ComfyUI_windows_portable"))
        self.cfg_wf_lipsync = tk.StringVar(value=self.core.config.get("workflow_lipsync", r"C:\AI\wan2.2_s2v_api.json"))
        self.cfg_wf_broll = tk.StringVar(value=self.core.config.get("workflow_broll", r"C:\AI\wan2.2_i2v_api.json"))
        self.cfg_ace_url = tk.StringVar(value=self.core.config.get("ace_url", "http://127.0.0.1:8001"))
        self.cfg_comfy_urls = tk.StringVar(value=", ".join(self.core.config.get("comfy_urls", ["http://127.0.0.1:8188", "http://127.0.0.1:8189"])))
        self.cfg_lowvram = tk.BooleanVar(value=bool(self.core.config.get("lowvram", False)))
        self.cfg_reserve_vram = tk.DoubleVar(value=float(self.core.config.get("reserve_vram", 2.0)))

        rows = [
            ("Папка ACE-Step 1.5 (ace_dir):", self.cfg_ace_dir),
            ("Папка ComfyUI Portable (comfy_root):", self.cfg_comfy_root),
            ("Шаблон Lip-Sync S2V (workflow_lipsync):", self.cfg_wf_lipsync),
            ("Шаблон B-Roll I2V/T2V (workflow_broll):", self.cfg_wf_broll),
            ("URL сервера ACE-Step:", self.cfg_ace_url),
            ("URL серверов ComfyUI (через запятую):", self.cfg_comfy_urls),
        ]
        for idx, (label_text, var) in enumerate(rows):
            ttk.Label(form, text=label_text).grid(row=idx, column=0, sticky=tk.W, pady=5, padx=6)
            ttk.Entry(form, textvariable=var, width=68).grid(row=idx, column=1, sticky=tk.EW, pady=5, padx=6)

        vram_frame = ttk.LabelFrame(form, text="Управление видеопамятью (VRAM)", padding=10)
        vram_frame.grid(row=len(rows), column=0, columnspan=2, sticky=tk.EW, pady=10, padx=6)

        ttk.Checkbutton(
            vram_frame,
            text="Использовать флаг --lowvram (включать для карт 12 ГБ VRAM; выключать для 24 ГБ VRAM для максимальной скорости)",
            variable=self.cfg_lowvram
        ).pack(anchor=tk.W, pady=4)

        res_row = ttk.Frame(vram_frame)
        res_row.pack(fill=tk.X, pady=4)
        ttk.Label(res_row, text="Резерв видеопамяти --reserve-vram (ГБ):").pack(side=tk.LEFT)
        ttk.Entry(res_row, textvariable=self.cfg_reserve_vram, width=10).pack(side=tk.LEFT, padx=8)

        btn_bar = ttk.Frame(form)
        btn_bar.grid(row=len(rows) + 1, column=0, columnspan=2, sticky=tk.W, pady=8, padx=6)
        ttk.Button(btn_bar, text="Сохранить настройки в config.json", command=self.on_save_settings).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_bar, text="Запустить ComfyUI (8188, GPU 0)", command=lambda: self.on_start_comfy(8188, 0)).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_bar, text="Запустить ComfyUI #2 (8189, GPU 1)", command=lambda: self.on_start_comfy(8189, 1)).pack(side=tk.LEFT, padx=4)

        # Блок «Обновление программы» на вкладке Настройки
        upd_frame = ttk.LabelFrame(
            form,
            text=f"Обновление программы (GitHub Releases: {GITHUB_REPO})",
            padding=10
        )
        upd_frame.grid(row=len(rows) + 2, column=0, columnspan=2, sticky=tk.EW, pady=10, padx=6)

        ttk.Label(upd_frame, textvariable=self.version_status_var, font=("Segoe UI", 10, "bold")).pack(
            anchor=tk.W, pady=(0, 6)
        )
        upd_btns = ttk.Frame(upd_frame)
        upd_btns.pack(fill=tk.X)
        ttk.Button(upd_btns, text="Проверить обновления на GitHub", command=self.on_check_updates).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        self.btn_install_update_settings = ttk.Button(
            upd_btns,
            text="Скачать и обновить (MusicVideoStudio_Setup.exe)",
            command=self.on_install_update,
            state=tk.DISABLED
        )
        self.btn_install_update_settings.pack(side=tk.LEFT, padx=4)

        form.columnconfigure(1, weight=1)

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
        self.probed_dur_label.configure(
            text=f"Точная длительность (FFprobe): {float(st.get('song_duration', 0.0)):.3f} сек"
        )
        self._refresh_storyboard_tree()

    def _refresh_storyboard_tree(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        fps = int(self.core.config.get("fps", 24))
        for scene in self.core.state.get("storyboard", []):
            sid = int(scene["id"])
            stype = scene.get("type", "lip-sync")
            type_ru = SCENE_TYPE_LABELS.get(stype, stype)
            tc = f"{float(scene['start']):.2f}s - {float(scene['end']):.2f}s"
            dur = f"{float(scene['duration']):.2f}"
            frames = self.core.calculate_wan_frames(float(scene["duration"]), fps=fps)
            status = scene.get("status", "ожидание")
            prompt = scene.get("prompt", "")
            self.tree.insert("", tk.END, iid=str(sid), values=(sid, stype, type_ru, tc, dur, frames, status, prompt))

    # -------------------------------------------------------------------------
    # Обработчики проверки и установки обновлений с GitHub
    # -------------------------------------------------------------------------
    def on_check_updates(self) -> None:
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
                        self.btn_install_update_settings.configure(state=tk.NORMAL)
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
                        self.btn_install_update_settings.configure(state=tk.DISABLED)

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
        self.btn_install_update_settings.configure(state=tk.DISABLED)

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
        threading.Thread(target=self.core.start_ace_server, kwargs={"log_cb": self.log}, daemon=True).start()

    def on_stop_ace(self) -> None:
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

    def on_browse_scene_image(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Выберите изображение для сцены",
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.webp"), ("Все файлы", "*.*")]
        )
        if file_path:
            self.edit_custom_img_var.set(file_path)
            self.on_save_scene_edits()

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
