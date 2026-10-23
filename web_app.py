import json
import threading
import mimetypes
import urllib.parse
from datetime import datetime
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import List, Dict, Any
from core import (
    StudioCore,
    SCENE_TYPE_LABELS,
    STORYBOARD_PRESETS,
    BUNDLE_DIR,
    APP_VERSION,
    GITHUB_REPO
)

PORT = 8765
WEB_DIR = BUNDLE_DIR / "web"

studio = StudioCore()
log_buffer: List[str] = []
log_lock = threading.Lock()


def append_log(msg: str) -> None:
    with log_lock:
        log_buffer.append(msg)
        if len(log_buffer) > 400:
            del log_buffer[: len(log_buffer) - 400]
    print(msg, flush=True)
    # Дублирование лога в <папка проекта>/logs/ГГГГ-ММ-ДД.txt
    try:
        pdir = studio.get_project_dir()
        if pdir and Path(pdir).exists():
            logfile = Path(pdir) / "logs" / f"{datetime.now().strftime('%Y-%m-%d')}.txt"
            with open(logfile, "a", encoding="utf-8") as fh:
                fh.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass  # запись лога не должна ронять сервер


class StudioRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, data: Dict[str, Any], status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return json.loads(raw) if raw.strip() else {}

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path

        if route in ("/", "/index.html"):
            index_file = WEB_DIR / "index.html"
            if not index_file.exists():
                self._send_json({"ok": False, "error": "Файл web/index.html не найден"}, 404)
                return
            content = index_file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if route == "/api/state":
            with log_lock:
                logs_copy = list(log_buffer[-120:])
            self._send_json({
                "ok": True,
                "version": APP_VERSION,
                "github_repo": GITHUB_REPO,
                "config": studio.config,
                "state": studio.state,
                "projects": studio.list_projects(),
                "project_dir": str(studio.get_project_dir()),          # текущая папка проекта
                "recent_projects": list(studio.recent_projects()),     # последние 10 проектов
                "presets": list(STORYBOARD_PRESETS.keys()),
                "scene_types": SCENE_TYPE_LABELS,
                "logs": logs_copy
            })
            return

        if route == "/api/update/check":
            try:
                info = studio.check_for_updates(log_cb=append_log)
                self._send_json({"ok": True, **info})
            except Exception as e:
                append_log(f"[UPDATE ERROR] {e}")
                self._send_json({"ok": False, "error": str(e), "current_version": APP_VERSION}, 500)
            return

        if route == "/api/gpu_status":
            servers = studio.get_online_comfy_servers(log_cb=append_log)
            self._send_json({"ok": True, "servers": servers})
            return

        if route == "/api/media":
            qs = urllib.parse.parse_qs(parsed.query)
            file_path = qs.get("path", [""])[0]
            p = Path(file_path)
            if not p.exists() or not p.is_file():
                self._send_json({"ok": False, "error": "Файл не найден"}, 404)
                return
            # Безопасность: отдаём файлы ТОЛЬКО из текущей папки проекта
            resolved = p.resolve()
            allowed_roots = [Path(studio.get_project_dir()).resolve()]
            legacy_root = (BUNDLE_DIR / "projects").resolve()   # совместимость: старые проекты в projects/
            def _is_relative(child: Path, root: Path) -> bool:
                try:
                    return child == root or child.is_relative_to(root)
                except AttributeError:  # Python < 3.9
                    try:
                        child.relative_to(root)
                        return True
                    except ValueError:
                        return False
            if not any(_is_relative(resolved, root) for root in allowed_roots + [legacy_root]):
                self._send_json({"ok": False, "error": "Доступ к файлу запрещён (вне папки проекта)"}, 403)
                return
            mime, _ = mimetypes.guess_type(str(p))
            data = p.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self._send_json({"ok": False, "error": f"Неизвестный маршрут: {route}"}, 404)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        try:
            body = self._read_json_body()

            if route == "/api/update/install":
                download_url = str(body.get("download_url", "")).strip()
                if not download_url:
                    info = studio.check_for_updates(log_cb=append_log)
                    download_url = str(info.get("download_url", "")).strip()
                if not download_url:
                    self._send_json({"ok": False, "error": "Ссылка на установщик MusicVideoStudio_Setup.exe не найдена в релизе"}, 400)
                    return

                def _bg_install() -> None:
                    try:
                        studio.download_and_install_update(download_url, exit_app=True, log_cb=append_log)
                    except Exception as exc:
                        append_log(f"[UPDATE ERROR] {exc}")

                threading.Thread(target=_bg_install, daemon=True).start()
                self._send_json({"ok": True, "message": "Скачивание и запуск установщика начаты"})
                return

            if route == "/api/config":
                cfg = studio.save_config(body)
                append_log("[CONFIG] Настройки обновлены через веб-интерфейс.")
                self._send_json({"ok": True, "config": cfg})
                return

            if route == "/api/project/open":
                proj_name = str(body.get("project_name", "default_project")).strip()
                st = studio.open_project(proj_name, log_cb=append_log)
                self._send_json({"ok": True, "state": st, "projects": studio.list_projects()})
                return

            # ===== Выбор папки проекта =====
            if route == "/api/project/pick_folder":
                path = studio.pick_folder_dialog(log_cb=append_log)
                if not path:
                    self._send_json({"ok": True, "path": "", "message": "Выбор отменён"})
                    return
                info = studio.set_project_dir(path, log_cb=append_log)
                self._send_json({"ok": bool(info), "path": str(Path(path).resolve())})
                return

            if route == "/api/project/create_folder":
                parent = str(body.get("parent_path", "")).strip()
                name = str(body.get("name", "")).strip()
                info = studio.create_project_folder(parent, name, log_cb=append_log)
                self._send_json({
                    "ok": bool(info),
                    "path": str(info.get("project_dir", "")) if info else "",
                    "state": info,
                })
                return

            if route == "/api/project/open_path":
                # Открытие проекта по полному пути (кнопки «Недавние проекты»)
                path = str(body.get("path", "")).strip()
                proj = Path(path).resolve()
                if not proj.is_dir():
                    self._send_json({"ok": False, "error": f"Папка не найдена: {proj}"}, 400)
                    return
                info = studio.set_project_dir(str(proj), log_cb=append_log)
                self._send_json({"ok": bool(info), "path": str(proj)})
                return
            # ===== /Выбор папки проекта =====

            if route == "/api/ace/start":
                ok = studio.start_ace_server(log_cb=append_log)
                self._send_json({"ok": ok})
                return

            if route == "/api/ace/stop":
                ok = studio.stop_ace_server(log_cb=append_log)
                self._send_json({"ok": True, "stopped": ok})
                return

            if route == "/api/comfy/start":
                port = int(body.get("port", 8188))
                gpu_id = int(body.get("gpu_id", 0))
                ok = studio.start_comfy_server(port=port, gpu_id=gpu_id, log_cb=append_log)
                self._send_json({"ok": ok})
                return

            if route == "/api/song/save_params":
                studio.save_song_request(
                    {
                        "prompt": str(body.get("prompt", "")),
                        "lyrics": str(body.get("lyrics", "")),
                        "duration": float(body.get("duration", 30.0)),
                        "seed": int(body.get("seed", 42))
                    },
                    hero_image=str(body.get("hero_image", ""))
                )
                append_log("[SONG] Параметры песни сохранены в data/song_request.json")
                self._send_json({"ok": True, "state": studio.state})
                return

            if route == "/api/song/set_file":
                source_path = str(body.get("path", "")).strip()
                final_path, dur = studio.set_song_file(source_path, copy_to_project=True, log_cb=append_log)
                self._send_json({"ok": True, "song_path": final_path, "song_duration": dur, "state": studio.state})
                return

            if route == "/api/upload/hero_image":
                path = studio.upload_hero_image(
                    file_b64=str(body.get("file_base64", "")),
                    filename=str(body.get("filename", "hero.png")),
                    log_cb=append_log
                )
                self._send_json({"ok": True, "hero_image": path, "state": studio.state})
                return

            if route == "/api/upload/song_audio":
                path, dur = studio.upload_song_audio(
                    file_b64=str(body.get("file_base64", "")),
                    filename=str(body.get("filename", "song.mp3")),
                    log_cb=append_log
                )
                self._send_json({"ok": True, "song_path": path, "song_duration": dur, "state": studio.state})
                return

            if route == "/api/pipeline/auto":
                hero_image = str(body.get("hero_image", "")).strip() or studio.state.get("hero_image", "")
                if body.get("hero_image_base64"):
                    hero_image = studio.upload_hero_image(
                        file_b64=str(body.get("hero_image_base64")),
                        filename=str(body.get("hero_image_filename", "hero.png")),
                        log_cb=append_log
                    )
                audio_path = str(body.get("audio_path", "")).strip() or None
                if body.get("audio_base64"):
                    audio_path, _ = studio.upload_song_audio(
                        file_b64=str(body.get("audio_base64")),
                        filename=str(body.get("audio_filename", "song.mp3")),
                        log_cb=append_log
                    )

                prompt = str(body.get("prompt", ""))
                lyrics = str(body.get("lyrics", ""))
                dur = float(body.get("duration", 30.0))
                seed = int(body.get("seed", 42))
                preset = str(body.get("preset", "cyber_cat"))
                scene_dur_raw = body.get("scene_duration")
                scene_dur = float(scene_dur_raw) if scene_dur_raw else None

                def _bg_auto() -> None:
                    try:
                        studio.run_auto_pipeline(
                            prompt=prompt,
                            lyrics=lyrics,
                            duration=dur,
                            seed=seed,
                            preset_name=preset,
                            scene_duration=scene_dur,
                            audio_path=audio_path,
                            hero_image=hero_image or None,
                            log_cb=append_log
                        )
                    except Exception as exc:
                        append_log(f"[AUTO ERROR] {exc}")

                threading.Thread(target=_bg_auto, daemon=True).start()
                self._send_json({"ok": True, "message": "Автоконвейер запущен: текст песни + фото → готовый клип"})
                return

            if route == "/api/song/generate_lyrics":
                res = studio.generate_lyrics_ace(
                    music_prompt=str(body.get("prompt", "")),
                    lyrics_hint=str(body.get("lyrics", "")),
                    log_cb=append_log
                )
                self._send_json({"ok": True, "result": res, "state": studio.state})
                return

            if route == "/api/song/generate_audio":
                prompt = str(body.get("prompt", ""))
                lyrics = str(body.get("lyrics", ""))
                dur = float(body.get("duration", 30.0))
                seed = int(body.get("seed", 42))

                def _bg_song() -> None:
                    try:
                        studio.generate_song_ace(prompt, lyrics, duration=dur, seed=seed, log_cb=append_log)
                    except Exception as exc:
                        append_log(f"[ERROR] {exc}")

                threading.Thread(target=_bg_song, daemon=True).start()
                self._send_json({"ok": True, "message": "Задача генерации трека запущена"})
                return

            if route == "/api/storyboard/generate":
                preset = str(body.get("preset", "cyber_cat"))
                scene_dur = float(body.get("scene_duration", studio.config.get("default_scene_duration", 5.0)))
                sb = studio.generate_storyboard_from_preset(preset_name=preset, scene_duration=scene_dur, log_cb=append_log)
                self._send_json({"ok": True, "storyboard": sb, "state": studio.state})
                return

            if route == "/api/storyboard/update_scene":
                sid = int(body.get("id", 0))
                updated = studio.update_scene(
                    scene_id=sid,
                    prompt=body.get("prompt"),
                    scene_type=body.get("type"),
                    custom_image=body.get("custom_image")
                )
                self._send_json({"ok": True, "scene": updated, "storyboard": studio.state["storyboard"]})
                return

            if route == "/api/audio/slice":
                files = studio.slice_audio_segments(log_cb=append_log)
                self._send_json({"ok": True, "segments": files, "storyboard": studio.state["storyboard"]})
                return

            if route == "/api/audio/normalize":
                # Мастеринг loudnorm может занять время — выполняем в фоне
                def _bg_normalize() -> None:
                    try:
                        out_path = studio.normalize_track(
                            input_path=str(body.get("path", "")).strip() or None,
                            target_lufs=float(body.get("target_lufs", -14.0)),
                            true_peak_db=float(body.get("true_peak", -1.5)),
                            log_cb=append_log
                        )
                        append_log(f"[MASTERING] Нормализованный трек готов: {out_path}")
                    except Exception as exc:
                        append_log(f"[MASTERING ERROR] {exc}")

                threading.Thread(target=_bg_normalize, daemon=True).start()
                self._send_json({"ok": True, "message": "Нормализация громкости запущена (результат: *_norm.mp3, оригинал не перезаписывается)"})
                return

            if route == "/api/audio/beats":
                res = studio.detect_beat_boundaries(
                    audio_path=str(body.get("path", "")).strip() or None,
                    beats_per_bar=int(body.get("beats_per_bar", 4)),
                    log_cb=append_log
                )
                self._send_json({"ok": True, **res, "state": studio.state})
                return

            if route == "/api/audio/beats/apply":
                bounds = body.get("boundaries")
                if not isinstance(bounds, list):
                    bounds = studio.state.get("beat_boundaries", [])
                preset = str(body.get("preset", "")).strip() or "cyber_cat"
                sb = studio.apply_beat_boundaries([float(b) for b in bounds], preset_name=preset, log_cb=append_log)
                self._send_json({"ok": True, "storyboard": sb, "beat_boundaries": studio.state.get("beat_boundaries", []), "state": studio.state})
                return

            if route == "/api/comfy/render_scene":
                sid = int(body.get("id", 1))

                def _bg_single() -> None:
                    try:
                        studio.render_single_scene(sid, log_cb=append_log)
                    except Exception as exc:
                        append_log(f"[ERROR] {exc}")

                threading.Thread(target=_bg_single, daemon=True).start()
                self._send_json({"ok": True, "message": f"Рендер сцены #{sid:03d} запущен"})
                return

            if route == "/api/comfy/queue_all":
                skip_completed = bool(body.get("skip_completed", True))

                def _bg_all() -> None:
                    try:
                        studio.queue_all_scenes(skip_completed=skip_completed, log_cb=append_log)
                    except Exception as exc:
                        append_log(f"[ERROR] {exc}")

                threading.Thread(target=_bg_all, daemon=True).start()
                self._send_json({"ok": True, "message": "Очередь рендера всех сцен запущена"})
                return

            if route == "/api/comfy/cancel":
                studio.cancel_queue(log_cb=append_log)
                self._send_json({"ok": True, "message": "Запрошена остановка очереди после текущей сцены"})
                return

            if route == "/api/video/assemble":
                out_name = str(body.get("output_name", "final_music_video.mp4"))

                def _bg_assemble() -> None:
                    try:
                        studio.assemble_video(output_name=out_name, log_cb=append_log)
                    except Exception as exc:
                        append_log(f"[ERROR] {exc}")

                threading.Thread(target=_bg_assemble, daemon=True).start()
                self._send_json({"ok": True, "message": "Запущена финальная сборка MP4"})
                return

            self._send_json({"ok": False, "error": f"Неизвестный POST-маршрут: {route}"}, 404)
        except Exception as e:
            append_log(f"[ERROR] {e}")
            self._send_json({"ok": False, "error": str(e)}, 500)


def main() -> None:
    import webbrowser
    # При запуске открываем последний проект (config.json → project_dir);
    # если папка пропала — open_last_project напишет понятное сообщение в лог.
    if not studio.open_last_project(log_cb=append_log):
        studio.open_project(studio.state["project_name"], log_cb=append_log)
    if not studio.state.get("storyboard"):
        studio.generate_storyboard_from_preset("cyber_cat", log_cb=append_log)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), StudioRequestHandler)
    url = f"http://127.0.0.1:{PORT}"
    append_log(f"[WEB] Веб-сервер MusicVideoStudio v{APP_VERSION} запущен: {url}")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        append_log("[WEB] Остановка веб-сервера...")
        server.server_close()


if __name__ == "__main__":
    main()
