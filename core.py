import os
import sys
import re
import json
import time
import math
import shutil
import urllib.request
import urllib.parse
import urllib.error
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Callable

# BUNDLE_DIR — для чтения вшитых в PyInstaller ресурсов (например, папки web)
BUNDLE_DIR: Path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

# APP_DIR — для записи и чтения изменяемых данных рядом с .exe (config.json и папка projects)
APP_DIR: Path = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)

CONFIG_PATH: Path = APP_DIR / "config.json"
PROJECTS_ROOT: Path = APP_DIR / "projects"

DEFAULT_CONFIG: Dict[str, Any] = {
    "ace_dir": r"C:\AI\ACE-Step-1.5",
    "comfy_root": r"C:\AI\ComfyUI_windows_portable",
    "workflow_lipsync": r"C:\AI\wan2.2_s2v_api.json",
    "workflow_broll": r"C:\AI\wan2.2_i2v_api.json",
    "ace_url": "http://127.0.0.1:8001",
    "comfy_urls": ["http://127.0.0.1:8188", "http://127.0.0.1:8189"],
    "lowvram": False,
    "reserve_vram": 2.0,
    "fps": 24,
    "default_scene_duration": 5.0,
    "skip_completed": True
}

SCENE_TYPE_LABELS: Dict[str, str] = {
    "lip-sync": "Синхронизация губ (вокал)",
    "b-roll": "Перебивка / атмосфера (B-Roll)",
    "action": "Динамичная сцена (Action)",
    "outro": "Финал (Outro)"
}

STORYBOARD_PRESETS: Dict[str, List[Dict[str, str]]] = {
    "cyber_cat": [
        {
            "type": "lip-sync",
            "prompt": "Medium close-up of a charismatic anthropomorphic ginger tabby cat wearing a vintage leather jacket and neon headphones, singing emotionally into a studio condenser microphone, expressive mouth movement, cinematic studio lighting, shallow depth of field, 4k"
        },
        {
            "type": "b-roll",
            "prompt": "Wide cinematic shot of a rain-slicked cyberpunk Tokyo alley at night, glowing neon reflections on wet asphalt, steam rising from vents, atmospheric fog, moody blue and magenta lighting, no characters, 4k"
        },
        {
            "type": "lip-sync",
            "prompt": "Close-up portrait of the ginger tabby cat singing passionately on a rooftop stage, neon city skyline bokeh in background, expressive facial animation and lip sync, dramatic rim light"
        },
        {
            "type": "action",
            "prompt": "Dynamic tracking shot of a sleek futuristic motorcycle speeding through a neon-lit highway tunnel, motion blur, sparks and light trails, high-octane cinematic action"
        },
        {
            "type": "b-roll",
            "prompt": "Macro shot of vintage analog synthesizer keys and glowing vacuum tubes pulsing to music rhythm, warm amber studio lighting, shallow focus"
        },
        {
            "type": "outro",
            "prompt": "Slow pull-back wide shot of the neon city skyline at dawn, soft golden sunlight breaking through dark clouds over calm ocean water, cinematic fade out"
        }
    ],
    "sea_voyage": [
        {
            "type": "lip-sync",
            "prompt": "Close-up of a rugged sea captain cat in a knitted fisherman sweater singing heartily on the wooden deck of a ship, wind ruffling fur, warm sunset lighting, natural lip synchronization"
        },
        {
            "type": "b-roll",
            "prompt": "Breathtaking aerial view of turquoise ocean waves crashing against dramatic basalt sea cliffs, golden hour sunlight, sea spray and foam, cinematic nature documentary style"
        },
        {
            "type": "action",
            "prompt": "Dynamic shot of a school of silver tuna leaping through crystal-clear ocean waves in slow motion, sunbeams piercing underwater, vibrant marine life"
        },
        {
            "type": "lip-sync",
            "prompt": "Medium shot of the captain cat at the ship helm singing with emotion, lantern light glowing in evening mist, expressive mouth movements, film grain"
        },
        {
            "type": "outro",
            "prompt": "Wide tranquil shot of a wooden sailboat silhouette gliding toward a glowing horizon under a starry night sky, calm sea reflections"
        }
    ]
}


class StudioCore:
    def __init__(self) -> None:
        self.config: Dict[str, Any] = dict(DEFAULT_CONFIG)
        PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
        self.ace_process: Optional[subprocess.Popen] = None
        self.comfy_processes: Dict[int, subprocess.Popen] = {}
        self.state: Dict[str, Any] = {
            "project_name": "default_project",
            "hero_image": "",
            "song_path": "",
            "song_duration": 0.0,
            "song_request": {
                "prompt": "upbeat synthwave pop, melodic female vocal, 120 bpm, emotional chorus",
                "lyrics": "[Verse 1]\nNeon lights across the bay\nChasing shadows far away\n\n[Chorus]\nWe are running through the night\nGlowing in electric light",
                "duration": 30.0,
                "seed": 42
            },
            "storyboard": []
        }
        self.load_config()
        self.open_project(self.state["project_name"])

    # -------------------------------------------------------------------------
    # Конфигурация и управление проектами
    # -------------------------------------------------------------------------
    def load_config(self) -> Dict[str, Any]:
        cfg = dict(DEFAULT_CONFIG)
        if CONFIG_PATH.exists():
            try:
                loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    cfg.update(loaded)
            except Exception:
                pass
        self.config = cfg
        self.save_config()
        return self.config

    def save_config(self, new_cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not hasattr(self, "config") or not isinstance(self.config, dict):
            self.config = dict(DEFAULT_CONFIG)
        if new_cfg is not None:
            self.config.update(new_cfg)
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(self.config, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        return self.config

    def get_project_dir(self, project_name: Optional[str] = None) -> Path:
        name = (project_name or self.state.get("project_name") or "default_project").strip()
        safe_name = re.sub(r'[<>:"/\\|?*]', "_", name)
        proj_dir = PROJECTS_ROOT / safe_name
        for sub in ("audio", "segments", "clips", "trimmed", "data", "output"):
            (proj_dir / sub).mkdir(parents=True, exist_ok=True)
        return proj_dir

    def list_projects(self) -> List[str]:
        if not PROJECTS_ROOT.exists():
            return []
        return sorted([d.name for d in PROJECTS_ROOT.iterdir() if d.is_dir()])

    def open_project(self, project_name: str, log_cb: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        proj_dir = self.get_project_dir(project_name)
        self.state["project_name"] = proj_dir.name

        # 1. Загрузка параметров песни (data/song_request.json)
        req_file = proj_dir / "data" / "song_request.json"
        if req_file.exists():
            try:
                req_data = json.loads(req_file.read_text(encoding="utf-8"))
                if isinstance(req_data, dict):
                    self.state["song_request"].update(req_data)
                    if "hero_image" in req_data:
                        self.state["hero_image"] = req_data["hero_image"]
            except Exception as e:
                if log_cb:
                    log_cb(f"[WARN] Ошибка чтения song_request.json: {e}")

        # 2. Проверка аудиофайла (audio/song.mp3 или .wav)
        song_mp3 = proj_dir / "audio" / "song.mp3"
        song_wav = proj_dir / "audio" / "song.wav"
        if song_mp3.exists():
            self.state["song_path"] = str(song_mp3.resolve())
            self.state["song_duration"] = self.probe_audio_duration(self.state["song_path"])
        elif song_wav.exists():
            self.state["song_path"] = str(song_wav.resolve())
            self.state["song_duration"] = self.probe_audio_duration(self.state["song_path"])
        else:
            self.state["song_path"] = ""
            self.state["song_duration"] = 0.0

        # 3. Загрузка раскадровки (data/storyboard.json) и синхронизация со сгенерированными клипами
        sb_file = proj_dir / "data" / "storyboard.json"
        storyboard: List[Dict[str, Any]] = []
        if sb_file.exists():
            try:
                loaded_sb = json.loads(sb_file.read_text(encoding="utf-8"))
                if isinstance(loaded_sb, list):
                    storyboard = loaded_sb
            except Exception as e:
                if log_cb:
                    log_cb(f"[WARN] Ошибка чтения storyboard.json: {e}")

        for idx, scene in enumerate(storyboard):
            scene_id = scene.get("id", idx + 1)
            scene["id"] = scene_id
            stype = scene.get("type", "lip-sync")
            scene["type"] = stype
            scene["type_label"] = SCENE_TYPE_LABELS.get(stype, stype)

            clip_file = proj_dir / "clips" / f"scene_{scene_id:03d}.mp4"
            seg_file = proj_dir / "segments" / f"scene_{scene_id:03d}.wav"

            if seg_file.exists():
                scene["audio_segment"] = str(seg_file.resolve())

            if clip_file.exists() and clip_file.stat().st_size > 1024:
                scene["clip_path"] = str(clip_file.resolve())
                scene["status"] = "готово"
            else:
                scene["clip_path"] = ""
                if scene.get("status") == "готово":
                    scene["status"] = "ожидание"

        self.state["storyboard"] = storyboard
        self.save_storyboard(storyboard)
        if log_cb:
            log_cb(
                f"[INFO] Открыт проект '{proj_dir.name}': длительность трека {self.state['song_duration']:.2f} сек, "
                f"сцен в раскадровке: {len(storyboard)}"
            )
        return self.state

    def save_song_request(self, song_request: Dict[str, Any], hero_image: Optional[str] = None) -> None:
        self.state["song_request"].update(song_request)
        if hero_image is not None:
            self.state["hero_image"] = hero_image
        proj_dir = self.get_project_dir()
        payload = dict(self.state["song_request"])
        payload["hero_image"] = self.state.get("hero_image", "")
        (proj_dir / "data" / "song_request.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def save_storyboard(self, storyboard: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        if storyboard is not None:
            self.state["storyboard"] = storyboard
        for idx, scene in enumerate(self.state["storyboard"]):
            scene["id"] = idx + 1
            stype = scene.get("type", "lip-sync")
            scene["type_label"] = SCENE_TYPE_LABELS.get(stype, stype)
        proj_dir = self.get_project_dir()
        sb_path = proj_dir / "data" / "storyboard.json"
        sb_path.write_text(
            json.dumps(self.state["storyboard"], ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        return self.state["storyboard"]

    def update_scene(
        self,
        scene_id: int,
        prompt: Optional[str] = None,
        scene_type: Optional[str] = None,
        custom_image: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        for scene in self.state["storyboard"]:
            if int(scene.get("id", 0)) == int(scene_id):
                if prompt is not None:
                    scene["prompt"] = prompt.strip()
                if scene_type is not None and scene_type in SCENE_TYPE_LABELS:
                    scene["type"] = scene_type
                    scene["type_label"] = SCENE_TYPE_LABELS[scene_type]
                if custom_image is not None:
                    scene["custom_image"] = custom_image.strip()
                self.save_storyboard()
                return scene
        return None

    # -------------------------------------------------------------------------
    # HTTP-утилиты (стандартная библиотека urllib.request)
    # -------------------------------------------------------------------------
    def _http_json(
        self,
        url: str,
        method: str = "GET",
        payload: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        data_bytes = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data_bytes = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}

    def _http_download(self, url: str, dest: Path, timeout: float = 120.0) -> Path:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                shutil.copyfileobj(resp, f)
        return dest

    # -------------------------------------------------------------------------
    # Управление процессами: ACE-Step 1.5 и ComfyUI + VRAM менеджмент
    # -------------------------------------------------------------------------
    def start_ace_server(self, log_cb: Optional[Callable[[str], None]] = None) -> bool:
        ace_dir = Path(self.config.get("ace_dir", r"C:\AI\ACE-Step-1.5"))
        if not ace_dir.exists():
            if log_cb:
                log_cb(f"[ERROR] Папка ACE-Step не найдена: {ace_dir}")
            return False

        python_exe = ace_dir / "venv" / "Scripts" / "python.exe"
        if not python_exe.exists():
            python_exe = Path("python")

        cmd = [str(python_exe), "-m", "acestep.api_server", "--port", "8001"]
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        try:
            self.ace_process = subprocess.Popen(
                cmd,
                cwd=str(ace_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags
            )
            if log_cb:
                log_cb(f"[INFO] Запущен сервер ACE-Step 1.5 (PID={self.ace_process.pid})")
            return True
        except Exception as e:
            if log_cb:
                log_cb(f"[ERROR] Не удалось запустить ACE-Step: {e}")
            return False

    def stop_ace_server(self, log_cb: Optional[Callable[[str], None]] = None) -> bool:
        """
        Принудительно завершает дерево процессов сервера ACE-Step через taskkill /F /T /PID
        для гарантированного освобождения VRAM перед запуском рендера видео в ComfyUI.
        """
        killed = False
        if self.ace_process and self.ace_process.poll() is None:
            pid = self.ace_process.pid
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(pid)],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                else:
                    self.ace_process.kill()
                self.ace_process = None
                killed = True
                if log_cb:
                    log_cb(f"[INFO] Дерево процессов ACE-Step (PID {pid}) остановлено. VRAM освобождена.")
            except Exception as e:
                if log_cb:
                    log_cb(f"[WARN] Ошибка при остановке PID {pid}: {e}")

        # Дополнительно проверяем порт 8001 через netstat на Windows, если сервер был запущен извне
        if os.name == "nt" and not killed:
            try:
                out = subprocess.check_output(["netstat", "-ano"], text=True, errors="ignore")
                for line in out.splitlines():
                    if ":8001 " in line and "LISTENING" in line:
                        parts = line.split()
                        ext_pid = parts[-1]
                        if ext_pid.isdigit() and int(ext_pid) > 0:
                            subprocess.run(
                                ["taskkill", "/F", "/T", "/PID", ext_pid],
                                capture_output=True,
                                text=True,
                                check=False
                            )
                            killed = True
                            if log_cb:
                                log_cb(f"[INFO] Внешний процесс ACE-Step на порту 8001 (PID {ext_pid}) остановлено.")
            except Exception:
                pass

        if not killed and log_cb:
            log_cb("[INFO] Активных процессов ACE-Step не обнаружено.")
        return killed

    def build_comfy_launch_args(self, port: int = 8188, gpu_id: int = 0) -> List[str]:
        comfy_root = Path(self.config.get("comfy_root", r"C:\AI\ComfyUI_windows_portable"))
        python_exe = comfy_root / "python_embeded" / "python.exe"
        main_py = comfy_root / "ComfyUI" / "main.py"

        cmd = [
            str(python_exe),
            "-s",
            str(main_py),
            "--windows-standalone-build",
            "--listen",
            "127.0.0.1",
            "--port",
            str(port),
            "--cuda-device",
            str(gpu_id)
        ]
        if bool(self.config.get("lowvram", False)):
            cmd.append("--lowvram")

        reserve_vram = float(self.config.get("reserve_vram", 0.0) or 0.0)
        if reserve_vram > 0:
            cmd.extend(["--reserve-vram", str(reserve_vram)])
        return cmd

    def start_comfy_server(self, port: int = 8188, gpu_id: int = 0, log_cb: Optional[Callable[[str], None]] = None) -> bool:
        comfy_root = Path(self.config.get("comfy_root", r"C:\AI\ComfyUI_windows_portable"))
        if not comfy_root.exists():
            if log_cb:
                log_cb(f"[ERROR] Папка ComfyUI не найдена: {comfy_root}")
            return False
        cmd = self.build_comfy_launch_args(port=port, gpu_id=gpu_id)
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(comfy_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            self.comfy_processes[port] = proc
            if log_cb:
                log_cb(f"[INFO] Запущен ComfyUI на порту {port} (GPU {gpu_id}): {' '.join(cmd)}")
            return True
        except Exception as e:
            if log_cb:
                log_cb(f"[ERROR] Не удалось запустить ComfyUI ({port}): {e}")
            return False

    def get_online_comfy_servers(self, log_cb: Optional[Callable[[str], None]] = None) -> List[Dict[str, Any]]:
        """
        Опрашивает все URL из comfy_urls (8188, 8189) через /system_stats и возвращает список
        реально доступных серверов вместе с информацией о GPU и свободной VRAM.
        """
        urls = self.config.get("comfy_urls", ["http://127.0.0.1:8188", "http://127.0.0.1:8189"])
        online: List[Dict[str, Any]] = []
        for raw_url in urls:
            base_url = raw_url.rstrip("/")
            try:
                stats = self._http_json(f"{base_url}/system_stats", method="GET", timeout=3.0)
                devices = stats.get("devices", [])
                dev_info = devices[0] if devices else {}
                vram_total_gb = round(dev_info.get("vram_total", 0) / (1024 ** 3), 2)
                vram_free_gb = round(dev_info.get("vram_free", 0) / (1024 ** 3), 2)
                gpu_name = dev_info.get("name", "GPU")
                online.append({
                    "url": base_url,
                    "gpu_name": gpu_name,
                    "vram_total_gb": vram_total_gb,
                    "vram_free_gb": vram_free_gb
                })
                if log_cb:
                    log_cb(
                        f"[GPU] Сервер {base_url} ОНЛАЙН — {gpu_name} "
                        f"(Свободно VRAM: {vram_free_gb} / {vram_total_gb} ГБ)"
                    )
            except Exception:
                if log_cb:
                    log_cb(f"[GPU] Сервер {base_url} недоступен (офлайн).")
        return online

    # -------------------------------------------------------------------------
    # ACE-Step 1.5 API: Генерация текста (/format_input) и песни (/release_task)
    # -------------------------------------------------------------------------
    def generate_lyrics_ace(
        self,
        music_prompt: str,
        lyrics_hint: str = "",
        log_cb: Optional[Callable[[str], None]] = None
    ) -> Dict[str, str]:
        ace_url = self.config.get("ace_url", "http://127.0.0.1:8001").rstrip("/")
        payload = {
            "model": "acestep-5Hz-lm-0.6B",
            "prompt": music_prompt.strip(),
            "lyrics": lyrics_hint.strip()
        }
        if log_cb:
            log_cb("[ACE] Запрос генерации/форматирования текста через /format_input (acestep-5Hz-lm-0.6B)...")
        resp = self._http_json(f"{ace_url}/format_input", method="POST", payload=payload, timeout=90.0)
        data = resp.get("data", resp) if isinstance(resp, dict) else {}
        formatted_prompt = data.get("prompt") or data.get("caption") or music_prompt
        formatted_lyrics = data.get("lyrics") or lyrics_hint
        self.save_song_request({"prompt": formatted_prompt, "lyrics": formatted_lyrics})
        if log_cb:
            log_cb("[ACE] Текст песни и теги стиля успешно получены.")
        return {"prompt": formatted_prompt, "lyrics": formatted_lyrics}

    def generate_song_ace(
        self,
        prompt: str,
        lyrics: str,
        duration: float = 30.0,
        seed: int = 42,
        log_cb: Optional[Callable[[str], None]] = None
    ) -> str:
        ace_url = self.config.get("ace_url", "http://127.0.0.1:8001").rstrip("/")
        proj_dir = self.get_project_dir()
        self.save_song_request({
            "prompt": prompt,
            "lyrics": lyrics,
            "duration": float(duration),
            "seed": int(seed)
        })

        payload = {
            "model": "acestep-v15-turbo",
            "prompt": prompt,
            "lyrics": lyrics,
            "audio_duration": float(duration),
            "duration": float(duration),
            "seed": int(seed),
            "output_format": "mp3"
        }
        if log_cb:
            log_cb(f"[ACE] Отправка задачи в /release_task (модель acestep-v15-turbo, {duration} сек)...")

        release_resp = self._http_json(f"{ace_url}/release_task", method="POST", payload=payload, timeout=60.0)
        data_block = release_resp.get("data", release_resp) if isinstance(release_resp, dict) else {}
        task_id = (
            data_block.get("task_id")
            or release_resp.get("task_id")
            or data_block.get("id")
        )
        if not task_id:
            raise RuntimeError(f"ACE-Step не вернул task_id: {release_resp}")

        if log_cb:
            log_cb(f"[ACE] Задача создана: task_id={task_id}. Ожидание результата через /query_result...")

        audio_source = ""
        for _ in range(180):
            time.sleep(2.0)
            try:
                q_resp = self._http_json(
                    f"{ace_url}/query_result",
                    method="POST",
                    payload={"task_id": task_id, "task_id_list": [task_id]},
                    timeout=30.0
                )
            except urllib.error.HTTPError:
                q_resp = self._http_json(
                    f"{ace_url}/query_result?task_id={urllib.parse.quote(str(task_id))}",
                    method="GET",
                    timeout=30.0
                )

            item = q_resp.get("data", q_resp)
            if isinstance(item, list) and item:
                item = item[0]
            if isinstance(item, dict):
                status = str(item.get("status", "")).lower()
                if status in ("succeeded", "success", "completed", "done", "1") or item.get("audio_path") or item.get("file_path") or item.get("url"):
                    audio_source = (
                        item.get("audio_path")
                        or item.get("file_path")
                        or item.get("url")
                        or item.get("output")
                        or ""
                    )
                    if isinstance(audio_source, list) and audio_source:
                        audio_source = audio_source[0]
                    if audio_source:
                        break
                elif status in ("failed", "error", "-1"):
                    raise RuntimeError(f"Ошибка рендера ACE-Step: {item}")

        if not audio_source:
            raise RuntimeError("Превышено время ожидания генерации трека в ACE-Step.")

        dest_song = proj_dir / "audio" / "song.mp3"
        if str(audio_source).startswith("http://") or str(audio_source).startswith("https://"):
            self._http_download(str(audio_source), dest_song)
        elif Path(str(audio_source)).exists():
            shutil.copy2(str(audio_source), dest_song)
        else:
            dl_url = f"{ace_url}/file?path={urllib.parse.quote(str(audio_source))}"
            self._http_download(dl_url, dest_song)

        self.set_song_file(str(dest_song.resolve()), copy_to_project=False, log_cb=log_cb)
        return str(dest_song.resolve())

    # -------------------------------------------------------------------------
    # FFprobe / FFmpeg: Точная длительность, нарезка 16kHz mono WAV и сборка
    # -------------------------------------------------------------------------
    def probe_audio_duration(self, audio_path: str) -> float:
        """
        Определяет точную длительность аудиофайла в секундах через ffprobe,
        а при отсутствии ffprobe парсит вывод `ffmpeg -i`.
        """
        path_obj = Path(audio_path)
        if not path_obj.exists():
            return 0.0

        # Способ 1: ffprobe
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path_obj)
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if proc.returncode == 0 and proc.stdout.strip():
                val = float(proc.stdout.strip())
                if val > 0:
                    return round(val, 4)
        except Exception:
            pass

        # Способ 2: парсинг вывода ffmpeg -i
        try:
            proc = subprocess.run(["ffmpeg", "-i", str(path_obj)], capture_output=True, text=True, timeout=15)
            output = (proc.stderr or "") + "\n" + (proc.stdout or "")
            match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", output)
            if match:
                hours = int(match.group(1))
                minutes = int(match.group(2))
                seconds = float(match.group(3))
                return round(hours * 3600 + minutes * 60 + seconds, 4)
        except Exception:
            pass

        return 0.0

    def set_song_file(
        self,
        source_path: str,
        copy_to_project: bool = True,
        log_cb: Optional[Callable[[str], None]] = None
    ) -> Tuple[str, float]:
        src = Path(source_path)
        if not src.exists():
            raise FileNotFoundError(f"Аудиофайл не найден: {source_path}")

        proj_dir = self.get_project_dir()
        dest = proj_dir / "audio" / "song.mp3"
        if copy_to_project and src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
            final_path = dest.resolve()
        else:
            final_path = src.resolve()

        duration = self.probe_audio_duration(str(final_path))
        self.state["song_path"] = str(final_path)
        self.state["song_duration"] = duration
        self.state["song_request"]["duration"] = duration
        self.save_song_request(self.state["song_request"])

        if log_cb:
            log_cb(f"[AUDIO] Загружен файл {final_path.name} — точная длительность: {duration:.3f} сек.")
        return str(final_path), duration

    def generate_storyboard_from_preset(
        self,
        preset_name: str = "cyber_cat",
        scene_duration: Optional[float] = None,
        log_cb: Optional[Callable[[str], None]] = None
    ) -> List[Dict[str, Any]]:
        templates = STORYBOARD_PRESETS.get(preset_name) or STORYBOARD_PRESETS["cyber_cat"]
        base_dur = float(scene_duration or self.config.get("default_scene_duration", 5.0))
        if base_dur <= 0:
            base_dur = 5.0

        total_dur = float(self.state.get("song_duration") or self.state["song_request"].get("duration") or 30.0)
        if self.state.get("song_path") and Path(self.state["song_path"]).exists():
            probed = self.probe_audio_duration(self.state["song_path"])
            if probed > 0:
                total_dur = probed
                self.state["song_duration"] = probed

        proj_dir = self.get_project_dir()
        storyboard: List[Dict[str, Any]] = []
        cursor = 0.0
        idx = 1

        while cursor < total_dur - 0.05:
            remaining = round(total_dur - cursor, 4)
            dur = round(min(base_dur, remaining), 4)
            # Если последний остаток меньше 1.2 сек и уже есть сцены — присоединяем его к предыдущей сцене
            if dur < 1.2 and storyboard:
                storyboard[-1]["duration"] = round(storyboard[-1]["duration"] + dur, 4)
                storyboard[-1]["end"] = round(cursor + dur, 4)
                break

            tpl = templates[(idx - 1) % len(templates)]
            stype = tpl["type"]
            # Помечаем финальную сцену как outro, если это конец песни
            if cursor + dur >= total_dur - 0.05 and idx > 2:
                stype = "outro"

            clip_path = proj_dir / "clips" / f"scene_{idx:03d}.mp4"
            seg_path = proj_dir / "segments" / f"scene_{idx:03d}.wav"
            is_ready = clip_path.exists() and clip_path.stat().st_size > 1024

            storyboard.append({
                "id": idx,
                "type": stype,
                "type_label": SCENE_TYPE_LABELS.get(stype, stype),
                "start": round(cursor, 4),
                "end": round(cursor + dur, 4),
                "duration": dur,
                "prompt": tpl["prompt"],
                "custom_image": "",
                "audio_segment": str(seg_path.resolve()) if seg_path.exists() else "",
                "clip_path": str(clip_path.resolve()) if is_ready else "",
                "status": "готово" if is_ready else "ожидание"
            })
            cursor = round(cursor + dur, 4)
            idx += 1

        self.save_storyboard(storyboard)
        if log_cb:
            log_cb(f"[STORYBOARD] Сформирована раскадровка ({len(storyboard)} сцен на {total_dur:.2f} сек).")
        return storyboard

    def slice_audio_segments(self, log_cb: Optional[Callable[[str], None]] = None) -> List[str]:
        """
        Нарезает исходный трек на сегменты строго по таймкодам раскадровки
        в формате 16kHz, mono, PCM S16LE WAV для модели Wan2.2 S2V.
        """
        song_path = self.state.get("song_path", "")
        if not song_path or not Path(song_path).exists():
            raise FileNotFoundError("Аудиофайл песни не выбран или не существует.")

        if not self.state.get("storyboard"):
            self.generate_storyboard_from_preset(log_cb=log_cb)

        proj_dir = self.get_project_dir()
        seg_dir = proj_dir / "segments"
        seg_dir.mkdir(parents=True, exist_ok=True)
        created_files: List[str] = []

        for scene in self.state["storyboard"]:
            sid = int(scene["id"])
            start = float(scene["start"])
            duration = float(scene["duration"])
            out_wav = seg_dir / f"scene_{sid:03d}.wav"

            cmd = [
                "ffmpeg", "-y",
                "-ss", f"{start:.4f}",
                "-t", f"{duration:.4f}",
                "-i", str(song_path),
                "-vn",
                "-ac", "1",
                "-ar", "16000",
                "-c:a", "pcm_s16le",
                str(out_wav)
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(f"Ошибка нарезки аудио для сцены #{sid}: {proc.stderr}")

            scene["audio_segment"] = str(out_wav.resolve())
            created_files.append(str(out_wav.resolve()))
            if log_cb:
                log_cb(f"[FFMPEG] Аудиосегмент сцены #{sid:03d}: {start:.2f}s - {start + duration:.2f}s -> {out_wav.name}")

        self.save_storyboard()
        return created_files

    # -------------------------------------------------------------------------
    # ComfyUI Workflow: разделение lip-sync / b-roll и формула кадров 4k + 1
    # -------------------------------------------------------------------------
    @staticmethod
    def calculate_wan_frames(duration_sec: float, fps: int = 24) -> int:
        """
        Вычисляет количество кадров для моделей семейства Wan по формуле 4k + 1.
        Гарантирует, что длительность сгенерированного фрагмента >= duration_sec,
        чтобы при финальной сборке обрезать лишний 1 кадр без потери синхронизации.
        """
        raw_frames = max(17, int(math.ceil(duration_sec * fps)))
        k = int(math.ceil((raw_frames - 1) / 4.0))
        return 4 * k + 1

    def prepare_workflow(self, scene: Dict[str, Any], seed: Optional[int] = None) -> Dict[str, Any]:
        """
        Готовит JSON-схему ComfyUI API для конкретной сцены:
        - Для `lip-sync` использует workflow_lipsync, передаёт портрет героя в LoadImage и WAV-сегмент в LoadAudio.
        - Для `b-roll` / `action` / `outro` использует workflow_broll (если указан и существует) или общий шаблон,
          но НЕ подставляет портрет героя (если не задана своя картинка сцены) и обнуляет влияние аудио/вокала,
          чтобы нейросеть не пыталась анимировать губы кота на морских волнах, пейзажах и тунце.
        - Ищет узлы как по `class_type`, так и безопасно по `_meta.title` без хрупких магических чисел.
        """
        scene_type = scene.get("type", "lip-sync")
        lipsync_path = Path(self.config.get("workflow_lipsync", r"C:\AI\wan2.2_s2v_api.json"))
        broll_path_str = str(self.config.get("workflow_broll", "")).strip()
        broll_path = Path(broll_path_str) if broll_path_str else lipsync_path

        if scene_type == "lip-sync":
            wf_path = lipsync_path
        else:
            wf_path = broll_path if (broll_path.exists() and broll_path.is_file()) else lipsync_path

        if not wf_path.exists():
            raise FileNotFoundError(f"Файл шаблона ComfyUI не найден: {wf_path}")

        workflow: Dict[str, Any] = json.loads(wf_path.read_text(encoding="utf-8"))
        fps = int(self.config.get("fps", 24))
        wan_frames = self.calculate_wan_frames(float(scene.get("duration", 5.0)), fps=fps)
        actual_seed = int(seed if seed is not None else (int(time.time() * 1000) % 2147483647))

        hero_img = str(self.state.get("hero_image", "")).strip()
        scene_custom_img = str(scene.get("custom_image", "")).strip()
        audio_seg = str(scene.get("audio_segment", "")).strip()
        prompt_text = str(scene.get("prompt", "")).strip()

        nodes_to_remove: List[str] = []

        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            class_type = str(node.get("class_type", ""))
            class_lower = class_type.lower()
            meta_title = str(node.get("_meta", {}).get("title", "")).lower()
            inputs = node.get("inputs", {})
            if not isinstance(inputs, dict):
                continue

            # 1. Текстовый промпт (позитивный)
            is_negative = any(w in meta_title for w in ("negative", "негатив", "neg"))
            if ("cliptextencode" in class_lower or "textencode" in class_lower or "wanvideotextencode" in class_lower) and not is_negative:
                if "positive_prompt" in inputs:
                    inputs["positive_prompt"] = prompt_text
                elif "text" in inputs and isinstance(inputs["text"], str):
                    inputs["text"] = prompt_text
                elif "prompt" in inputs and isinstance(inputs["prompt"], str):
                    inputs["prompt"] = prompt_text

            # 2. Загрузка изображения (LoadImage)
            if class_type in ("LoadImage", "VHS_LoadImagePath") or "load image" in meta_title or "loadimage" in class_lower:
                if scene_type == "lip-sync":
                    target_img = scene_custom_img or hero_img
                    if target_img:
                        if "image" in inputs:
                            inputs["image"] = target_img
                        elif "image_path" in inputs:
                            inputs["image_path"] = target_img
                else:
                    # Для b-roll / action / outro: подставляем только если для сцены явно задана своя картинка
                    if scene_custom_img:
                        if "image" in inputs:
                            inputs["image"] = scene_custom_img
                        elif "image_path" in inputs:
                            inputs["image_path"] = scene_custom_img

            # 3. Загрузка и влияние аудио (LoadAudio / WanSoundToVideo)
            is_audio_loader = (
                class_type in ("LoadAudio", "VHS_LoadAudio", "VHS_LoadAudioUpload", "DownloadAndLoadWav2VecModel")
                or "load audio" in meta_title
                or "loadaudio" in class_lower
            )
            if is_audio_loader:
                if scene_type == "lip-sync" and audio_seg:
                    for key in ("audio", "audio_file", "file", "path"):
                        if key in inputs:
                            inputs[key] = audio_seg
                elif scene_type != "lip-sync":
                    # Отключаем влияние вокала на пейзажи и перебивки в общем S2V-шаблоне
                    for weight_key in ("audio_scale", "audio_weight", "strength", "vocal_weight", "scale"):
                        if weight_key in inputs and isinstance(inputs[weight_key], (int, float)):
                            inputs[weight_key] = 0.0

            # Если это узел S2V conditioning / embedder, при b-roll обнуляем силу аудио-синхронизации
            if scene_type != "lip-sync" and any(k in class_lower or k in meta_title for k in ("s2v", "sound", "audio", "wav2vec", "fantasytalking", "sonic")):
                for weight_key in ("audio_scale", "audio_cfg", "audio_weight", "strength", "scale"):
                    if weight_key in inputs and isinstance(inputs[weight_key], (int, float)):
                        inputs[weight_key] = 0.0

            # 4. Количество кадров (формула 4k + 1) и FPS по ключам и _meta.title
            for frame_key in ("length", "num_frames", "frames", "frame_count", "video_length"):
                if frame_key in inputs and isinstance(inputs[frame_key], (int, float)):
                    inputs[frame_key] = wan_frames

            for fps_key in ("frame_rate", "fps"):
                if fps_key in inputs and isinstance(inputs[fps_key], (int, float)):
                    inputs[fps_key] = fps

            # 5. Seed генерации
            for seed_key in ("seed", "noise_seed"):
                if seed_key in inputs and isinstance(inputs[seed_key], (int, float)):
                    inputs[seed_key] = actual_seed

            # 6. Имя выходного файла
            if "filename_prefix" in inputs:
                inputs["filename_prefix"] = f"mvs_scene_{int(scene['id']):03d}"

        for nid in nodes_to_remove:
            workflow.pop(nid, None)

        return workflow

    # -------------------------------------------------------------------------
    # Отправка и ожидание рендера сцены в ComfyUI
    # -------------------------------------------------------------------------
    def render_single_scene(
        self,
        scene_id: int,
        server_url: Optional[str] = None,
        log_cb: Optional[Callable[[str], None]] = None
    ) -> str:
        scene = next((s for s in self.state["storyboard"] if int(s["id"]) == int(scene_id)), None)
        if not scene:
            raise ValueError(f"Сцена #{scene_id} не найдена в раскадровке.")

        if not server_url:
            online = self.get_online_comfy_servers(log_cb=log_cb)
            if not online:
                raise RuntimeError("Ни один сервер ComfyUI (8188/8189) не отвечает.")
            server_url = online[0]["url"]

        server_url = server_url.rstrip("/")

        # Если для lip-sync сцены ещё не нарезан WAV-сегмент, нарезаем автоматически
        if scene.get("type") == "lip-sync":
            seg_path = scene.get("audio_segment", "")
            if not seg_path or not Path(seg_path).exists():
                if self.state.get("song_path") and Path(self.state["song_path"]).exists():
                    self.slice_audio_segments(log_cb=log_cb)

        workflow = self.prepare_workflow(scene)
        scene["status"] = "рендер"
        self.save_storyboard()

        if log_cb:
            log_cb(
                f"[COMFY] Отправка сцены #{scene_id:03d} ({scene.get('type')}, {scene.get('duration')}s) "
                f"на сервер {server_url}..."
            )

        resp = self._http_json(
            f"{server_url}/prompt",
            method="POST",
            payload={"prompt": workflow},
            timeout=30.0
        )
        prompt_id = resp.get("prompt_id")
        if not prompt_id:
            scene["status"] = "ошибка"
            self.save_storyboard()
            raise RuntimeError(f"ComfyUI не вернул prompt_id: {resp}")

        # Поллинг /history/<prompt_id>
        output_file_info: Optional[Dict[str, str]] = None
        for _ in range(900):
            time.sleep(2.0)
            hist = self._http_json(f"{server_url}/history/{prompt_id}", method="GET", timeout=15.0)
            if prompt_id in hist:
                entry = hist[prompt_id]
                outputs = entry.get("outputs", {})
                for _node_id, node_out in outputs.items():
                    for key in ("gifs", "videos", "images"):
                        items = node_out.get(key, [])
                        for item in items:
                            fname = str(item.get("filename", ""))
                            if fname.lower().endswith((".mp4", ".webm", ".mov", ".gif")):
                                output_file_info = {
                                    "filename": fname,
                                    "subfolder": str(item.get("subfolder", "")),
                                    "type": str(item.get("type", "output"))
                                }
                                break
                        if output_file_info:
                            break
                    if output_file_info:
                        break
                if output_file_info:
                    break

        if not output_file_info:
            scene["status"] = "ошибка"
            self.save_storyboard()
            raise RuntimeError(f"Таймаут ожидания рендера сцены #{scene_id} на {server_url}")

        query = urllib.parse.urlencode(output_file_info)
        view_url = f"{server_url}/view?{query}"
        proj_dir = self.get_project_dir()
        clip_dest = proj_dir / "clips" / f"scene_{int(scene_id):03d}.mp4"
        self._http_download(view_url, clip_dest)

        scene["clip_path"] = str(clip_dest.resolve())
        scene["status"] = "готово"
        self.save_storyboard()

        if log_cb:
            log_cb(f"[COMFY] Сцена #{scene_id:03d} успешно сохранена: {clip_dest.name}")
        return str(clip_dest.resolve())

    def queue_all_scenes(
        self,
        skip_completed: Optional[bool] = None,
        log_cb: Optional[Callable[[str], None]] = None
    ) -> List[str]:
        """
        Проверяет через /system_stats доступные серверы ComfyUI (8188, 8189).
        - Если онлайн 1 сервер (1 GPU): направляет все сцены в один поток (шаг 1).
        - Если онлайн оба сервера (2 GPU): распределяет задачи параллельно в 2 потока (шаг 2).
        - Пропускает сцены со статусом 'готово' и физически существующим MP4 при skip_completed=True.
        """
        import concurrent.futures

        if skip_completed is None:
            skip_completed = bool(self.config.get("skip_completed", True))

        online_servers = self.get_online_comfy_servers(log_cb=log_cb)
        if not online_servers:
            raise RuntimeError("Ни один сервер ComfyUI (8188, 8189) не запущен.")

        pending_scenes: List[Dict[str, Any]] = []
        for scene in self.state["storyboard"]:
            clip_p = Path(scene.get("clip_path", "")) if scene.get("clip_path") else None
            if skip_completed and scene.get("status") == "готово" and clip_p and clip_p.exists() and clip_p.stat().st_size > 1024:
                if log_cb:
                    log_cb(f"[SKIP] Сцена #{int(scene['id']):03d} уже готова ({clip_p.name}), пропускаем.")
                continue
            pending_scenes.append(scene)

        if not pending_scenes:
            if log_cb:
                log_cb("[QUEUE] Все сцены уже отрендерены.")
            return [s.get("clip_path", "") for s in self.state["storyboard"] if s.get("clip_path")]

        num_servers = len(online_servers)
        if log_cb:
            mode_desc = (
                f"1 GPU ({online_servers[0]['url']}) — последовательный поток (шаг 1)"
                if num_servers == 1
                else f"{num_servers} GPU — параллельное распределение (шаг {num_servers})"
            )
            log_cb(f"[QUEUE] К рендеру: {len(pending_scenes)} сцен. Режим: {mode_desc}")

        rendered_paths: List[str] = []
        if num_servers == 1:
            srv_url = online_servers[0]["url"]
            for sc in pending_scenes:
                path = self.render_single_scene(int(sc["id"]), server_url=srv_url, log_cb=log_cb)
                rendered_paths.append(path)
        else:
            def _worker(server_info: Dict[str, Any], scenes_slice: List[Dict[str, Any]]) -> List[str]:
                out: List[str] = []
                for sc in scenes_slice:
                    p = self.render_single_scene(int(sc["id"]), server_url=server_info["url"], log_cb=log_cb)
                    out.append(p)
                return out

            with concurrent.futures.ThreadPoolExecutor(max_workers=num_servers) as executor:
                futures = []
                for idx, srv in enumerate(online_servers):
                    slice_for_gpu = pending_scenes[idx::num_servers]
                    if slice_for_gpu:
                        futures.append(executor.submit(_worker, srv, slice_for_gpu))
                for fut in concurrent.futures.as_completed(futures):
                    rendered_paths.extend(fut.result())

        return rendered_paths

    # -------------------------------------------------------------------------
    # Финальная сборка клипа с устранением рассинхрона (Lip-Sync Drift Fix)
    # -------------------------------------------------------------------------
    def assemble_video(self, output_name: str = "final_music_video.mp4", log_cb: Optional[Callable[[str], None]] = None) -> str:
        """
        Устраняет рассинхрон звука и видео (Lip-Sync Drift от лишнего кадра 4k + 1 в Wan2.2):
        1. Каждая готовая сцена перед склейкой обрезается строго до `scene['duration']` при `-r 24`.
        2. Выполняется конкатенация выровненных фрагментов и наложение исходного трека
           с параметрами: -c:v libx264 -preset fast -crf 18 -r 24 -pix_fmt yuv420p -c:a aac -b:a 192k -shortest
        """
        proj_dir = self.get_project_dir()
        trimmed_dir = proj_dir / "trimmed"
        trimmed_dir.mkdir(parents=True, exist_ok=True)

        storyboard = self.state.get("storyboard", [])
        if not storyboard:
            raise RuntimeError("Раскадровка пуста.")

        song_path = self.state.get("song_path", "")
        if not song_path or not Path(song_path).exists():
            raise FileNotFoundError("Исходный аудиофайл песни не найден для финальной склейки.")

        fps = int(self.config.get("fps", 24))
        concat_lines: List[str] = []

        for scene in storyboard:
            sid = int(scene["id"])
            raw_clip = Path(scene.get("clip_path") or (proj_dir / "clips" / f"scene_{sid:03d}.mp4"))
            if not raw_clip.exists():
                raise FileNotFoundError(f"Видеофайл сцены #{sid:03d} не найден: {raw_clip}")

            exact_dur = float(scene["duration"])
            trimmed_clip = trimmed_dir / f"trimmed_{sid:03d}.mp4"

            # Нормализация и точная подрезка до расчётной длительности сцены (-t {scene['duration']} -r 24)
            trim_cmd = [
                "ffmpeg", "-y",
                "-i", str(raw_clip),
                "-t", f"{exact_dur:.4f}",
                "-r", str(fps),
                "-an",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                str(trimmed_clip)
            ]
            proc = subprocess.run(trim_cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(f"Ошибка подрезки сцены #{sid:03d}: {proc.stderr}")

            escaped_path = str(trimmed_clip.resolve()).replace("'", "'\\''")
            concat_lines.append(f"file '{escaped_path}'")
            if log_cb:
                log_cb(f"[SYNC] Сцена #{sid:03d} выровнена строго до {exact_dur:.3f} сек ({fps} FPS).")

        concat_list_path = trimmed_dir / "concat_list.txt"
        concat_list_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

        final_mp4 = proj_dir / "output" / output_name
        assemble_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list_path),
            "-i", str(song_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-r", "24",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(final_mp4)
        ]
        if log_cb:
            log_cb("[FFMPEG] Запуск финальной сборки клипа...")
        proc = subprocess.run(assemble_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"Ошибка финальной сборки MP4: {proc.stderr}")

        if log_cb:
            log_cb(f"[DONE] Финальный клип успешно собран: {final_mp4.resolve()}")
        return str(final_mp4.resolve())
