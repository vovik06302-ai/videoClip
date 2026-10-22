import os
import io
import sys
import re
import json
import time
import math
import base64
import shutil
import hashlib
import threading
import tempfile
import urllib.request
import urllib.parse
import urllib.error
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Callable

APP_VERSION = "1.0.0"
GITHUB_REPO = "vovik06302-ai/videoClip"

# BUNDLE_DIR — для чтения вшитых в PyInstaller ресурсов (например, папки web)
BUNDLE_DIR: Path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

# APP_DIR — папка, где находится сам исполняемый .exe (или core.py)
APP_DIR: Path = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)


def _resolve_writable_data_dir() -> Path:
    """
    Проверяет наличие прав на запись в APP_DIR (путём os.access и пробного создания временного файла).
    Если программа установлена в защищённую системную директорию (например, C:\\Program Files)
    и запись запрещена (PermissionError), автоматически переключается на пользовательскую папку
    %LOCALAPPDATA%\\MusicVideoStudio.
    """
    if os.access(APP_DIR, os.W_OK):
        test_file = APP_DIR / f".write_test_{os.getpid()}.tmp"
        try:
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink(missing_ok=True)
            return APP_DIR
        except (PermissionError, OSError):
            pass

    fallback_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "MusicVideoStudio"
    try:
        fallback_dir.mkdir(parents=True, exist_ok=True)
        return fallback_dir
    except Exception:
        temp_fallback = Path(tempfile.gettempdir()) / "MusicVideoStudio"
        temp_fallback.mkdir(parents=True, exist_ok=True)
        return temp_fallback


DATA_DIR: Path = _resolve_writable_data_dir()
CONFIG_FILE: Path = DATA_DIR / "config.json"
CONFIG_PATH: Path = CONFIG_FILE
PROJECTS_DIR: Path = DATA_DIR / "projects"
PROJECTS_ROOT: Path = PROJECTS_DIR

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
        try:
            PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            pass
        self.ace_process: Optional[subprocess.Popen] = None
        self.comfy_processes: Dict[int, subprocess.Popen] = {}
        # Отмена очереди рендера: текущая сцена дорендеривается, следующие не запускаются
        self.cancel_requested = threading.Event()
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
            "storyboard": [],
            "beat_boundaries": [],
            "queue_progress": {"total": 0, "done": 0, "failed": 0, "current": ""}
        }
        self.load_config()
        self.open_project(self.state["project_name"])
        if not self.state.get("storyboard"):
            self.generate_storyboard_from_preset("cyber_cat")

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
        global DATA_DIR, CONFIG_FILE, CONFIG_PATH, PROJECTS_DIR, PROJECTS_ROOT
        if not hasattr(self, "config") or not isinstance(self.config, dict):
            self.config = dict(DEFAULT_CONFIG)
        if new_cfg is not None:
            self.config.update(new_cfg)
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(
                json.dumps(self.config, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except PermissionError:
            # Аварийное переключение на %LOCALAPPDATA%\MusicVideoStudio при отказе в доступе
            fallback = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "MusicVideoStudio"
            try:
                fallback.mkdir(parents=True, exist_ok=True)
                DATA_DIR = fallback
                CONFIG_FILE = DATA_DIR / "config.json"
                CONFIG_PATH = CONFIG_FILE
                PROJECTS_DIR = DATA_DIR / "projects"
                PROJECTS_ROOT = PROJECTS_DIR
                PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
                CONFIG_PATH.write_text(
                    json.dumps(self.config, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
            except Exception:
                pass
        except OSError:
            pass
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

        # 3.1 Восстановление границ сцен по битам (data/beat_boundaries.json)
        beats_file = proj_dir / "data" / "beat_boundaries.json"
        boundaries: List[float] = []
        if beats_file.exists():
            try:
                bd = json.loads(beats_file.read_text(encoding="utf-8"))
                if isinstance(bd, dict) and isinstance(bd.get("boundaries"), list):
                    boundaries = [float(b) for b in bd["boundaries"]]
            except Exception as e:
                if log_cb:
                    log_cb(f"[WARN] Ошибка чтения beat_boundaries.json: {e}")
        self.state["beat_boundaries"] = boundaries

        self.save_storyboard(storyboard)
        if log_cb:
            log_cb(
                f"[INFO] Открыт проект '{proj_dir.name}': длительность трека {self.state['song_duration']:.2f} сек, "
                f"сцен в раскадровке: {len(storyboard)}"
            )
        return self.state

    # -------------------------------------------------------------------------
    # Загрузка файлов из веб-интерфейса (фото героя / аудио песни)
    # -------------------------------------------------------------------------
    ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
    ALLOWED_AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}

    def _save_upload_b64(
        self,
        file_b64: str,
        filename: str,
        subdir: str,
        allowed_exts: set,
        dest_name: str,
        max_bytes: int = 25 * 1024 * 1024,
        log_cb: Optional[Callable[[str], None]] = None
    ) -> str:
        """Сохраняет файл из base64 в папку проекта. Возвращает абсолютный путь."""
        raw_b64 = str(file_b64).strip()
        # Поддержка data:URL из input[type=file] (data:image/png;base64,....)
        if raw_b64.startswith("data:") and "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        try:
            data = base64.b64decode(raw_b64)
        except Exception as exc:
            raise ValueError(f"Некорректные данные файла (base64): {exc}")
        if not data:
            raise ValueError("Пустой файл.")
        if len(data) > max_bytes:
            raise ValueError(f"Файл слишком большой ({len(data) // (1024 * 1024)} МБ, лимит {max_bytes // (1024 * 1024)} МБ).")

        ext = Path(str(filename)).suffix.lower()
        if ext not in allowed_exts:
            ext = ""
        proj_dir = self.get_project_dir()
        target_dir = proj_dir / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        dest = target_dir / f"{dest_name}{ext or ''}"
        dest.write_bytes(data)

        if log_cb:
            digest = hashlib.sha256(data).hexdigest()[:12]
            log_cb(f"[UPLOAD] {dest.name} ({len(data) / 1024:.1f} КБ, sha256:{digest}) сохранён в проект '{proj_dir.name}'.")
        return str(dest.resolve())

    def upload_hero_image(self, file_b64: str, filename: str, log_cb: Optional[Callable[[str], None]] = None) -> str:
        path = self._save_upload_b64(
            file_b64, filename, "assets", self.ALLOWED_IMAGE_EXTS,
            f"hero_{int(time.time())}", log_cb=log_cb
        )
        self.save_song_request(dict(self.state.get("song_request", {})), hero_image=path)
        if log_cb:
            log_cb("[UPLOAD] Изображение героя применено к сценам lip-sync.")
        return path

    def upload_song_audio(self, file_b64: str, filename: str, log_cb: Optional[Callable[[str], None]] = None) -> Tuple[str, float]:
        tmp_name = f"upload_{int(time.time())}"
        src_path = self._save_upload_b64(
            file_b64, filename, "audio", self.ALLOWED_AUDIO_EXTS,
            tmp_name, max_bytes=80 * 1024 * 1024, log_cb=log_cb
        )
        final_path, duration = self.set_song_file(src_path, copy_to_project=True, log_cb=log_cb)
        # Если расширение загруженного файла не mp3 — пересохраняем через ffmpeg в канонический song.mp3
        if Path(final_path).suffix.lower() != ".mp3" and self._ffmpeg_available():
            canonical = Path(final_path).parent / "song.mp3"
            try:
                subprocess.run(
                    [self._ffmpeg_bin(), "-y", "-i", final_path, "-vn", "-acodec", "libmp3lame", "-q:a", "2", str(canonical)],
                    capture_output=True, timeout=300
                )
                if canonical.exists() and canonical.stat().st_size > 1024:
                    Path(final_path).unlink(missing_ok=True)
                    self.state["song_path"] = str(canonical.resolve())
                    self.save_song_request(self.state["song_request"])
                    final_path = str(canonical.resolve())
            except Exception:
                pass
        return final_path, duration

    def _ffmpeg_bin(self) -> str:
        return str(self.config.get("ffmpeg_path", "ffmpeg"))

    def _ffmpeg_available(self) -> bool:
        try:
            subprocess.run([self._ffmpeg_bin(), "-version"], capture_output=True, timeout=10)
            return True
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # Мастеринг трека (loudnorm) и автоподбор границ сцен по битам (librosa)
    # -------------------------------------------------------------------------
    def normalize_track(
        self,
        input_path: Optional[str] = None,
        target_lufs: float = -14.0,
        true_peak_db: float = -1.5,
        log_cb: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Мастеринг-проход ffmpeg loudnorm: сохраняет результат как отдельный файл
        <имя>_norm.mp3 рядом с оригиналом. Оригинальный трек НЕ перезаписывается.
        После нормализации новый файл становится активным треком проекта.
        """
        def say(msg: str) -> None:
            if log_cb:
                log_cb(msg)

        if not self._ffmpeg_available():
            raise RuntimeError(
                f"ffmpeg не найден ('{self._ffmpeg_bin()}'). Укажите путь к ffmpeg в настройках (config: ffmpeg_path)."
            )

        src = Path(input_path or self.state.get("song_path", ""))
        if not str(input_path or self.state.get("song_path", "")).strip() or not src.exists():
            raise FileNotFoundError("Сначала выберите или сгенерируйте аудиофайл трека.")

        out_path = src.with_name(f"{src.stem}_norm.mp3")
        af = f"loudnorm=I={target_lufs}:TP={true_peak_db}"
        cmd = [self._ffmpeg_bin(), "-y", "-i", str(src), "-af", af, str(out_path)]
        say(f"[MASTERING] Нормализация громкости: {' '.join(cmd)}")
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if proc.returncode != 0 or not out_path.exists() or out_path.stat().st_size < 1024:
            tail = (proc.stderr or "").strip().splitlines()[-3:]
            raise RuntimeError(f"Ошибка ffmpeg при нормализации: {' | '.join(tail) or 'код возврата ' + str(proc.returncode)}")

        size_kb = out_path.stat().st_size / 1024
        dur = self.probe_audio_duration(str(out_path))
        say(f"[MASTERING] Готово: {out_path.name} ({size_kb:.0f} КБ, {dur:.2f} сек), цель I={target_lufs} LUFS, TP={true_peak_db} dBTP. Оригинал сохранён.")

        # Нормализованный трек становится основным треком проекта
        self.set_song_file(str(out_path.resolve()), copy_to_project=True, log_cb=log_cb)
        return str(out_path.resolve())

    @staticmethod
    def _snap_to_bar(times: List[float], beat_period: float, bar_seconds: float, total_dur: float) -> List[float]:
        """
        Из последовательности долей (beat times) выбирает начала тактов:
        каждую сильную долю, ближайшую к сетке тактов (bar_length = beats_per_bar * beat_period).
        """
        snapped: List[float] = []
        seen: set = set()
        for t in times:
            k = round(t / bar_seconds)
            cand = k * bar_seconds
            if cand <= 0.05 or cand >= total_dur - 0.05:
                continue
            # берём ближайший бит к расчётной границе такта
            nearest = min(times, key=lambda b: abs(b - cand))
            if abs(nearest - cand) > beat_period * 1.5:
                val = round(cand, 3)
            else:
                val = round(nearest, 3)
            if 0.05 < val < total_dur - 0.05 and val not in seen:
                seen.add(val)
                snapped.append(val)
        snapped.sort()
        return snapped

    def detect_beat_boundaries(
        self,
        audio_path: Optional[str] = None,
        beats_per_bar: int = 4,
        log_cb: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """
        Автоподбор границ сцен по битам через librosa (beat tracking).
        Возвращает: tempo, beat period, интервал такта и список начал тактов (сильных долей).
        Результат сохраняется в state["beat_boundaries"] и projects/<имя>/data/beat_boundaries.json.
        """
        def say(msg: str) -> None:
            if log_cb:
                log_cb(msg)

        try:
            import librosa  # локальный импорт: тяжёлая зависимость нужна только здесь
        except ImportError:
            raise RuntimeError(
                "Модуль librosa не установлен. Установите зависимости: pip install -r requirements.txt"
            )

        src = Path(audio_path or self.state.get("song_path", ""))
        if not str(audio_path or self.state.get("song_path", "")).strip() or not src.exists():
            raise FileNotFoundError("Сначала выберите или сгенерируйте аудиофайл трека.")

        y, sr = librosa.load(str(src), mono=True)
        total_dur = float(len(y) / sr)
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr, trim=False)
        tempo_val = float(tempo.item() if hasattr(tempo, "item") else tempo)
        beat_times = librosa.frames_to_time(beats, sr=sr)
        beat_period = (60.0 / tempo_val) if tempo_val > 0 else 0.5
        bar_seconds = beat_period * max(1, int(beats_per_bar))

        boundaries = self._snap_to_bar(list(beat_times), beat_period, bar_seconds, total_dur)

        result = {
            "tempo": round(tempo_val, 2),
            "beat_period": round(beat_period, 4),
            "beats_per_bar": int(beats_per_bar),
            "bar_seconds": round(bar_seconds, 4),
            "duration": round(total_dur, 3),
            "boundaries": boundaries,
        }
        self.state["beat_boundaries"] = boundaries
        try:
            proj_dir = self.get_project_dir()
            (proj_dir / "data").mkdir(parents=True, exist_ok=True)
            (proj_dir / "data" / "beat_boundaries.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            say(f"[BEATS] Предупреждение: не удалось сохранить beat_boundaries.json: {exc}")

        say(
            f"[BEATS] Темп {tempo_val:.1f} BPM, такт {bar_seconds:.2f} сек — найдено "
            f"{len(beat_times)} долей, предложено {len(boundaries)} границ сцен на началах тактов."
        )
        return result

    def apply_beat_boundaries(
        self,
        boundaries: List[float],
        preset_name: str = "cyber_cat",
        log_cb: Optional[Callable[[str], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        Пересобирает раскадровку так, чтобы границы сцен совпадали с переданными
        метками (началами тактов). Метки сортируются, дубликаты удаляются;
        последняя сцена автоматически растягивается до конца трека.
        """
        marks = sorted({round(float(b), 3) for b in boundaries if 0.05 < float(b)})
        total = float(self.state.get("song_duration") or 0.0)
        if total <= 0 and self.state.get("song_path"):
            total = self.probe_audio_duration(self.state["song_path"])
        cuts = [0.0] + [m for m in marks if m < total - 0.5] + [total] if total > 0 else [0.0] + [m for m in marks]

        templates = STORYBOARD_PRESETS.get(preset_name) or STORYBOARD_PRESETS["cyber_cat"]
        proj_dir = self.get_project_dir()
        storyboard: List[Dict[str, Any]] = []
        idx = 1
        for i in range(len(cuts) - 1):
            start, end = cuts[i], cuts[i + 1]
            dur = round(end - start, 4)
            if dur < 0.3:
                continue
            tpl = templates[(idx - 1) % len(templates)]
            stype = tpl["type"]
            clip_path = proj_dir / "clips" / f"scene_{idx:03d}.mp4"
            seg_path = proj_dir / "segments" / f"scene_{idx:03d}.wav"
            is_ready = clip_path.exists() and clip_path.stat().st_size > 1024
            storyboard.append({
                "id": idx,
                "type": stype,
                "type_label": SCENE_TYPE_LABELS.get(stype, stype),
                "start": round(start, 4),
                "end": round(end, 4),
                "duration": dur,
                "prompt": tpl["prompt"],
                "custom_image": "",
                "audio_segment": str(seg_path.resolve()) if seg_path.exists() else "",
                "clip_path": str(clip_path.resolve()) if is_ready else "",
                "status": "готово" if is_ready else "ожидание"
            })
            idx += 1

        # хвост после последней метки присоединяем к финальной сцене
        if total > 0 and storyboard and cuts[-1] < total - 0.05:
            storyboard[-1]["end"] = round(total, 4)
            storyboard[-1]["duration"] = round(total - storyboard[-1]["start"], 4)

        self.save_storyboard(storyboard)
        if log_cb:
            log_cb(f"[BEATS] Раскадровка перестроена по битам: {len(storyboard)} сцен.")
        return storyboard

    def run_auto_pipeline(
        self,
        prompt: str,
        lyrics: str,
        duration: float,
        seed: int,
        preset_name: str = "cyber_cat",
        scene_duration: Optional[float] = None,
        audio_path: Optional[str] = None,
        hero_image: Optional[str] = None,
        output_name: str = "final_music_video.mp4",
        log_cb: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Автосценарий «минимум участия»: текст песни + фото → готовый клип одной кнопкой.
        Шаги: (опц.) генерация трека ACE-Step → раскадровка → нарезка аудио →
        рендер всех сцен ComfyUI → финальная сборка MP4.
        """
        def step(msg: str) -> None:
            if log_cb:
                log_cb(f"[AUTO] {msg}")

        if hero_image:
            self.save_song_request({"prompt": prompt, "lyrics": lyrics}, hero_image=hero_image)
            step("Фото героя принято.")

        if audio_path:
            _, dur = self.set_song_file(audio_path, copy_to_project=True, log_cb=log_cb)
            step(f"Аудиофайл загружен, длительность {dur:.2f} сек.")
        elif lyrics.strip():
            step("Трек отсутствует — генерируем песню в ACE-Step по тексту...")
            gen_path = self.generate_song_ace(prompt, lyrics, duration=duration, seed=seed, log_cb=log_cb)
            if gen_path:
                audio_path = gen_path
            else:
                step("ACE-Step вернул пустой результат, пробуем существующий трек проекта.")

        if not self.state.get("song_path"):
            raise RuntimeError("Нет аудиодорожки: сгенерируйте трек или загрузите аудиофайл.")

        storyboard = self.generate_storyboard_from_preset(preset_name=preset_name, scene_duration=scene_duration, log_cb=log_cb)

        # Автоподбор границ сцен по битам (если доступны аудио + librosa) — монтаж попадает в такты
        beat_bounds: List[float] = []
        try:
            res = self.detect_beat_boundaries(log_cb=log_cb)
            beat_bounds = res.get("boundaries", [])
        except Exception as exc:
            step(f"Границы по битам недоступны ({exc}) — используются равномерные сцены.")
        if len(beat_bounds) >= 2:
            storyboard = self.apply_beat_boundaries(beat_bounds, preset_name=preset_name, log_cb=log_cb)
            step(f"Границы сцен выровнены по началам тактов: {len(storyboard)} сцен.")
        else:
            step(f"Раскадровка: {len(storyboard)} сцен.")

        self.slice_audio_segments(log_cb=log_cb)
        step("Аудио нарезано по сценам.")

        self.queue_all_scenes(skip_completed=bool(self.config.get("skip_completed", True)), log_cb=log_cb)
        step("Все сцены отрендерены.")

        out_path = self.assemble_video(output_name=output_name, log_cb=log_cb)
        step(f"Готово! Финальный клип: {out_path}")
        return out_path

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
    @staticmethod
    def normalize_song_tags(music_prompt: str) -> str:
        """
        Приводит теги стиля к формату, который лучше всего понимает ACE-Step:
        "[Genre subgenre, Mood, Instruments, Tempo BPM, Vocal type]" —
        в квадратных скобках, через запятую, без предложений и лишних слов.
        """
        raw = (music_prompt or "").strip()
        if not raw:
            return ""
        # уже обёрнуто в [ ... ] — не трогаем
        if raw.startswith("[") and "]" in raw:
            return raw
        # убираем кавычки, переводим строки в запятые
        cleaned = raw.replace('"', "").replace("\n", ", ")
        parts = [p.strip(" .;") for p in re.split(r"[,;]", cleaned) if p.strip(" .;")]
        return "[" + ", ".join(parts) + "]"

    @staticmethod
    def validate_lyrics_structure(lyrics: str) -> List[str]:
        """
        Эвристики качества текста песни для ACE-Step. Возвращает список
        предупреждений (пустой список = текст выглядит хорошо).
        """
        warnings: List[str] = []
        text = (lyrics or "").strip()
        if not text:
            return ["Текст пуст — ACE-Step сгенерирует инструментал или случайный вокал."]
        upper = text.upper()
        if "[CHORUS]" not in upper:
            warnings.append("Нет секции [Chorus] — припев делает песню запоминающейся.")
        if "[VERSE" not in upper:
            warnings.append("Нет секций [Verse] — куплеты задают историю между припевами.")
        lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("[")]
        avg_len = sum(len(l.split()) for l in lines) / max(len(lines), 1)
        if avg_len > 12:
            warnings.append(f"Средняя строка ~{avg_len:.0f} слов — для ритуемого вокала лучше 4–9 слов в строке.")
        if len(text) < 120:
            warnings.append("Текст очень короткий — треку может не хватить материала на полную длительность.")
        return warnings

    def generate_lyrics_ace(
        self,
        music_prompt: str,
        lyrics_hint: str = "",
        log_cb: Optional[Callable[[str], None]] = None
    ) -> Dict[str, str]:
        ace_url = self.config.get("ace_url", "http://127.0.0.1:8001").rstrip("/")
        normalized_tags = self.normalize_song_tags(music_prompt)
        if normalized_tags != music_prompt.strip():
            if log_cb:
                log_cb(f"[ACE] Теги стиля нормализованы: {normalized_tags}")
            music_prompt = normalized_tags
        for warn in self.validate_lyrics_structure(lyrics_hint):
            if log_cb:
                log_cb(f"[LYRICS][СОВЕТ] {warn}")
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
        # Теги стиля приводим к каноничному формату ACE-Step [Genre, Mood, ...]
        prompt = self.normalize_song_tags(prompt) or prompt
        for warn in self.validate_lyrics_structure(lyrics):
            if log_cb:
                log_cb(f"[LYRICS][СОВЕТ] {warn}")
        self.save_song_request({
            "prompt": prompt,
            "lyrics": lyrics,
            "duration": float(duration),
            "seed": int(seed)
        })

        payload = {
            "model": "acestep-v15-turbo",
            "prompt": prompt,
            "lyrics": lyrics.strip(),
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

    def cancel_queue(self, log_cb: Optional[Callable[[str], None]] = None) -> None:
        """Отмена очереди рендера: текущая сцена дорендеривается, следующие не запускаются."""
        self.cancel_requested.set()
        if log_cb:
            log_cb("[QUEUE] Запрошена остановка очереди. Текущая сцена будет дорендерена, следующие пропущены.")

    def _render_one_scene_safely(
        self,
        scene: Dict[str, Any],
        server_url: str,
        log_cb: Optional[Callable[[str], None]],
        lock: "threading.Lock",
        total: int
    ) -> bool:
        """Рендер одной сцены с изоляцией ошибок. Возвращает True при успехе."""
        sid = int(scene["id"])
        try:
            self.render_single_scene(sid, server_url=server_url, log_cb=log_cb)
            with lock:
                self.state["queue_progress"]["done"] += 1
            return True
        except Exception as exc:
            # Ошибка одной сцены не должна останавливать всю очередь
            for sc in self.state["storyboard"]:
                if int(sc["id"]) == sid:
                    sc["status"] = "ошибка"
                    break
            self.save_storyboard()
            if log_cb:
                log_cb(f"[QUEUE] ✗ Сцена #{sid:03d} завершилась с ошибкой: {exc}. Продолжаем очередь.")
            with lock:
                self.state["queue_progress"]["failed"] += 1
                done_now = self.state["queue_progress"]["done"] + self.state["queue_progress"]["failed"]
                log_cb(f"[QUEUE] Прогресс: {done_now}/{total}")
            return False

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
        - Ошибка одной сцены не останавливает очередь; поддержана отмена (cancel_requested)
          и прогресс в state['queue_progress'] = {total, done, failed, current}.
        """
        import concurrent.futures

        if skip_completed is None:
            skip_completed = bool(self.config.get("skip_completed", True))

        online_servers = self.get_online_comfy_servers(log_cb=log_cb)
        if not online_servers:
            raise RuntimeError("Ни один сервер ComfyUI (8188, 8189) не запущен.")

        pending_scenes: List[Dict[str, Any]] = []
        skipped_count = 0
        for scene in self.state["storyboard"]:
            clip_p = Path(scene.get("clip_path", "")) if scene.get("clip_path") else None
            if skip_completed and scene.get("status") == "готово" and clip_p and clip_p.exists() and clip_p.stat().st_size > 1024:
                if log_cb:
                    log_cb(f"[SKIP] Сцена #{int(scene['id']):03d} уже готова ({clip_p.name}), пропускаем.")
                skipped_count += 1
                continue
            pending_scenes.append(scene)

        # Инициализация прогресса очереди
        self.cancel_requested.clear()
        self.state["queue_progress"] = {
            "total": len(pending_scenes),
            "done": 0,
            "failed": 0,
            "current": f"Сцена 0/{len(pending_scenes)}"
        }

        if not pending_scenes:
            if log_cb:
                log_cb("[QUEUE] Все сцены уже отрендерены.")
                log_cb(f"[QUEUE] ИТОГ: готово 0, ошибок 0, пропущено {skipped_count}.")
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
        progress_lock = threading.Lock()
        cancelled = False

        def _set_current(sid: int) -> None:
            with progress_lock:
                qp = self.state["queue_progress"]
                qp["current"] = f"Сцена {min(qp['done'] + qp['failed'] + 1, qp['total'])}/{qp['total']} (#{sid:03d})"

        if num_servers == 1:
            srv_url = online_servers[0]["url"]
            for sc in pending_scenes:
                if self.cancel_requested.is_set():
                    cancelled = True
                    remaining = sum(1 for x in pending_scenes if int(x["id"]) >= int(sc["id"]))
                    skipped_count += remaining
                    if log_cb:
                        log_cb(f"[QUEUE] Остановлено пользователем. Не выполнено сцен: {remaining}.")
                    break
                _set_current(int(sc["id"]))
                ok = self._render_one_scene_safely(sc, srv_url, log_cb, progress_lock, len(pending_scenes))
                if ok:
                    rendered_paths.append(sc.get("clip_path", ""))
        else:
            def _worker(server_info: Dict[str, Any], scenes_slice: List[Dict[str, Any]]) -> None:
                nonlocal cancelled
                for sc in scenes_slice:
                    if self.cancel_requested.is_set():
                        with progress_lock:
                            cancelled = True
                        return
                    _set_current(int(sc["id"]))
                    self._render_one_scene_safely(sc, server_info["url"], log_cb, progress_lock, len(pending_scenes))

            with concurrent.futures.ThreadPoolExecutor(max_workers=num_servers) as executor:
                futures = []
                for idx, srv in enumerate(online_servers):
                    slice_for_gpu = pending_scenes[idx::num_servers]
                    if slice_for_gpu:
                        futures.append(executor.submit(_worker, srv, slice_for_gpu))
                for fut in concurrent.futures.as_completed(futures):
                    fut.result()  # исключения рабочих потоков уже изолированы внутри

            if self.cancel_requested.is_set():
                cancelled = True
            # Пути готовых клипов берём из раскадровки (порядок в 2 потоках непредсказуем)
            rendered_paths = [
                sc.get("clip_path", "") for sc in self.state["storyboard"]
                if sc.get("status") == "готово" and sc.get("clip_path")
            ]

        qp = self.state["queue_progress"]
        qp["current"] = "остановлено" if cancelled else ("завершено" if qp["failed"] == 0 else "завершено с ошибками")
        if log_cb:
            log_cb(
                f"[QUEUE] ИТОГ: готово {qp['done']}, ошибок {qp['failed']}, пропущено {skipped_count}"
                + (". Очередь остановлена пользователем." if cancelled else ".")
            )

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

    # -------------------------------------------------------------------------
    # Система проверки и установки обновлений через GitHub Releases
    # -------------------------------------------------------------------------
    @staticmethod
    def _parse_version_tuple(ver_str: str) -> Tuple[int, ...]:
        cleaned = ver_str.strip().lstrip("vV")
        parts = re.findall(r"\d+", cleaned)
        return tuple(int(p) for p in parts) if parts else (0, 0, 0)

    def check_for_updates(self, log_cb: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        """
        Проверяет последний релиз в GitHub репозитории GITHUB_REPO.
        Возвращает словарь с информацией о текущей и доступной версиях, ссылкой на установщик и списком изменений.
        """
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "MusicVideoStudio-Updater"
        }
        if log_cb:
            log_cb(f"[UPDATE] Проверка обновлений в репозитории {GITHUB_REPO} (текущая v{APP_VERSION})...")

        req = urllib.request.Request(api_url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                release = json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            if e.code == 404:
                if log_cb:
                    log_cb("[UPDATE] Опубликованных релизов в GitHub Releases пока нет.")
                return {
                    "current_version": APP_VERSION,
                    "latest_version": APP_VERSION,
                    "update_available": False,
                    "download_url": "",
                    "html_url": f"https://github.com/{GITHUB_REPO}/releases",
                    "notes": "Релизы ещё не опубликованы."
                }
            raise RuntimeError(f"Ошибка обращения к GitHub API ({e.code}): {e.reason}")
        except Exception as e:
            raise RuntimeError(f"Не удалось проверить обновления: {e}")

        tag_name = str(release.get("tag_name", "")).strip()
        latest = tag_name.lstrip("vV") or APP_VERSION
        body = str(release.get("body", "") or "")
        html_url = str(release.get("html_url", f"https://github.com/{GITHUB_REPO}/releases"))
        assets = release.get("assets", [])

        try:
            is_newer = tuple(map(int, latest.split("."))) > tuple(map(int, APP_VERSION.split(".")))
        except ValueError:
            is_newer = self._parse_version_tuple(latest) > self._parse_version_tuple(APP_VERSION)

        download_url = ""
        preferred_names = ("MusicVideoStudio_Setup.exe", "MusicVideoStudio_Desktop.exe")
        if isinstance(assets, list):
            for pref in preferred_names:
                for asset in assets:
                    if isinstance(asset, dict) and str(asset.get("name", "")) == pref:
                        download_url = str(asset.get("browser_download_url", ""))
                        break
                if download_url:
                    break
            if not download_url:
                for asset in assets:
                    if isinstance(asset, dict) and str(asset.get("name", "")).lower().endswith(".exe"):
                        download_url = str(asset.get("browser_download_url", ""))
                        break

        if log_cb:
            if is_newer:
                log_cb(f"[UPDATE] Доступна новая версия: v{latest} (установлена v{APP_VERSION}).")
            else:
                log_cb(f"[UPDATE] Установлена актуальная версия v{APP_VERSION} (на GitHub: v{latest}).")

        return {
            "current_version": APP_VERSION,
            "latest_version": latest,
            "update_available": is_newer,
            "download_url": download_url,
            "html_url": html_url,
            "notes": body
        }

    def download_and_install_update(
        self,
        download_url: str,
        exit_app: bool = True,
        log_cb: Optional[Callable[[str], None]] = None
    ) -> Path:
        """
        Скачивает установщик MusicVideoStudio_Setup.exe во временную папку,
        очищает переменные окружения PyInstaller (_MEIPASS2, PYTHONPATH, PYTHONHOME, TCL_LIBRARY, TK_LIBRARY),
        чтобы дочерний процесс инсталлятора не пытался искать python311.dll во временной папке _MEI родителя,
        запускает инсталлятор через os.startfile (или subprocess.Popen с чистым env) и завершает приложение.
        """
        if not download_url:
            raise ValueError("Не указана ссылка download_url для скачивания обновления.")

        temp_dir = Path(tempfile.gettempdir())
        filename = download_url.split("/")[-1] or "MusicVideoStudio_Setup.exe"
        if not filename.lower().endswith(".exe"):
            filename = "MusicVideoStudio_Setup.exe"
        installer_path = temp_dir / filename

        if log_cb:
            log_cb(f"[UPDATE] Скачивание установщика: {download_url} -> {installer_path}")

        req = urllib.request.Request(
            download_url,
            headers={"User-Agent": "MusicVideoStudio-Updater"},
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=300.0) as resp:
            with open(installer_path, "wb") as f:
                shutil.copyfileobj(resp, f)

        if log_cb:
            log_cb(f"[UPDATE] Запуск установщика {installer_path}...")

        # Освобождаем дочерние процессы перед обновлением
        self.stop_ace_server()

        # Очищаем переменные окружения PyInstaller, чтобы новый процесс не наследовал старый путь Temp\_MEI...
        clean_env = dict(os.environ)
        for var in ("_MEIPASS", "_MEIPASS2", "PYTHONPATH", "PYTHONHOME", "TCL_LIBRARY", "TK_LIBRARY"):
            clean_env.pop(var, None)
            os.environ.pop(var, None)

        if hasattr(os, "startfile"):
            os.startfile(str(installer_path))
        else:
            creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            subprocess.Popen(
                [str(installer_path)],
                env=clean_env,
                cwd=str(temp_dir),
                close_fds=True,
                creationflags=creationflags
            )

        if exit_app:
            os._exit(0)

        return installer_path
