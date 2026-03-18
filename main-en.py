"""
Youtility - YouTube Video Downloader
Features: Video download, playlist, live stream, codec conversion, history
"""

import sys
import os
import shutil
import json
import re
import signal
import subprocess
import sqlite3
import threading
import urllib.parse
from collections import deque
from datetime import datetime, timedelta

import requests
import yt_dlp

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget,
    QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QProgressBar, QMessageBox,
    QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QCheckBox, QSystemTrayIcon, QMenu, QDialog,
    QScrollArea
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QColor, QIcon


# ─────────────────────────────────────────────────────────
#  Worker Threads
# ─────────────────────────────────────────────────────────

class ThumbnailThread(QThread):
    """Fetches thumbnail image bytes in background."""
    finished = pyqtSignal(bytes)
    error    = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            data = requests.get(self.url, timeout=10).content
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))


class InfoFetchThread(QThread):
    """Fetches yt-dlp video info in background (non-blocking for the UI)."""
    info_ready = pyqtSignal(dict)
    error      = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            opts = {"quiet": True, "no_warnings": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
            self.info_ready.emit(info)
        except Exception as e:
            self.error.emit(str(e))


class PlaylistInfoThread(QThread):
    """Fetches playlist metadata (titles, count) without full extraction."""
    info_ready = pyqtSignal(dict)
    error      = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        # If URL is a watch URL with list= param, convert to playlist URL
        # so yt-dlp doesn't get confused and return just the single video
        self.url = self._to_playlist_url(url)

    @staticmethod
    def _to_playlist_url(url: str) -> str:
        """Convert https://youtube.com/watch?v=X&list=Y  →  https://youtube.com/playlist?list=Y"""
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        list_id = params.get("list", [None])[0]
        if list_id and ("watch" in parsed.path or "v" in params):
            return f"https://www.youtube.com/playlist?list={list_id}"
        return url

    def run(self):
        try:
            opts = {
                "quiet":        True,
                "no_warnings":  True,
                "extract_flat": True,
                "noplaylist":   False,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)

            # Force-expand entries (may be a lazy generator in yt-dlp)
            if info and "entries" in info:
                info["entries"] = list(info["entries"] or [])

            self.info_ready.emit(info)
        except Exception as e:
            self.error.emit(str(e))


class DownloadThread(QThread):
    """Downloads a single video or audio file."""
    progress_signal = pyqtSignal(dict)
    status_signal   = pyqtSignal(str)   # "merging", etc.
    error_signal    = pyqtSignal(str)
    finished_signal = pyqtSignal(str)   # emits FINAL merged file path

    def __init__(self, url: str, download_path: str, ydl_opts: dict):
        super().__init__()
        self.url              = url
        self.download_path    = download_path
        self.ydl_opts         = ydl_opts.copy()
        self.is_cancelled     = False
        self.downloaded_file  = None   # last intermediate file seen
        self.final_file       = None   # final path after postprocessing/merge
        self.current_ydl      = None

    def run(self):
        try:
            def progress_hook(d):
                if self.is_cancelled:
                    raise Exception("Download cancelled by user.")
                if d["status"] == "downloading":
                    self.progress_signal.emit(d)
                elif d["status"] == "finished":
                    self.downloaded_file = d["filename"]

            def postprocessor_hook(d):
                """Capture the real final path after FFmpeg merge/remux."""
                if d.get("status") == "finished":
                    # yt-dlp puts the final path in info_dict["filepath"]
                    fp = (d.get("info_dict", {}) or {}).get("filepath") or \
                         d.get("filepath", "")
                    if fp and os.path.exists(fp):
                        self.final_file = fp

            self.ydl_opts["progress_hooks"]      = [progress_hook]
            self.ydl_opts["postprocessor_hooks"] = [postprocessor_hook]

            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                self.current_ydl = ydl
                ydl.download([self.url])

            if not self.is_cancelled:
                # Prefer postprocessor-captured path; fall back to resolving from template
                best = self.final_file or self._resolve_merged(
                    self.downloaded_file,
                    self.ydl_opts.get("merge_output_format", ""),
                )
                self.finished_signal.emit(best or self.downloaded_file or "")

        except Exception as e:
            if not self.is_cancelled:
                self.error_signal.emit(str(e))

    @staticmethod
    def _resolve_merged(downloaded: str, merge_fmt: str) -> str:
        """
        If yt-dlp emitted an intermediate file like 'video.f251.webm' but the
        real merged file is 'video.mkv', find and return the merged path.
        Pattern: strip trailing  .fNNN.ext  and add .merge_fmt
        """
        if not downloaded or not merge_fmt:
            return downloaded
        # Strip format-tagged extension: .f137.mp4 / .f251.webm / .fNNN.ext
        base = re.sub(r"\.[a-z0-9]+\.[a-z0-9]{2,4}$", "",
                      downloaded, flags=re.IGNORECASE)
        candidate = f"{base}.{merge_fmt}"
        if candidate != downloaded and os.path.exists(candidate):
            return candidate
        return downloaded

    def cancel(self):
        """Signal cancellation. Do NOT wait() here — blocks the UI event loop."""
        self.is_cancelled = True
        if self.isRunning():
            self.terminate()


class PlaylistDownloadThread(QThread):
    """Downloads all videos in a playlist, one by one."""
    progress_signal      = pyqtSignal(dict)       # current-video yt-dlp progress dict
    video_started_signal = pyqtSignal(int, str)   # (1-based index, title)
    video_done_signal    = pyqtSignal(int, str)   # (1-based index, final filepath)
    error_signal         = pyqtSignal(str, int)   # (message, 0-based index, -1 = fatal)
    all_done_signal      = pyqtSignal()

    def __init__(self, url: str, download_path: str, ydl_opts: dict, entries: list):
        super().__init__()
        self.url           = url
        self.download_path = download_path
        self.ydl_opts      = ydl_opts.copy()
        self.entries       = entries              # list of {title, webpage_url}
        self.is_cancelled  = False
        self.total         = len(entries)
        self.current_index = 0

    def run(self):
        current_file  = [None]
        final_file    = [None]

        def progress_hook(d):
            if self.is_cancelled:
                raise Exception("Download cancelled by user.")
            if d["status"] == "downloading":
                self.progress_signal.emit(d)
            elif d["status"] == "finished":
                current_file[0] = d["filename"]

        def postprocessor_hook(d):
            if d.get("status") == "finished":
                fp = (d.get("info_dict", {}) or {}).get("filepath") or \
                    d.get("filepath", "")
                if fp and os.path.exists(fp):
                    final_file[0] = fp
            
            pp = d.get("postprocessor", "") 
            if "Merger" in pp or "Remux" in pp:
                pass 

        opts = self.ydl_opts.copy()
        opts["progress_hooks"]      = [progress_hook]
        opts["postprocessor_hooks"] = [postprocessor_hook]
        opts["noplaylist"]          = True

        for i, entry in enumerate(self.entries):
            if self.is_cancelled:
                break

            self.current_index = i + 1
            title = entry.get("title", f"Video {i + 1}")

            # extract_flat returns `url` which may be just a video ID or a short URL
            video_url = entry.get("webpage_url")
            if not video_url:
                raw = entry.get("url", "")
                if raw.startswith("http"):
                    video_url = raw
                elif raw:
                    # Plain video ID — build full URL
                    video_url = f"https://www.youtube.com/watch?v={raw}"

            if not video_url:
                self.error_signal.emit(f"Could not get URL for video {i + 1}", i)
                continue

            self.video_started_signal.emit(self.current_index, title)
            current_file[0] = None
            final_file[0]   = None

            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([video_url])
                # Prefer postprocessor path, then resolve, then raw intermediate
                best = final_file[0] or DownloadThread._resolve_merged(
                    current_file[0],
                    self.ydl_opts.get("merge_output_format", ""),
                )
                self.video_done_signal.emit(self.current_index, best or current_file[0] or "")
            except Exception as e:
                if self.is_cancelled:
                    break
                self.error_signal.emit(str(e), i)

        if not self.is_cancelled:
            self.all_done_signal.emit()

    def cancel(self):
        """Signal cancellation. Do NOT wait() here — blocks the UI event loop."""
        self.is_cancelled = True
        if self.isRunning():
            self.terminate()


class ConversionThread(QThread):
    progress_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal()
    error_signal    = pyqtSignal(str)

    def __init__(self, input_file: str, output_file: str,
                 video_codec: str, audio_codec: str,
                 extra_params: list = None,
                 cpu_fallback_video: str = "",
                 hwaccel_input_args: list = None):          # ← EKLENDİ
        super().__init__()
        self.input_file          = input_file
        self.output_file         = output_file
        self.video_codec         = video_codec
        self.audio_codec         = audio_codec
        self.extra_params        = extra_params or []
        self.cpu_fallback_video  = cpu_fallback_video
        self.hwaccel_input_args  = hwaccel_input_args or [] # ← EKLENDİ
        self.is_running          = True
        self._process            = None

    def _build_command(self, video_codec: str) -> list:
        cmd = ["ffmpeg"]
        cmd.extend(self.hwaccel_input_args)                 # ← EKLENDİ
        cmd.extend(["-i", self.input_file,
                    "-c:v", video_codec,
                    "-c:a", self.audio_codec])
        cmd.extend(self.extra_params)
        cmd.extend(["-y", self.output_file])
        return cmd

    # ------------------------------------------------------------------
    def _run_ffmpeg(self, command: list) -> tuple[int, str]:
        """Run ffmpeg and return (returncode, stderr_tail)."""
        self._process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding='utf-8',
            errors='replace',    # never crash on unexpected chars (cp1254, etc.)
            bufsize=1,
        )

        duration         = None
        duration_pattern = re.compile(r"Duration:\s*(\d{2}):(\d{2}):(\d{2})\.\d+")
        time_pattern     = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})\.\d+")
        fps_pattern      = re.compile(r"fps=\s*([\d.]+)")
        all_lines        = []

        for line in self._process.stderr:
            if not self.is_running:
                self._process.terminate()
                return -1, ""

            all_lines.append(line)

            if duration is None:
                m = duration_pattern.search(line)
                if m:
                    h, mn, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    duration = h * 3600 + mn * 60 + s

            tm = time_pattern.search(line)
            if tm:
                h, mn, s = int(tm.group(1)), int(tm.group(2)), int(tm.group(3))
                cur = h * 3600 + mn * 60 + s
                pct = min((cur / duration) * 100, 100.0) if duration else 0.0
                fps_m = fps_pattern.search(line)
                fps   = fps_m.group(1) if fps_m else "0"
                eta   = max(duration - cur, 0) if duration else 0
                self.progress_signal.emit({
                    "percent": pct,
                    "time":    f"{h:02d}:{mn:02d}:{s:02d}",
                    "speed":   fps,
                    "eta":     str(timedelta(seconds=eta)),
                })

        ret = self._process.wait()
        return ret, "".join(all_lines[-30:])

    # ------------------------------------------------------------------
    def run(self):
        try:
            ret, stderr_tail = self._run_ffmpeg(self._build_command(self.video_codec))

            # Hardware encoder might not be available – try CPU fallback
            if ret != 0 and self.cpu_fallback_video and self.is_running:
                hw_keywords = ("nvenc", "amf", "qsv", "vaapi", "videotoolbox")
                if any(k in self.video_codec.lower() for k in hw_keywords):
                    self.progress_signal.emit({
                        "percent": 0, "time": "00:00:00",
                        "speed": "0", "eta": "Retrying with CPU...",
                    })
                    ret, stderr_tail = self._run_ffmpeg(
                        self._build_command(self.cpu_fallback_video)
                    )

            if not self.is_running:
                return

            if ret == 0:
                self.finished_signal.emit()
            else:
                # Extract a readable error from stderr
                err_match = re.search(
                    r"(Error|Invalid|No such|Encoder|Decoder|not found|"
                    r"Unknown encoder|Unrecognized)[^\n]*",
                    stderr_tail, re.IGNORECASE,
                )
                msg = err_match.group(0).strip() if err_match else \
                      f"FFmpeg exited with code {ret}."
                self.error_signal.emit(msg)

        except FileNotFoundError:
            self.error_signal.emit(
                "FFmpeg not found. Please install FFmpeg first (Settings tab)."
            )
        except Exception as e:
            self.error_signal.emit(str(e))

    def cancel(self):
        self.is_running = False
        if self._process:
            try:
                self._process.terminate()
            except Exception:
                pass
        self.quit()
        self.wait(3000)


class LiveStreamThread(QThread):
    """Downloads a live stream by running yt-dlp as a real subprocess.
    Uses %(id)s as filename during download to avoid Windows encoding bugs
    with non-ASCII titles (Turkish chars etc.) that corrupt FFmpeg muxing.
    Renames to real title after completion.
    """
    progress_signal = pyqtSignal(dict)
    status_signal   = pyqtSignal(str)
    error_signal    = pyqtSignal(str)
    finished_signal = pyqtSignal(str)

    _PROG_RE = re.compile(
        r"(\d+):\s*\[download\]\s+"
        r"([\d.]+)(KiB|MiB|GiB|B)\s+at\s+"
        r"([\d.]+)(KiB|MiB|GiB|B)/s\s+"
        r"\([\d:]+\)"
        r"(?:\s*\(frag\s+(\d+)/(\d+)\))?",
        re.IGNORECASE,
    )
    _MERGE_RE  = re.compile(r"\[ffmpeg\]|Merging", re.IGNORECASE)
    # Matches --print "after_move:%(title)s	%(id)s	%(filepath)s"
    _PRINT_RE  = re.compile(r"^(.+)	([A-Za-z0-9_-]+)	(.+)$")

    def __init__(self, url: str, ydl_args: list, live_dir: str, output_fmt: str):
        super().__init__()
        self.url          = url
        self.ydl_args     = ydl_args
        self.live_dir     = live_dir
        self.output_fmt   = output_fmt
        self._proc        = None
        self.is_cancelled = False
        self.debug_log    = []  # Store debug output

    @staticmethod
    def _to_bytes(value: float, unit: str) -> float:
        return value * {"B": 1, "KIB": 1024, "MIB": 1024**2, "GIB": 1024**3}.get(unit.upper(), 1)

    @staticmethod
    def _safe_filename(title: str, ext: str) -> str:
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(". ")[:200]
        return f"{safe}.{ext}" if safe else f"recording.{ext}"

    def run(self):
        cmd = [sys.executable, "-m", "yt_dlp"] + self.ydl_args + [self.url]
        final_path = ""
        video_title = ""
        video_id = ""

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
            )

            for line in self._proc.stdout:
                if self.is_cancelled:
                    break
                line = line.rstrip()
                
                # Log ALL lines to debug
                self.debug_log.append(line)

                pm = self._PRINT_RE.match(line)
                if pm:
                    video_title = pm.group(1).strip()
                    video_id    = pm.group(2).strip()
                    final_path  = pm.group(3).strip()
                    continue

                m = self._PROG_RE.search(line)
                if m:
                    stream_id  = int(m.group(1)) if m.group(1) else 1
                    dl_bytes   = self._to_bytes(float(m.group(2)), m.group(3))
                    spd_bytes  = self._to_bytes(float(m.group(4)), m.group(5))
                    frag_idx   = int(m.group(6)) if m.group(6) else 0
                    frag_count = int(m.group(7)) if m.group(7) else 0
                    self.progress_signal.emit({
                        "stream_id": stream_id, "downloaded": dl_bytes,
                        "speed": spd_bytes, "frag_idx": frag_idx, "frag_count": frag_count,
                    })
                elif self._MERGE_RE.search(line):
                    self.status_signal.emit("merging")

            ret = self._proc.wait()
            if self.is_cancelled:
                return
            if ret != 0:
                self.error_signal.emit(f"yt-dlp exited with code {ret}")
                return

            # Rename id-based file to proper title
            if final_path and os.path.exists(final_path) and video_title and video_id:
                ext       = os.path.splitext(final_path)[1].lstrip(".")
                nice_name = self._safe_filename(video_title, ext or self.output_fmt)
                nice_path = os.path.join(self.live_dir, nice_name)
                if os.path.exists(nice_path) and nice_path != final_path:
                    base, ext2 = os.path.splitext(nice_path)
                    nice_path  = f"{base}_{video_id}{ext2}"
                try:
                    os.rename(final_path, nice_path)
                    final_path = nice_path
                except Exception:
                    pass

            if not final_path or not os.path.exists(final_path):
                final_path = self._find_output()

            self.finished_signal.emit(final_path)

        except Exception as e:
            if not self.is_cancelled:
                self.error_signal.emit(str(e))
        
        finally:
            # Always write debug log, even on error
            debug_file = os.path.join(self.live_dir, "_debug.log")
            try:
                with open(debug_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(self.debug_log))
            except Exception:
                pass

    def _find_output(self) -> str:
        """Find the LARGEST non-fragment file — more reliable than newest mtime."""
        try:
            files = [
                os.path.join(self.live_dir, f)
                for f in os.listdir(self.live_dir)
                if not re.search(r"\.(part|ytdl)(-Frag\d+)?$", f, re.IGNORECASE)
                and os.path.isfile(os.path.join(self.live_dir, f))
            ]
            if files:
                return max(files, key=os.path.getsize)
        except Exception:
            pass
        return ""

    def cancel(self):
        self.is_cancelled = True
        if self._proc and self._proc.poll() is None:
            if os.name == "nt":
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(self._proc.pid)],
                        capture_output=True,
                    )
                except Exception:
                    self._proc.terminate()
            else:
                import signal as _sig
                try:
                    self._proc.send_signal(_sig.SIGTERM)
                except Exception:
                    self._proc.terminate()


class DownloadManager:
    def __init__(self):
        self._lock                 = threading.Lock()   # FIXED: was missing
        self.active_downloads      = []
        self.download_queue        = []
        self.max_concurrent        = 2

    def add_download(self, url: str, path: str, opts: dict = None):
        with self._lock:
            t = DownloadThread(url, path, opts or {})
            if len(self.active_downloads) < self.max_concurrent:
                self._start(t)
            else:
                self.download_queue.append(t)

    def _start(self, t: DownloadThread):
        self.active_downloads.append(t)
        t.finished_signal.connect(lambda _: self._on_done(t))
        t.start()

    def _on_done(self, t: DownloadThread):
        with self._lock:
            self.active_downloads.discard(t) if hasattr(
                self.active_downloads, "discard") else None
            if t in self.active_downloads:
                self.active_downloads.remove(t)
            if self.download_queue:
                self._start(self.download_queue.pop(0))

    def cancel_all(self):
        with self._lock:
            for t in list(self.active_downloads):
                t.cancel()
            self.download_queue.clear()


# ─────────────────────────────────────────────────────────
#  Shared stylesheet helpers
# ─────────────────────────────────────────────────────────

_BTN_BLUE = """
    QPushButton {
        background-color: #0d47a1; color: white;
        border: none; border-radius: 4px;
        padding: 8px 15px; font-size: 13px; font-weight: bold;
    }
    QPushButton:hover   { background-color: #1565c0; }
    QPushButton:pressed { background-color: #0a3d8f; }
    QPushButton:disabled{ background-color: #555; color: #999; }
"""
_BTN_RED = """
    QPushButton {
        background-color: #b71c1c; color: white;
        border: none; border-radius: 4px;
        padding: 8px 15px; font-size: 13px; font-weight: bold;
    }
    QPushButton:hover   { background-color: #c62828; }
    QPushButton:pressed { background-color: #8b0000; }
    QPushButton:disabled{ background-color: #555; color: #999; }
"""
_COMBO = """
    QComboBox {
        background-color: #363636; color: #fff;
        border: 1px solid #4a4a4a; border-radius: 4px;
        padding: 5px 10px; min-height: 30px; font-size: 13px;
    }
    QComboBox::drop-down { border: none; }
    QComboBox QAbstractItemView {
        background-color: #363636; color: #fff;
        selection-background-color: #0d47a1;
    }
"""
_INPUT = """
    QLineEdit {
        background-color: #2b2b2b; color: #fff;
        border: 2px solid #1e1e1e; border-radius: 4px;
        padding: 5px 10px; font-size: 13px;
    }
    QLineEdit:focus { border: 2px solid #0d47a1; }
"""
_GROUP = """
    QGroupBox {
        background-color: #2d2d2d; border-radius: 6px;
        border: 1px solid #3d3d3d; color: #fff;
        font-size: 14px; font-weight: bold;
        padding: 15px; margin-top: 10px;
    }
    QGroupBox::title {
        subcontrol-origin: margin; left: 10px; padding: 0 5px;
    }
"""


# ─────────────────────────────────────────────────────────
#  Main Window
# ─────────────────────────────────────────────────────────

class VideoDownloader(QMainWindow):

    # ── Construction ──────────────────────────────────────
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Youtility")

        # ── App icon ──
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        self.tray_icon = QSystemTrayIcon(self)   # always create tray icon

        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
            self.setWindowIcon(icon)
            self.tray_icon.setIcon(icon)
            if os.name == "nt":
                try:
                    import ctypes
                    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                        "consolaktif.youtility.1.0"
                    )
                except Exception:
                    pass
        else:
            print(f"Icon file not found: {icon_path}")

        # ── Tray menu ──
        tray_menu = QMenu()
        tray_menu.addAction("Show",  self.show)
        tray_menu.addAction("Quit",  app.quit)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.setToolTip("Youtility")
        self.tray_icon.setVisible(True)

        # ── State ──
        self.active_download       = None
        self.active_playlist_dl    = None
        self.active_live_dl        = None
        self._info_thread          = None
        self._thumbnail_thread     = None
        self._playlist_info_thread = None
        self.download_path         = os.path.expanduser("~/Downloads")
        self._playlist_entries     = []
        self._live_dir             = ""
        self._live_record_start    = None   # datetime when recording started
        # Rolling speed averages (smoothing)
        self._speed_samples        = deque(maxlen=8)
        self._live_speed_samples   = deque(maxlen=8)
        self._pl_speed_samples     = deque(maxlen=8)

        self.download_manager = DownloadManager()

        self.setup_ui_style()
        self.init_ui()
        self.load_settings()

    # ── Global stylesheet ──────────────────────────────────
    def setup_ui_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #2b2b2b; color: #fff; }
            QTabWidget::pane     { border: 1px solid #3a3a3a; }
            QTabBar::tab {
                background-color: #3a3a3a; color: #fff;
                padding: 8px 20px; margin: 2px;
            }
            QTabBar::tab:selected { background-color: #4a4a4a; }
            QLabel  { color: #fff; }
            QLineEdit {
                background-color: #3a3a3a; color: #fff;
                padding: 5px; border: 1px solid #4a4a4a;
            }
            QPushButton {
                background-color: #0d47a1; color: #fff;
                padding: 8px 15px; border: none; border-radius: 4px;
            }
            QPushButton:hover    { background-color: #1565c0; }
            QPushButton:disabled { background-color: #555; color: #999; }
            QComboBox {
                background-color: #3a3a3a; color: #fff;
                padding: 5px; border: 1px solid #4a4a4a;
            }
            QProgressBar {
                border: 1px solid #3a3a3a; border-radius: 4px;
                text-align: center; height: 25px;
            }
            QProgressBar::chunk { background-color: #0d47a1; border-radius: 3px; }
            QTableWidget {
                background-color: #2b2b2b; color: #e0e0e0;
                gridline-color: #383838; border: 1px solid #383838;
                border-radius: 4px; selection-background-color: #1976d2;
            }
            QTableWidget::item {
                padding: 6px; border-bottom: 1px solid #383838; font-size: 13px;
            }
            QTableWidget::item:selected { background-color: #1976d2; color: #fff; }
            QHeaderView::section {
                background-color: #232323; color: #90caf9;
                padding: 8px; border: none;
                border-right: 1px solid #383838;
                border-bottom: 2px solid #1976d2;
                font-weight: bold; font-size: 13px;
            }
            QScrollBar:vertical {
                background-color: #2b2b2b; width: 10px; margin: 0;
            }
            QScrollBar::handle:vertical {
                background-color: #424242; border-radius: 5px; min-height: 20px;
            }
            QScrollBar::handle:vertical:hover { background-color: #4f4f4f; }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical { height: 0; }
            QCheckBox { color: #fff; font-size: 13px; }
            QCheckBox::indicator {
                width: 16px; height: 16px;
                border: 1px solid #4a4a4a; border-radius: 3px;
                background-color: #3a3a3a;
            }
            QCheckBox::indicator:checked { background-color: #0d47a1; }
            QGroupBox {
                background-color: #2d2d2d; border-radius: 6px;
                border: 1px solid #3d3d3d; color: #fff;
                font-size: 14px; font-weight: bold;
                padding: 15px; margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 10px; padding: 0 5px;
            }
        """)

    # ── Tabs ──────────────────────────────────────────────
    def init_ui(self):
        self.setMinimumSize(750, 680)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.youtube_tab  = QWidget()
        self.playlist_tab = QWidget()
        self.live_tab     = QWidget()
        self.codec_tab    = QWidget()
        self.history_tab  = QWidget()
        self.settings_tab = QWidget()

        self.tabs.addTab(self.youtube_tab,  "📺  YouTube")
        self.tabs.addTab(self.playlist_tab, "📋  Playlist")
        self.tabs.addTab(self.live_tab,     "🔴  Live Stream")
        self.tabs.addTab(self.codec_tab,    "🔄  Video Codec")
        self.tabs.addTab(self.history_tab,  "📜  History")
        self.tabs.addTab(self.settings_tab, "⚙️  Settings")

        self.setup_youtube_tab()
        self.setup_playlist_tab()
        self.setup_live_tab()
        self.setup_codec_tab()
        self.setup_history_tab()
        self.setup_settings_tab()
        

    # ══════════════════════════════════════════════════════
    #  1. YOUTUBE TAB
    # ══════════════════════════════════════════════════════

    def setup_youtube_tab(self):
        layout = QVBoxLayout(self.youtube_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # FFmpeg warning banner
        self.ffmpeg_warning_banner = QWidget()
        self.ffmpeg_warning_banner.setStyleSheet(
            "QWidget { border-radius:4px; padding:10px; margin-bottom:10px; }"
        )
        banner_layout = QHBoxLayout(self.ffmpeg_warning_banner)
        banner_layout.setContentsMargins(10, 10, 10, 10)
        w_txt = QLabel("⚠️  FFmpeg is not installed. It is required for video downloading.")
        w_txt.setStyleSheet("color:#fff; font-size:13px; border:1px solid #404040;")
        banner_layout.addWidget(w_txt)
        inst_btn = QPushButton("Install FFmpeg")
        inst_btn.setStyleSheet(
            "QPushButton{background:#cf0000;color:white;border:none;border-radius:4px;"
            "padding:10px 15px;font-size:12px;font-weight:bold;}"
            "QPushButton:hover{background:#e30202;}"
        )
        inst_btn.clicked.connect(self.download_ffmpeg)
        banner_layout.addWidget(inst_btn)
        layout.addWidget(self.ffmpeg_warning_banner)
        self.ffmpeg_warning_banner.hide()

        # Hero area (logo + URL input)
        main_container = QWidget()
        main_layout    = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(30)

        self.url_wrapper        = QWidget()
        self.url_wrapper_layout = QVBoxLayout(self.url_wrapper)
        self.url_wrapper_layout.setContentsMargins(0, 50, 0, 50)

        # Logo + title
        self.logo_container = QWidget()
        logo_layout = QVBoxLayout(self.logo_container)
        logo_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo_lbl = QLabel()
        logo_px  = QPixmap("icon.ico").scaled(
            128, 128,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        logo_lbl.setPixmap(logo_px)
        logo_layout.addWidget(logo_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        title_lbl = QLabel("Download YouTube Video")
        title_lbl.setStyleSheet("color:#fff; font-size:24px; font-weight:bold; margin-top:10px;")
        logo_layout.addWidget(title_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        sub_lbl = QLabel("Paste a YouTube link to get started.")
        sub_lbl.setStyleSheet("color:#b0b0b0; font-size:14px;")
        logo_layout.addWidget(sub_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        self.url_wrapper_layout.addWidget(self.logo_container)

        # URL input row
        self.url_container = QWidget()
        self.url_container.setStyleSheet(
            "QWidget{background-color:#363636;border-radius:8px;padding:20px;}"
        )
        url_row = QHBoxLayout(self.url_container)
        url_row.setContentsMargins(10, 10, 10, 10)
        url_row.setSpacing(8)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(
            "Copy the YouTube video link then press 'Paste'."
        )
        self.url_input.setMinimumHeight(45)
        self.url_input.setStyleSheet(_INPUT)
        self.url_input.returnPressed.connect(self._on_enter_pressed)

        self.paste_button = QPushButton("Paste")
        self.paste_button.setMinimumHeight(45)
        self.paste_button.setFixedWidth(120)
        self.paste_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.paste_button.setStyleSheet(_BTN_BLUE)
        self.paste_button.clicked.connect(self.paste_url)

        url_row.addWidget(self.url_input)
        url_row.addWidget(self.paste_button)
        self.url_wrapper_layout.addWidget(self.url_container)

        main_layout.addWidget(self.url_wrapper)
        layout.addWidget(main_container)

        # Video info container (hidden until URL fetched)
        self.video_info_container = QWidget()
        vi_layout = QVBoxLayout(self.video_info_container)
        vi_layout.setContentsMargins(0, 0, 0, 0)
        vi_layout.setSpacing(15)

        # Thumbnail + metadata row
        info_row        = QWidget()
        info_row_layout = QHBoxLayout(info_row)
        info_row_layout.setContentsMargins(0, 0, 0, 0)
        info_row_layout.setSpacing(15)

        # Left: thumbnail
        left_panel = QWidget()
        left_panel.setFixedWidth(320)
        left_lyt = QVBoxLayout(left_panel)
        left_lyt.setContentsMargins(0, 0, 0, 0)
        left_lyt.setSpacing(8)

        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(320, 180)
        self.thumbnail_label.setStyleSheet("border:1px solid #3a3a3a; border-radius:4px;")
        self.thumbnail_label.setScaledContents(True)

        self.download_thumbnail_btn = QPushButton("⬇ Download Thumbnail")
        self.download_thumbnail_btn.setFixedWidth(320)
        self.download_thumbnail_btn.setStyleSheet(_BTN_BLUE)
        self.download_thumbnail_btn.clicked.connect(self.download_thumbnail)

        left_lyt.addWidget(self.thumbnail_label)
        left_lyt.addWidget(self.download_thumbnail_btn)
        info_row_layout.addWidget(left_panel)

        # Right: metadata
        right_panel = QWidget()
        right_lyt   = QVBoxLayout(right_panel)
        right_lyt.setContentsMargins(0, 0, 0, 0)
        right_lyt.setSpacing(12)

        _stat_style = """
            QLabel {
                color:#e0e0e0; font-size:13px; padding:8px 12px;
                background-color:#2d2d2d; border-radius:6px;
                border:1px solid #3d3d3d;
            }
        """
        self.title_label       = QLabel()
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(
            "QLabel{color:#fff;font-size:15px;font-weight:bold;"
            "padding:8px 12px;background-color:#2d2d2d;"
            "border-radius:6px;border:1px solid #3d3d3d;}"
        )
        self.channel_label     = QLabel()
        self.channel_label.setStyleSheet(
            "QLabel{color:#8721fc;font-size:14px;font-weight:bold;"
            "padding:8px 12px;background-color:#2d2d2d;"
            "border-radius:6px;border:1px solid #3d3d3d;}"
        )
        self.duration_label    = QLabel()
        self.duration_label.setStyleSheet(_stat_style)
        self.views_label       = QLabel()
        self.views_label.setStyleSheet(_stat_style)
        self.upload_date_label = QLabel()
        self.upload_date_label.setStyleSheet(_stat_style)

        right_lyt.addWidget(self.title_label)
        right_lyt.addWidget(self.channel_label)
        right_lyt.addWidget(self.duration_label)
        right_lyt.addWidget(self.views_label)
        right_lyt.addWidget(self.upload_date_label)
        right_lyt.addStretch()
        info_row_layout.addWidget(right_panel)
        vi_layout.addWidget(info_row)

        # Format table
        self.format_table = QTableWidget()
        self.format_table.setMinimumHeight(150)
        self.format_table.setColumnCount(5)
        self.format_table.setHorizontalHeaderLabels(
            ["Quality", "Format", "Resolution", "FPS", "Size"]
        )
        hdr = self.format_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.format_table.verticalHeader().setVisible(False)
        self.format_table.setShowGrid(True)
        self.format_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.format_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        vi_layout.addWidget(self.format_table)

        # Format table'dan sonra, btn_row'dan önce:
        time_row = QWidget()
        time_lyt = QHBoxLayout(time_row)
        time_lyt.setContentsMargins(0, 0, 0, 0)
        time_lyt.setSpacing(8)

        self.yt_time_range_cb = QCheckBox("Download specific time range")
        self.yt_time_range_cb.setStyleSheet("color:#b0b0b0; font-size:12px;")
        time_lyt.addWidget(self.yt_time_range_cb)

        self.yt_start_time = QLineEdit()
        self.yt_start_time.setPlaceholderText("00:00:00")
        self.yt_start_time.setFixedWidth(80)
        self.yt_start_time.setStyleSheet(_INPUT)
        self.yt_start_time.hide()
        time_lyt.addWidget(self.yt_start_time)

        self.yt_end_time = QLineEdit()
        self.yt_end_time.setPlaceholderText("00:00:00")
        self.yt_end_time.setFixedWidth(80)
        self.yt_end_time.setStyleSheet(_INPUT)
        self.yt_end_time.hide()
        time_lyt.addWidget(self.yt_end_time)
        time_lyt.addStretch()
        vi_layout.addWidget(time_row)

        # Checkbox toggle
        self.yt_time_range_cb.toggled.connect(lambda checked: (
            self.yt_start_time.show() if checked else self.yt_start_time.hide(),
            self.yt_end_time.show()   if checked else self.yt_end_time.hide(),
        ))

        # Download buttons
        btn_row = QWidget()
        btn_lyt = QHBoxLayout(btn_row)
        btn_lyt.setContentsMargins(0, 0, 0, 0)
        btn_lyt.setSpacing(10)

        self.download_button     = QPushButton("⬇ Download Video")
        self.mp3_download_button = QPushButton("🎵 Download MP3")
        for b in (self.download_button, self.mp3_download_button):
            b.setMinimumHeight(36)
            b.setStyleSheet(_BTN_BLUE)
        self.download_button.clicked.connect(lambda: self.start_download(mp3_only=False))
        self.mp3_download_button.clicked.connect(lambda: self.start_download(mp3_only=True))
        self.download_button.setEnabled(False)
        btn_lyt.addWidget(self.download_button)
        btn_lyt.addWidget(self.mp3_download_button)
        vi_layout.addWidget(btn_row)

        # Progress section
        self.progress_container = QWidget()
        prog_lyt = QVBoxLayout(self.progress_container)
        prog_lyt.setContentsMargins(0, 0, 0, 0)
        prog_lyt.setSpacing(5)

        prog_row     = QWidget()
        prog_row_lyt = QHBoxLayout(prog_row)
        prog_row_lyt.setContentsMargins(0, 0, 0, 0)
        prog_row_lyt.setSpacing(10)

        self.download_progress = QProgressBar()
        self.download_progress.setMinimumHeight(25)

        self.cancel_button = QPushButton("⏹ Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.setFixedWidth(100)
        self.cancel_button.setStyleSheet(_BTN_RED)
        self.cancel_button.clicked.connect(self.cancel_download)

        prog_row_lyt.addWidget(self.download_progress)
        prog_row_lyt.addWidget(self.cancel_button)
        prog_lyt.addWidget(prog_row)

        details_row = QWidget()
        det_lyt     = QHBoxLayout(details_row)
        det_lyt.setContentsMargins(0, 0, 0, 0)

        self.download_speed   = QLabel("Speed: -- MB/s")
        self.download_eta     = QLabel("Remaining: --:--:--")
        self.download_size    = QLabel("Size: -- MB / -- MB")
        self.download_percent = QLabel("Progress: 0%")
        for lbl in (self.download_speed, self.download_eta,
                    self.download_size, self.download_percent):
            lbl.setStyleSheet("color:#b0b0b0; font-size:12px;")
            det_lyt.addWidget(lbl)

        prog_lyt.addWidget(details_row)
        vi_layout.addWidget(self.progress_container)

        layout.addWidget(self.video_info_container)
        self.video_info_container.hide()
        layout.addStretch()

        # Signals
        self.format_table.itemSelectionChanged.connect(self.update_download_button)
        self.url_input.textChanged.connect(self.on_url_changed)

    # ── YouTube helpers ────────────────────────────────────

    def update_download_button(self):
        self.download_button.setEnabled(
            len(self.format_table.selectedItems()) > 0
        )

    def paste_url(self):
        try:
            clipboard = QApplication.clipboard()
            text = clipboard.text().strip()
            if not text:
                return
            self.url_input.setText(text)
            # If URL contains a playlist list= param, redirect to Playlist tab
            if self._url_has_playlist(text):
                self.pl_url_input.setText(text)
                self.tabs.setCurrentWidget(self.playlist_tab)
                self.fetch_playlist_info()
            else:
                self._start_info_fetch(text)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not read clipboard: {e}")

    def _on_enter_pressed(self):
        url = self.url_input.text().strip()
        if not url:
            return
        if self._url_has_playlist(url):
            self.pl_url_input.setText(url)
            self.tabs.setCurrentWidget(self.playlist_tab)
            self.fetch_playlist_info()
        else:
            self._start_info_fetch(url)

    @staticmethod
    def _url_has_playlist(url: str) -> bool:
        """Returns True if the URL contains a list= parameter (i.e. is a playlist URL)."""
        import urllib.parse
        try:
            params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            return "list" in params
        except Exception:
            return False

    def on_url_changed(self):
        """Only update the UI layout; do NOT auto-fetch on every keystroke."""
        url = self.url_input.text().strip()
        if url:
            self.url_wrapper_layout.setContentsMargins(0, 10, 0, 10)
            self.logo_container.hide()
            self.url_container.setStyleSheet(
                "QWidget{background-color:#363636;border-radius:4px;padding:8px;}"
            )
            self.url_input.setMinimumHeight(36)
            self.paste_button.setMinimumHeight(36)
        else:
            self.reset_url_view()

    def _start_info_fetch(self, url: str):
        # Cancel any ongoing fetch
        if self._info_thread and self._info_thread.isRunning():
            self._info_thread.terminate()
            self._info_thread.wait(1000)

        self.paste_button.setText("Fetching...")
        self.paste_button.setEnabled(False)
        self.video_info_container.hide()

        self._info_thread = InfoFetchThread(url)
        self._info_thread.info_ready.connect(self._on_info_ready)
        self._info_thread.error.connect(self._on_info_error)
        self._info_thread.start()

    def _on_info_ready(self, info: dict):
        self.paste_button.setText("Paste")
        self.paste_button.setEnabled(True)

        # Auto-redirect live streams to Live Stream tab
        is_live = (
            info.get("is_live") or
            info.get("was_live") or
            info.get("live_status") in ("is_live", "is_upcoming") or
            info.get("duration") is None   # live/unknown duration = probably live
        )
        if is_live:
            url = self.url_input.text().strip()
            self.live_url_input.setText(url)
            self.tabs.setCurrentWidget(self.live_tab)
            self._fetch_live_info(url, info)
            return

        self.update_video_info(info)

    def _on_info_error(self, error: str):
        self.paste_button.setText("Paste")
        self.paste_button.setEnabled(True)
        self.reset_url_view()
        QMessageBox.warning(self, "Error", f"Could not fetch video info:\n{error}")

    def reset_url_view(self):
        self.url_wrapper_layout.setContentsMargins(0, 50, 0, 50)
        self.logo_container.show()
        self.url_container.setStyleSheet(
            "QWidget{background-color:#363636;border-radius:8px;padding:20px;}"
        )
        self.url_input.setMinimumHeight(45)
        self.paste_button.setMinimumHeight(45)
        self.paste_button.setText("Paste")
        self.paste_button.setEnabled(True)
        self.video_info_container.hide()

    def update_video_info(self, info: dict):
        self.video_info_container.show()

        # Thumbnail (async)
        thumb_url = info.get("thumbnail")
        self.current_thumbnail_url = thumb_url
        if thumb_url:
            if self._thumbnail_thread and self._thumbnail_thread.isRunning():
                self._thumbnail_thread.terminate()
            self._thumbnail_thread = ThumbnailThread(thumb_url)
            self._thumbnail_thread.finished.connect(self._on_thumbnail_ready)
            self._thumbnail_thread.start()

        # Title
        title = info.get("title", "Unknown Title")
        self.title_label.setText(f"📹  {title}")
        self.title_label.setMaximumWidth(500)

        # Channel
        channel = info.get("uploader", "Unknown Channel")
        self.channel_label.setText(f"👤  {channel}")

        # Duration
        dur = info.get("duration")
        if dur:
            h, r = divmod(int(dur), 3600)
            m, s = divmod(r, 60)
            dur_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
            self.duration_label.setText(f"⏱  Duration: {dur_str}")
        else:
            self.duration_label.setText("⏱  Duration: Unknown")

        if dur:
            h, r = divmod(int(dur), 3600)
            m, s = divmod(r, 60)
            self.yt_end_time.setText(f"{h:02d}:{m:02d}:{s:02d}")
            self.yt_start_time.setText("00:00:00")

        # Views
        views = info.get("view_count", 0) or 0
        if views >= 1_000_000:
            v_str = f"{views / 1_000_000:.1f}M"
        elif views >= 1_000:
            v_str = f"{views / 1_000:.1f}K"
        else:
            v_str = str(views)
        self.views_label.setText(f"👁  Views: {v_str}")

        # Upload date
        ud = info.get("upload_date", "")
        if ud:
            try:
                d = datetime.strptime(ud, "%Y%m%d")
                self.upload_date_label.setText(
                    f"📅  Released: {d.strftime('%d %B %Y')}"
                )
            except Exception:
                self.upload_date_label.setText("📅  Released: Unknown")
        else:
            self.upload_date_label.setText("📅  Released: Unknown")

        self.update_format_table(info)

    def _on_thumbnail_ready(self, data: bytes):
        px = QPixmap()
        px.loadFromData(data)
        self.thumbnail_label.setPixmap(px)
        self.thumbnail_label.setScaledContents(True)

    def update_format_table(self, info: dict):
        self.format_table.setRowCount(0)
        formats = info.get("formats", [])

        video_formats = [
            f for f in formats
            if f.get("vcodec") != "none" and f.get("height") is not None
        ]
        video_formats.sort(
            key=lambda x: (x.get("height", 0) or 0, x.get("filesize", 0) or 0),
            reverse=True,
        )

        seen_res = set()
        for f in video_formats:
            res = f.get("height", 0)
            if res in seen_res:
                continue
            seen_res.add(res)

            row = self.format_table.rowCount()
            self.format_table.insertRow(row)

            height = f.get("height", 0) or 0
            width  = f.get("width",  0) or 0

            # Hem genişliği hem yüksekliği kontrol et
            if width >= 7680 or height >= 4320:
                q_text = "8K"
            elif width >= 3840 or height >= 2160:
                q_text = "4K"
            elif width >= 2560 or height >= 1440:
                q_text = "2K"
            else:
                q_text = f"{height}p"

            q_item = QTableWidgetItem(q_text)
            q_item.setData(Qt.ItemDataRole.UserRole, f.get("format_id"))
            q_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            fmt_item = QTableWidgetItem(f.get("ext", "N/A"))
            fmt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            w = f.get("width", "N/A")
            res_item = QTableWidgetItem(f"{w}x{res}" if w != "N/A" else "N/A")
            res_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            fps = f.get("fps", "N/A")
            fps_item = QTableWidgetItem(f"{fps} FPS" if fps != "N/A" else "N/A")
            fps_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            fsize = f.get("filesize", 0)
            if fsize:
                s_str = (f"{fsize/1024**3:.1f} GB"
                         if fsize > 1024**3 else f"{fsize/1024**2:.1f} MB")
            else:
                s_str = "N/A"
            sz_item = QTableWidgetItem(s_str)
            sz_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            for col, item in enumerate([q_item, fmt_item, res_item, fps_item, sz_item]):
                item.setForeground(QColor("#e0e0e0"))
                self.format_table.setItem(row, col, item)

        if self.format_table.rowCount() > 0:
            self.format_table.selectRow(0)

    def download_thumbnail(self):
        if not hasattr(self, "current_thumbnail_url") or not self.current_thumbnail_url:
            return
        try:
            # title_label yerine info'dan al, o da yoksa URL'den türet
            raw_title = self.title_label.text().replace("📹  ", "").strip()
            
            if not raw_title:
                # Fallback: URL'den video ID al
                parsed = urllib.parse.urlparse(self.url_input.text())
                vid_id = urllib.parse.parse_qs(parsed.query).get("v", ["thumbnail"])[0]
                raw_title = vid_id
                
            safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw_title).strip(". ")[:100]
            if not safe_title:
                safe_title = "thumbnail"

            resp = requests.get(self.current_thumbnail_url, timeout=10)
            if resp.status_code != 200:
                QMessageBox.warning(self, "Error",
                    f"Thumbnail download failed (HTTP {resp.status_code})")
                return
            px = QPixmap()
            px.loadFromData(resp.content)
            out, _ = QFileDialog.getSaveFileName(
                self, "Save Thumbnail",
                os.path.join(self.get_download_path(), f"{safe_title}.jpg"),
                "JPEG (*.jpg)",
            )
            if out:
                px.save(out, "JPG", quality=100)
                QMessageBox.information(self, "Success", "Thumbnail saved!")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not save thumbnail:\n{e}")

    def start_download(self, mp3_only: bool = False):
        try:
            url = self.url_input.text().strip()
            if not url:
                QMessageBox.warning(self, "Warning", "Please enter a valid URL.")
                return

            download_path = self.get_download_path()
            self.download_button.setEnabled(False)
            self.mp3_download_button.setEnabled(False)

            speed_opts = {
                "concurrent_fragment_downloads": 10,
                "buffersize": 16384,
            }

            if mp3_only:
                self.mp3_conversion_mode = True
                self.mp3_download_button.setText("Downloading MP3...")
                bitrate = self.audio_quality_combo.currentText()
                bitrate_tag = bitrate.replace("k", "") if bitrate != "Best" else "320"
                ydl_opts = {
                    "format": "bestaudio/best",
                    "outtmpl": os.path.join(download_path, f"%(title)s_{bitrate_tag}k.%(ext)s"),
                    "quiet": True, "no_warnings": True,
                    **speed_opts,
                }
                if self.yt_time_range_cb.isChecked():
                    start_t = self.yt_start_time.text().strip()
                    end_t   = self.yt_end_time.text().strip()
                    if start_t and end_t:
                        ydl_opts["download_ranges"] = yt_dlp.utils.download_range_func(
                            None, [(self._to_seconds(start_t), self._to_seconds(end_t))]
                        )
                        ydl_opts["force_keyframes_at_cuts"] = True
                        self.download_progress.setRange(0, 0)
                        self.download_percent.setText("Progress: cutting...")
            else:
                self.mp3_conversion_mode = False
                self.download_button.setText("Downloading...")
                selected = self.format_table.selectedItems()
                if not selected:
                    QMessageBox.warning(self, "Warning", "Please select a format.")
                    self.reset_download_state()
                    return
                fmt_id = self.format_table.item(selected[0].row(), 0).data(
                    Qt.ItemDataRole.UserRole
                )
                ydl_opts = {
                    "format": f"{fmt_id}+bestaudio/best",
                    "outtmpl": os.path.join(download_path, "%(title)s_%(height)sp.%(ext)s"),
                    "merge_output_format": "mkv",
                    "keepvideo": False,
                    "quiet": True, "no_warnings": True,
                    "postprocessors": [
                        {"key": "FFmpegVideoConvertor", "preferedformat": "mkv"},
                        {"key": "FFmpegVideoRemuxer",   "preferedformat": "mkv"},
                    ],'extractor_args': {
                        'youtube': {
                            'player_client': ['web', 'android'],
                        }
                    },
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    },
                    **speed_opts,
                }
                if self.yt_time_range_cb.isChecked():
                    start_t = self.yt_start_time.text().strip()
                    end_t   = self.yt_end_time.text().strip()
                    if start_t and end_t:
                        ydl_opts["download_ranges"] = yt_dlp.utils.download_range_func(
                            None, [(self._to_seconds(start_t), self._to_seconds(end_t))]
                        )
                        ydl_opts["force_keyframes_at_cuts"] = True
                    elif start_t:
                        ydl_opts["download_ranges"] = yt_dlp.utils.download_range_func(
                            None, [(self._to_seconds(start_t), float("inf"))]
                        )
                        ydl_opts["force_keyframes_at_cuts"] = True
                        self.download_progress.setRange(0, 0)

            self.active_download = DownloadThread(url, download_path, ydl_opts)
            self.active_download.progress_signal.connect(self.update_progress)
            self.active_download.error_signal.connect(self.on_download_error)
            self.active_download.finished_signal.connect(self.on_download_complete)
            self.active_download.status_signal.connect(self._on_download_status)
            self.active_download.start()
            self.cancel_button.setEnabled(True)
            self._speed_samples.clear()

        except Exception as e:
            self.on_download_error(str(e))


    def _on_download_status(self, status: str):
        if status == "merging":
            self.download_progress.setRange(0, 0)
            self.download_speed.setText("Speed: --")
            self.download_eta.setText("Remaining: --")
        
        if self.yt_time_range_cb.isChecked():
            self.download_percent.setText("FFmpeg Cutting...")
        else:
            self.download_percent.setText("Video+Audio Merging...")

    def update_progress(self, d: dict):
        try:
            if d["status"] != "downloading":
                return

            raw_speed = d.get("speed", 0) or 0
            if raw_speed > 0:
                self._speed_samples.append(raw_speed)
            speed = sum(self._speed_samples) / len(self._speed_samples) if self._speed_samples else 0

            # ── YENİ: veri gelince range'i sıfırla ──────────────────
            total      = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0) or 0

            if total:
                pct = (downloaded / total) * 100
                self.download_progress.setRange(0, 100)   # ← indeterminate'den çıkar
                self.download_progress.setValue(int(pct))
                self.download_percent.setText(f"Progress: {pct:.1f}%")
            else:
                # total bilinmiyor ama downloaded var — en azından onu göster
                self.download_progress.setRange(0, 0)
                if downloaded > 1024**2:
                    self.download_percent.setText(
                        f"İndirilen: {downloaded/1024**2:.1f} MB"
                    )
            # ─────────────────────────────────────────────────────────

            if speed > 1024**2:
                self.download_speed.setText(f"Speed: {speed/1024**2:.1f} MB/s")
            elif speed > 0:
                self.download_speed.setText(f"Speed: {speed/1024:.1f} KB/s")
            else:
                self.download_speed.setText("Speed: --")

            if total:
                if total > 1024**3:
                    sz = f"Size: {downloaded/1024**3:.2f} GB / {total/1024**3:.2f} GB"
                else:
                    sz = f"Size: {downloaded/1024**2:.1f} MB / {total/1024**2:.1f} MB"
            else:
                if downloaded > 1024**3:
                    sz = f"İndirilen: {downloaded/1024**3:.2f} GB"
                else:
                    sz = f"İndirilen: {downloaded/1024**2:.1f} MB"
            self.download_size.setText(sz)

            eta = d.get("eta")
            if eta is not None:
                m, s = divmod(int(eta), 60)
                h, m = divmod(m, 60)
                self.download_eta.setText(
                    f"Remaining: {h:02d}:{m:02d}:{s:02d}" if h
                    else f"Remaining: {m:02d}:{s:02d}"
                )
            else:
                self.download_eta.setText("Remaining: --")

        except Exception as e:
            print(f"Progress update error: {e}")

    def on_download_error(self, error: str):
        QMessageBox.critical(self, "Download Error", error)
        self.reset_download_state()

    def on_download_complete(self, downloaded_file: str):
        try:
            final_file = downloaded_file
            if getattr(self, "mp3_conversion_mode", False):
                converted = self.convert_to_mp3(downloaded_file)
                if converted:
                    final_file = converted

            self.add_to_history(
                os.path.basename(final_file),
                self.url_input.text(),
                "Finished",
                final_file,
            )
            self._show_done_dialog(final_file)
        except Exception as e:
            print(f"Post-download error: {e}")
        finally:
            self.reset_download_state()

    def _show_done_dialog(self, filepath: str, title: str = "Download Complete"):
        """Custom completion dialog with Open File/Folder and Show in Folder buttons."""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(400)
        dlg.setStyleSheet("background-color:#2b2b2b; color:#fff;")
        lyt = QVBoxLayout(dlg)
        lyt.setSpacing(14)
        lyt.setContentsMargins(20, 20, 20, 20)

        icon_lbl = QLabel("✅")
        icon_lbl.setStyleSheet("font-size:36px;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lyt.addWidget(icon_lbl)

        msg = QLabel(title)
        msg.setStyleSheet("font-size:16px; font-weight:bold; color:#fff;")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lyt.addWidget(msg)

        is_dir  = filepath and os.path.isdir(filepath)
        is_file = filepath and os.path.isfile(filepath)

        if is_file or is_dir:
            name_lbl = QLabel(os.path.basename(filepath) if is_file else filepath)
            name_lbl.setStyleSheet("font-size:12px; color:#b0b0b0;")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_lbl.setWordWrap(True)
            lyt.addWidget(name_lbl)

        btn_row = QWidget()
        btn_lyt = QHBoxLayout(btn_row)
        btn_lyt.setSpacing(8)
        btn_lyt.setContentsMargins(0, 0, 0, 0)

        open_btn   = QPushButton("📂  Open" + (" Folder" if is_dir else " File"))
        folder_btn = QPushButton("📁  Show in Folder")
        ok_btn     = QPushButton("OK")
        for b in (open_btn, folder_btn, ok_btn):
            b.setMinimumHeight(36)
            b.setStyleSheet(_BTN_BLUE)

        open_btn.setEnabled(bool(is_file or is_dir))
        folder_btn.setEnabled(bool(is_file))

        def _open():
            try:
                target = filepath
                if os.name == "nt":
                    os.startfile(target)
                elif os.name == "darwin":
                    subprocess.run(["open", target])
                else:
                    subprocess.run(["xdg-open", target])
            except Exception:
                pass

        def _show_folder():
            try:
                if os.name == "nt":
                    subprocess.run(f'explorer /select,"{filepath}"', shell=True)
                elif os.name == "darwin":
                    subprocess.run(["open", "-R", filepath])
                else:
                    subprocess.run(["xdg-open", os.path.dirname(filepath)])
            except Exception:
                pass

        open_btn.clicked.connect(_open)
        folder_btn.clicked.connect(_show_folder)
        ok_btn.clicked.connect(dlg.accept)

        btn_lyt.addWidget(open_btn)
        btn_lyt.addWidget(folder_btn)
        btn_lyt.addWidget(ok_btn)
        lyt.addWidget(btn_row)
        dlg.exec()

    def convert_to_mp3(self, input_file: str) -> str | None:
        """Convert downloaded audio to MP3 using libmp3lame (standard encoder)."""
        output = os.path.splitext(input_file)[0] + ".mp3"
        quality = getattr(self, "audio_quality_combo", None)
        bitrate = quality.currentText() if quality else "192k"
        if bitrate == "Best":
            bitrate = "320k"
            bitrate_tag = bitrate.replace("k", "")
    
        # ── Input'taki geçici ext'i at, bitrate'i ekle ──────
        base = re.sub(r"\.[a-z0-9]+$", "", input_file, flags=re.IGNORECASE)
        # Eğer zaten _320k gibi bir tag varsa üstüne ekleme
        if not base.endswith(f"_{bitrate_tag}k"):
            output = f"{base}_{bitrate_tag}k.mp3"
        else:
            output = f"{base}.mp3"
        cmd = ["ffmpeg", "-i", input_file,
               "-c:a", "libmp3lame",   # FIXED: was libshine (not in standard FFmpeg)
               "-b:a", bitrate,
               "-y", output]
        try:
            result = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace')
            if result.returncode == 0:
                # Remove original if different file
                if os.path.abspath(input_file) != os.path.abspath(output):
                    try:
                        os.remove(input_file)
                    except Exception:
                        pass
                return output
            else:
                err = result.stderr[-500:] if result.stderr else "Unknown error"
                QMessageBox.warning(self, "MP3 Conversion Error", err)
                return None
        except FileNotFoundError:
            QMessageBox.warning(self, "Error",
                "FFmpeg not found. Please install it from the Settings tab.")
            return None

    def reset_download_state(self):
        try:
            if self.active_download:
                self.active_download.is_cancelled = True
                self.active_download.quit()
                self.active_download.wait(2000)
                self.active_download = None

            self.download_button.setText("⬇ Download Video")
            self.mp3_download_button.setText("🎵 Download MP3")
            self.download_button.setEnabled(True)
            self.mp3_download_button.setEnabled(True)
            self.cancel_button.setEnabled(False)
            self.download_progress.setRange(0, 100)
            self.download_progress.setValue(0)
            self.download_speed.setText("Speed: -- MB/s")
            self.download_eta.setText("Remaining: --:--:--")
            self.download_size.setText("Size: -- MB / -- MB")
            self.download_percent.setText("Progress: 0%")
        except Exception as e:
            print(f"Reset error: {e}")

    def _to_seconds(self, t: str) -> float:
        """'HH:MM:SS' veya 'MM:SS' → saniye"""
        parts = t.strip().split(":")
        try:
            if len(parts) == 3:
                return int(parts[0])*3600 + int(parts[1])*60 + float(parts[2])
            elif len(parts) == 2:
                return int(parts[0])*60 + float(parts[1])
            else:
                return float(parts[0])
        except Exception:
            return 0.0

    def cancel_download(self):
        if not self.active_download:
            return
        reply = QMessageBox.question(
            self, "Cancel Download",
            "Are you sure you want to cancel the download?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        dl_dir = self.get_download_path()
        self.active_download.cancel()

        # Clean up partial files
        for fname in os.listdir(dl_dir):
            if fname.endswith((".part", ".temp", ".ytdl")):
                try:
                    os.remove(os.path.join(dl_dir, fname))
                except Exception:
                    pass

        self.reset_download_state()
        QMessageBox.information(self, "Cancelled",
            "Download cancelled and temporary files removed.")

    # ══════════════════════════════════════════════════════
    #  2. PLAYLIST TAB
    # ══════════════════════════════════════════════════════

    def setup_playlist_tab(self):
        layout = QVBoxLayout(self.playlist_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header
        header = QWidget()
        header.setStyleSheet("QWidget{background-color:#363636;border-radius:8px;padding:10px;}")
        hdr_lyt = QHBoxLayout(header)
        hdr_lyt.setContentsMargins(10, 10, 10, 10)
        hdr_lyt.setSpacing(12)
        
        ic = QLabel()
        ic.setPixmap(QPixmap("icon.ico").scaled(
            32, 32,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))
        hdr_lyt.addWidget(ic)

        tc = QWidget()
        tl = QVBoxLayout(tc)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(2)
        tl.addWidget(_make_label("Playlist Downloads", "color:#fff;font-size:16px;font-weight:bold;"))
        tl.addWidget(_make_label("Download entire YouTube playlists", "color:#b0b0b0;font-size:12px;"))
        hdr_lyt.addWidget(tc, 1)
        
        hdr_text = QLabel("")
        hdr_text.setStyleSheet("font-size:16px;font-weight:bold;color:#ffffff;")
        hdr_lyt.addWidget(hdr_text)
        hdr_lyt.addStretch()
        layout.addWidget(header)

        # URL input container
        url_container = QWidget()
        url_container.setStyleSheet("QWidget{background-color:#2a2a2a;border-radius:6px;padding:12px;}")
        url_lyt = QVBoxLayout(url_container)
        url_lyt.setContentsMargins(0, 0, 0, 0)
        url_lyt.setSpacing(8)
        
        input_row = QWidget()
        input_row_lyt = QHBoxLayout(input_row)
        input_row_lyt.setContentsMargins(0, 0, 0, 0)
        input_row_lyt.setSpacing(8)
        
        self.pl_url_input = QLineEdit()
        self.pl_url_input.setPlaceholderText("Paste a YouTube playlist or channel URL...")
        self.pl_url_input.setMinimumHeight(36)
        self.pl_url_input.setStyleSheet(_INPUT)
        self.pl_url_input.returnPressed.connect(self.fetch_playlist_info)
        
        self.pl_paste_btn = QPushButton("Paste")
        self.pl_paste_btn.setMinimumHeight(36)
        self.pl_paste_btn.setFixedWidth(80)
        self.pl_paste_btn.setStyleSheet(_BTN_BLUE)
        self.pl_paste_btn.clicked.connect(self.paste_playlist_url)
        
        self.pl_fetch_btn = QPushButton("Fetch")
        self.pl_fetch_btn.setMinimumHeight(36)
        self.pl_fetch_btn.setFixedWidth(80)
        self.pl_fetch_btn.setStyleSheet(_BTN_BLUE)
        self.pl_fetch_btn.clicked.connect(self.fetch_playlist_info)
        
        input_row_lyt.addWidget(self.pl_url_input)
        input_row_lyt.addWidget(self.pl_paste_btn)
        input_row_lyt.addWidget(self.pl_fetch_btn)
        url_lyt.addWidget(input_row)
        
        self.pl_info_label = QLabel("No playlist loaded")
        self.pl_info_label.setStyleSheet("color:#b0b0b0;font-size:12px;")
        url_lyt.addWidget(self.pl_info_label)
        layout.addWidget(url_container)

        # Options row (compact inline) — Quality uses settings default
        options_row = QWidget()
        options_lyt = QHBoxLayout(options_row)
        options_lyt.setContentsMargins(0, 0, 0, 0)
        options_lyt.setSpacing(12)
        
        self.pl_audio_only_cb = QCheckBox("Audio Only (MP3)")
        options_lyt.addWidget(self.pl_audio_only_cb)
        options_lyt.addStretch()
        layout.addWidget(options_row)

        # Action buttons
        action_row = QWidget()
        action_lyt = QHBoxLayout(action_row)
        action_lyt.setContentsMargins(0, 0, 0, 0)
        action_lyt.setSpacing(10)

        self.pl_start_btn = QPushButton("Start Download")
        self.pl_start_btn.setMinimumHeight(36)
        self.pl_start_btn.setStyleSheet(_BTN_BLUE)
        self.pl_start_btn.setEnabled(False)
        self.pl_start_btn.clicked.connect(self.start_playlist_download)

        self.pl_cancel_btn = QPushButton("Cancel")
        self.pl_cancel_btn.setMinimumHeight(36)
        self.pl_cancel_btn.setStyleSheet(_BTN_RED)
        self.pl_cancel_btn.setEnabled(False)
        self.pl_cancel_btn.clicked.connect(self.cancel_playlist_download)

        action_lyt.addWidget(self.pl_start_btn)
        action_lyt.addWidget(self.pl_cancel_btn)
        layout.addWidget(action_row)

        # Selection controls
        select_row = QWidget()
        select_lyt = QHBoxLayout(select_row)
        select_lyt.setContentsMargins(0, 0, 0, 0)
        select_lyt.setSpacing(8)
        
        self.pl_select_all_btn = QPushButton("✓ Select All")
        self.pl_select_all_btn.setMaximumWidth(120)
        self.pl_select_all_btn.setMinimumHeight(32)
        self.pl_select_all_btn.setStyleSheet(_BTN_BLUE)
        self.pl_select_all_btn.clicked.connect(self.select_all_playlist_videos)
        self.pl_select_all_btn.setEnabled(False)
        
        self.pl_deselect_all_btn = QPushButton("✗ Deselect All")
        self.pl_deselect_all_btn.setMaximumWidth(120)
        self.pl_deselect_all_btn.setMinimumHeight(32)
        self.pl_deselect_all_btn.setStyleSheet(_BTN_RED)
        self.pl_deselect_all_btn.clicked.connect(self.deselect_all_playlist_videos)
        self.pl_deselect_all_btn.setEnabled(False)
        
        self.pl_selected_count_lbl = QLabel("Selected: 0/0")
        self.pl_selected_count_lbl.setStyleSheet("color:#b0b0b0;font-size:12px;")
        
        select_lyt.addWidget(self.pl_select_all_btn)
        select_lyt.addWidget(self.pl_deselect_all_btn)
        select_lyt.addStretch()
        select_lyt.addWidget(self.pl_selected_count_lbl)
        layout.addWidget(select_row)

        # Playlist table
        self.pl_table = QTableWidget()
        self.pl_table.setColumnCount(4)
        self.pl_table.setHorizontalHeaderLabels(["☑", "#", "Title", "Status"])
        hdr = self.pl_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.pl_table.verticalHeader().setVisible(False)
        self.pl_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.pl_table.itemClicked.connect(self.on_playlist_item_clicked)
        layout.addWidget(self.pl_table)

        # Progress section (at bottom)
        prog_container = QWidget()
        prog_container.setStyleSheet("QWidget{background-color:#2a2a2a;border-radius:6px;padding:12px;}")
        pg_lyt = QVBoxLayout(prog_container)
        pg_lyt.setContentsMargins(0, 0, 0, 0)
        pg_lyt.setSpacing(8)

        self.pl_current_label = QLabel("Idle")
        self.pl_current_label.setStyleSheet("color:#b0b0b0;font-size:12px;")
        pg_lyt.addWidget(self.pl_current_label)

        self.pl_overall_bar = QProgressBar()
        self.pl_overall_bar.setMinimumHeight(18)
        self.pl_overall_bar.setFormat("Overall: %p%")
        pg_lyt.addWidget(self.pl_overall_bar)

        self.pl_video_bar = QProgressBar()
        self.pl_video_bar.setMinimumHeight(18)
        self.pl_video_bar.setFormat("Current: %p%")
        pg_lyt.addWidget(self.pl_video_bar)

        det_row = QWidget()
        det_lyt = QHBoxLayout(det_row)
        det_lyt.setContentsMargins(0, 0, 0, 0)
        det_lyt.setSpacing(16)
        
        self.pl_speed_lbl = QLabel("Speed: --")
        self.pl_eta_lbl = QLabel("Remaining: --")
        self.pl_size_lbl = QLabel("Size: --")
        for lbl in (self.pl_speed_lbl, self.pl_eta_lbl, self.pl_size_lbl):
            lbl.setStyleSheet("color:#b0b0b0;font-size:11px;")
            det_lyt.addWidget(lbl)
        det_lyt.addStretch()
        pg_lyt.addWidget(det_row)
        layout.addWidget(prog_container)

    def paste_playlist_url(self):
        text = QApplication.clipboard().text().strip()
        if text:
            self.pl_url_input.setText(text)

    def fetch_playlist_info(self):
        url = self.pl_url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Warning", "Please enter a playlist URL.")
            return

        self.pl_fetch_btn.setEnabled(False)
        self.pl_fetch_btn.setText("Fetching...")
        self.pl_info_label.setText("Fetching playlist info...")
        self.pl_table.setRowCount(0)
        self._playlist_entries = []

        self._playlist_info_thread = PlaylistInfoThread(url)
        self._playlist_info_thread.info_ready.connect(self.on_playlist_info_ready)
        self._playlist_info_thread.error.connect(self.on_playlist_info_error)
        self._playlist_info_thread.start()

    def on_playlist_info_ready(self, info: dict):
        self.pl_fetch_btn.setEnabled(True)
        self.pl_fetch_btn.setText("🔍 Fetch Playlist")

        entries = list(info.get("entries") or [])

        # Handle nested playlists (playlist of playlists — flatten one level)
        flat = []
        for e in entries:
            if e and e.get("_type") == "playlist" and e.get("entries"):
                flat.extend(e["entries"])
            elif e:
                flat.append(e)
        entries = [e for e in flat if e]   # remove None / private videos

        if not entries:
            # Might be a single video URL rather than a playlist
            self.pl_info_label.setText(
                "⚠️  No playlist entries found. "
                "Make sure the URL contains a 'list=' parameter."
            )
            self.pl_fetch_btn.setEnabled(True)
            self.pl_fetch_btn.setText("🔍 Fetch Playlist")
            return

        self._playlist_entries = entries

        pl_title = info.get("title") or info.get("playlist_title") or "Playlist"
        self.pl_info_label.setText(
            f"📋  <b>{pl_title}</b>  —  {len(entries)} video(s) found"
        )

        # Populate table
        self.pl_table.setRowCount(0)
        for i, entry in enumerate(entries):
            row = self.pl_table.rowCount()
            self.pl_table.insertRow(row)
            
            # Checkbox column (column 0)
            checkbox_item = QTableWidgetItem()
            checkbox_item.setCheckState(Qt.CheckState.Checked)
            checkbox_item.setFlags(checkbox_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checkbox_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.pl_table.setItem(row, 0, checkbox_item)
            
            # Index column (column 1)
            num = QTableWidgetItem(str(i + 1))
            num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.pl_table.setItem(row, 1, num)
            
            # Title column (column 2)
            title = QTableWidgetItem(entry.get("title") or f"Video {i + 1}")
            self.pl_table.setItem(row, 2, title)
            
            # Status column (column 3)
            status = QTableWidgetItem("Pending")
            status.setForeground(QColor("#b0b0b0"))
            status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.pl_table.setItem(row, 3, status)

        self.pl_start_btn.setEnabled(len(entries) > 0)
        self.pl_select_all_btn.setEnabled(len(entries) > 0)
        self.pl_deselect_all_btn.setEnabled(len(entries) > 0)
        self.update_playlist_selection_count()

    def on_playlist_info_error(self, error: str):
        self.pl_fetch_btn.setEnabled(True)
        self.pl_fetch_btn.setText("🔍 Fetch Playlist")
        self.pl_info_label.setText("Failed to fetch playlist.")
        QMessageBox.warning(self, "Error", f"Could not fetch playlist:\n{error}")

    def on_playlist_item_clicked(self, item):
        """Handle checkbox clicks to update selection counter."""
        if item.column() == 0:  # Checkbox column
            self.update_playlist_selection_count()

    def update_playlist_selection_count(self):
        """Update the selected count label."""
        total = self.pl_table.rowCount()
        selected = sum(1 for row in range(total)
                      if self.pl_table.item(row, 0).checkState() == Qt.CheckState.Checked)
        self.pl_selected_count_lbl.setText(f"Selected: {selected}/{total}")

    def select_all_playlist_videos(self):
        """Check all videos in the playlist."""
        for row in range(self.pl_table.rowCount()):
            item = self.pl_table.item(row, 0)
            item.setCheckState(Qt.CheckState.Checked)
        self.update_playlist_selection_count()

    def deselect_all_playlist_videos(self):
        """Uncheck all videos in the playlist."""
        for row in range(self.pl_table.rowCount()):
            item = self.pl_table.item(row, 0)
            item.setCheckState(Qt.CheckState.Unchecked)
        self.update_playlist_selection_count()

    def start_playlist_download(self):
        if not self._playlist_entries:
            QMessageBox.warning(self, "Warning", "Please fetch a playlist first.")
            return

        # Collect only selected entries with their original indices
        selected_entries = []
        selected_indices = []
        for row in range(self.pl_table.rowCount()):
            if self.pl_table.item(row, 0).checkState() == Qt.CheckState.Checked:
                selected_entries.append(self._playlist_entries[row])
                selected_indices.append(row)

        if not selected_entries:
            QMessageBox.warning(self, "Warning", "Please select at least one video.")
            return

        base_path  = self.get_download_path()
        # Use default quality from settings
        quality = self.video_quality_combo.currentText()
        audio_only = self.pl_audio_only_cb.isChecked()

        # Create a dedicated subfolder named after the playlist
        pl_title      = self.pl_info_label.text()
        # Extract playlist name from label "📋  <b>NAME</b> — N video(s) found"
        import html
        raw = re.sub(r"<[^>]+>", "", pl_title).strip()          # strip HTML tags
        raw = re.sub(r"\s*—.*$", "", raw).replace("📋", "").strip()
        safe_pl_name  = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw) or "Playlist"
        download_path = os.path.join(base_path, safe_pl_name)
        os.makedirs(download_path, exist_ok=True)

        speed_opts = {
            "concurrent_fragment_downloads": 10,
            "buffersize": 16384,
        }

        if audio_only:
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join(download_path, "%(title)s.%(ext)s"),
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],'extractor_args': {
                        'youtube': {
                            'player_client': ['web', 'android'],
                        }
                    },
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    },
                "quiet": True, "no_warnings": True,
                **speed_opts,
            }
        else:
            fmt = "bestvideo+bestaudio/best"
            if quality != "Best":
                h   = quality.replace("p", "")
                fmt = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]"
            ydl_opts = {
                "format": fmt,
                "outtmpl": os.path.join(download_path, "%(title)s_%(height)sp.%(ext)s"),
                "merge_output_format": "mkv",
                "quiet": True, "no_warnings": True,
                "keepvideo": False,
                "postprocessors": [
                    {"key": "FFmpegVideoConvertor", "preferedformat": "mkv"},
                    {"key": "FFmpegVideoRemuxer",   "preferedformat": "mkv"},
                ],
                **speed_opts,
            }

        self.pl_start_btn.setEnabled(False)
        self.pl_cancel_btn.setEnabled(True)
        self.pl_overall_bar.setValue(0)
        self.pl_video_bar.setValue(0)
        self.pl_current_label.setText(f"📁  Saving to: {download_path}")
        self._pl_speed_samples.clear()
        
        # Store selected indices for progress tracking
        self._pl_selected_indices = selected_indices

        self.active_playlist_dl = PlaylistDownloadThread(
            PlaylistInfoThread._to_playlist_url(self.pl_url_input.text().strip()),
            download_path,
            ydl_opts,
            selected_entries,  # Use only selected entries
        )
        self.active_playlist_dl.progress_signal.connect(self.on_playlist_video_progress)
        self.active_playlist_dl.video_started_signal.connect(self.on_playlist_video_started)
        self.active_playlist_dl.video_done_signal.connect(self.on_playlist_video_done)
        self.active_playlist_dl.error_signal.connect(self.on_playlist_error)
        self.active_playlist_dl.all_done_signal.connect(self.on_playlist_all_done)
        self.active_playlist_dl.start()

    def on_playlist_video_started(self, index: int, title: str):
        # index is 1-based from download thread (1 to len(selected_entries))
        total_selected = len(getattr(self, '_pl_selected_indices', self._playlist_entries))
        self.pl_current_label.setText(
            f"Downloading {index}/{total_selected}: {title}"
        )
        self.pl_video_bar.setValue(0)
        
        # Mark previous as done using original table row index
        if index > 1:
            prev_table_row = self._pl_selected_indices[index - 2]
            status_item = self.pl_table.item(prev_table_row, 3)  # Column 3 = Status
            if status_item:
                status_item.setText("✅ Done")
                status_item.setForeground(QColor("#4caf50"))
        
        # Mark current as downloading using original table row index
        curr_table_row = self._pl_selected_indices[index - 1]
        status_item = self.pl_table.item(curr_table_row, 3)  # Column 3 = Status
        if status_item:
            status_item.setText("⬇ Downloading")
            status_item.setForeground(QColor("#2196f3"))
        
        # Update overall progress
        overall_pct = ((index - 1) / total_selected) * 100
        self.pl_overall_bar.setValue(int(overall_pct))


    def on_playlist_video_progress(self, d: dict):
        total      = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        downloaded = d.get("downloaded_bytes", 0) or 0
        if total:
            pct = (downloaded / total) * 100
            self.pl_video_bar.setValue(int(pct))

        raw_speed = d.get("speed", 0) or 0
        if raw_speed > 0:
            self._pl_speed_samples.append(raw_speed)
        speed = sum(self._pl_speed_samples) / len(self._pl_speed_samples) if self._pl_speed_samples else 0
        if speed > 1024 ** 2:
            self.pl_speed_lbl.setText(f"Speed: {speed/1024**2:.1f} MB/s")
        elif speed > 0:
            self.pl_speed_lbl.setText(f"Speed: {speed/1024:.1f} KB/s")

        eta = d.get("eta")
        if eta is not None:
            m, s = divmod(int(eta), 60)
            h, m = divmod(m, 60)
            self.pl_eta_lbl.setText(f"Remaining: {h:02d}:{m:02d}:{s:02d}")

        if total:
            sz = (f"{downloaded/1024**2:.1f} / {total/1024**2:.1f} MB"
                  if total < 1024**3
                  else f"{downloaded/1024**3:.2f} / {total/1024**3:.2f} GB")
            self.pl_size_lbl.setText(f"Size: {sz}")

        # Overall
        total_count = len(self._playlist_entries)
        if total_count:
            done = (self.active_playlist_dl.current_index - 1) if self.active_playlist_dl else 0
            overall = ((done + (downloaded / total if total else 0)) / total_count) * 100
            self.pl_overall_bar.setValue(int(overall))

    def on_playlist_video_done(self, index: int, filepath: str):
        # index is 1-based from download thread
        table_row = self._pl_selected_indices[index - 1]
        status_item = self.pl_table.item(table_row, 3)  # Column 3 = Status
        if status_item:
            status_item.setText("✅ Done")
            status_item.setForeground(QColor("#4caf50"))
        if filepath:
            self.add_to_history(
                os.path.basename(filepath),
                self.pl_url_input.text(),
                "Finished",
                filepath,
            )

    def on_playlist_error(self, msg: str, index: int):
        if index >= 0:
            table_row = self._pl_selected_indices[index]  # index is 0-based here from thread
            status_item = self.pl_table.item(table_row, 3)  # Column 3 = Status
            if status_item:
                status_item.setText("❌ Error")
                status_item.setForeground(QColor("#f44336"))
            print(f"Playlist video {index + 1} error: {msg}")
        else:
            QMessageBox.critical(self, "Playlist Error", msg)
            self.reset_playlist_state()

    def on_playlist_all_done(self):
        # Mark last video done if not already marked
        if hasattr(self, '_pl_selected_indices') and self._pl_selected_indices:
            last_row = self._pl_selected_indices[-1]
            item = self.pl_table.item(last_row, 3)
            if item and item.text() == "⬇ Downloading":
                item.setText("✅ Done")
                item.setForeground(QColor("#4caf50"))

        self.pl_overall_bar.setValue(100)
        self.pl_current_label.setText("✅  All downloads complete!")
        self.reset_playlist_state()

        # Show completion with open-folder button
        dl_dir = ""
        if self.active_playlist_dl:
            dl_dir = self.active_playlist_dl.download_path
        elif self._playlist_entries:
            dl_dir = self.get_download_path()
        self._show_done_dialog(dl_dir, title="Playlist Download Complete")

        

    def cancel_playlist_download(self):
        if self.active_playlist_dl:
            self.active_playlist_dl.cancel()
        self.reset_playlist_state()
        self.pl_current_label.setText("Cancelled.")

    def reset_playlist_state(self):
        self.active_playlist_dl = None
        self.pl_start_btn.setEnabled(len(self._playlist_entries) > 0)
        self.pl_cancel_btn.setEnabled(False)

    # ══════════════════════════════════════════════════════
    #  3. LIVE STREAM TAB
    # ══════════════════════════════════════════════════════

    def setup_live_tab(self):
        layout = QVBoxLayout(self.live_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header
        header = QWidget()
        header.setStyleSheet("QWidget{background-color:#363636;border-radius:8px;padding:10px;}")
        hdr_lyt = QHBoxLayout(header)
        hdr_lyt.setContentsMargins(10, 10, 10, 10)
        
        ic = QLabel()
        ic.setPixmap(QPixmap("icon.ico").scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        hdr_lyt.addWidget(ic)
        
        tc = QWidget()
        tl = QVBoxLayout(tc)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(2)
        tl.addWidget(_make_label("Live Stream Recorder", "color:#fff;font-size:16px;font-weight:bold;"))
        tl.addWidget(_make_label("Record YouTube live or DVR streams", "color:#b0b0b0;font-size:12px;"))
        hdr_lyt.addWidget(tc, 1)
        layout.addWidget(header)

        # URL Input
        url_container = QWidget()
        url_container.setStyleSheet("QWidget{background-color:#363636;border-radius:8px;padding:15px;}")
        url_row = QHBoxLayout(url_container)
        url_row.setContentsMargins(5, 5, 5, 5)
        url_row.setSpacing(8)

        self.live_url_input = QLineEdit()
        self.live_url_input.setPlaceholderText("Paste YouTube live stream URL...")
        self.live_url_input.setMinimumHeight(38)
        self.live_url_input.setStyleSheet(_INPUT)

        self.live_paste_btn = QPushButton("Paste")
        self.live_paste_btn.setMinimumHeight(38)
        self.live_paste_btn.setFixedWidth(100)
        self.live_paste_btn.setStyleSheet(_BTN_BLUE)
        self.live_paste_btn.clicked.connect(self.paste_live_url)

        url_row.addWidget(self.live_url_input)
        url_row.addWidget(self.live_paste_btn)
        layout.addWidget(url_container)

        # Stream Info (hidden until fetched) - YouTube tab style
        self.live_info_group = QWidget()
        self.live_info_group.setStyleSheet("QWidget{background-color:#2d2d2d;border-radius:8px;border:1px solid #3d3d3d;padding:12px;}")
        li_lyt = QVBoxLayout(self.live_info_group)
        li_lyt.setContentsMargins(0, 0, 0, 0)
        li_lyt.setSpacing(12)

        # Thumbnail + Info row (left/right)
        info_row = QWidget()
        info_row_lyt = QHBoxLayout(info_row)
        info_row_lyt.setContentsMargins(0, 0, 0, 0)
        info_row_lyt.setSpacing(15)

        # Left: Thumbnail
        left_panel = QWidget()
        left_panel.setFixedWidth(280)
        left_lyt = QVBoxLayout(left_panel)
        left_lyt.setContentsMargins(0, 0, 0, 0)
        left_lyt.setSpacing(8)

        self.live_thumbnail = QLabel()
        self.live_thumbnail.setFixedSize(280, 157)
        self.live_thumbnail.setStyleSheet("border:1px solid #3a3a3a;border-radius:4px;background-color:#1a1a1a;")
        self.live_thumbnail.setScaledContents(True)
        self.live_thumbnail.setText("Loading...")
        self.live_thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_lyt.addWidget(self.live_thumbnail)

        download_thumb_btn = QPushButton("Download Thumbnail")
        download_thumb_btn.setFixedWidth(280)
        download_thumb_btn.setStyleSheet(_BTN_BLUE)
        download_thumb_btn.clicked.connect(self.download_live_thumbnail)
        left_lyt.addWidget(download_thumb_btn)
        info_row_lyt.addWidget(left_panel)

        # Right: Stream Info
        right_panel = QWidget()
        right_lyt = QVBoxLayout(right_panel)
        right_lyt.setContentsMargins(0, 0, 0, 0)
        right_lyt.setSpacing(10)

        self.live_info_title = QLabel("")
        self.live_info_title.setWordWrap(True)
        self.live_info_title.setStyleSheet("color:#fff;font-size:14px;font-weight:bold;padding:6px 8px;background-color:#2d2d2d;border-radius:4px;border:1px solid #3d3d3d;")
        right_lyt.addWidget(self.live_info_title)

        self.live_info_channel = QLabel("")
        self.live_info_channel.setStyleSheet("color:#8721fc;font-size:12px;font-weight:bold;padding:4px 8px;")
        right_lyt.addWidget(self.live_info_channel)

        stats_row = QWidget()
        stats_lyt = QHBoxLayout(stats_row)
        stats_lyt.setContentsMargins(0, 0, 0, 0)
        stats_lyt.setSpacing(8)

        self.live_info_status = QLabel("")
        self.live_info_status.setStyleSheet("color:#e0e0e0;font-size:12px;padding:4px 8px;background-color:#363636;border-radius:4px;border:1px solid #404040;")
        stats_lyt.addWidget(self.live_info_status)

        self.live_info_viewers = QLabel("")
        self.live_info_viewers.setStyleSheet("color:#e0e0e0;font-size:12px;padding:4px 8px;background-color:#363636;border-radius:4px;border:1px solid #404040;")
        stats_lyt.addWidget(self.live_info_viewers)
        right_lyt.addWidget(stats_row)

        right_lyt.addStretch()
        info_row_lyt.addWidget(right_panel)
        li_lyt.addWidget(info_row)

        # Fetch button
        fetch_row = QWidget()
        fetch_lyt = QHBoxLayout(fetch_row)
        fetch_lyt.setContentsMargins(0, 0, 0, 0)
        self.live_fetch_btn = QPushButton("Fetch Stream Info")
        self.live_fetch_btn.setMinimumHeight(32)
        self.live_fetch_btn.setMaximumWidth(180)
        self.live_fetch_btn.setStyleSheet(_BTN_BLUE)
        self.live_fetch_btn.clicked.connect(lambda: self._fetch_live_info(self.live_url_input.text().strip()))
        fetch_lyt.addWidget(self.live_fetch_btn)
        fetch_lyt.addStretch()
        li_lyt.addWidget(fetch_row)

        layout.addWidget(self.live_info_group)
        self.live_info_group.hide()

        # Output Format (minimal)
        opt_container = QWidget()
        opt_container.setStyleSheet("QWidget{background-color:#2d2d2d;border-radius:8px;padding:10px;border:1px solid #3d3d3d;}")
        opt_lyt = QHBoxLayout(opt_container)
        opt_lyt.setContentsMargins(8, 5, 8, 5)
        opt_lyt.setSpacing(8)

        opt_lyt.addWidget(QLabel("Output Format:"))
        self.live_format_combo = QComboBox()
        self.live_format_combo.addItems(["mkv", "mp4", "ts"])
        self.live_format_combo.setStyleSheet(_COMBO)
        self.live_format_combo.setMaximumWidth(100)
        opt_lyt.addWidget(self.live_format_combo)
        opt_lyt.addStretch()
        layout.addWidget(opt_container)

        # Timer interval options (for DVR streams)
        opt_lyt.addWidget(QLabel("Start:"))
        self.live_start_time = QLineEdit()
        self.live_start_time.hide()
        self.live_start_time.setPlaceholderText("00:00:00")
        self.live_start_time.setFixedWidth(80)
        self.live_start_time.setStyleSheet(_INPUT)
        opt_lyt.addWidget(self.live_start_time)

        opt_lyt.addWidget(QLabel("End:"))
        self.live_end_time = QLineEdit()
        self.live_end_time.hide()
        self.live_end_time.setPlaceholderText("00:00:00")
        self.live_end_time.setFixedWidth(80)
        self.live_end_time.setStyleSheet(_INPUT)
        opt_lyt.addWidget(self.live_end_time)

        # Action Buttons
        action_row = QWidget()
        act_lyt = QHBoxLayout(action_row)
        act_lyt.setContentsMargins(0, 0, 0, 0)
        act_lyt.setSpacing(10)

        self.live_start_btn = QPushButton("Start Recording")
        self.live_start_btn.setMinimumHeight(36)
        self.live_start_btn.setStyleSheet(_BTN_BLUE)
        self.live_start_btn.clicked.connect(self.start_live_download)

        self.live_stop_btn = QPushButton("Stop Recording")
        self.live_stop_btn.setMinimumHeight(36)
        self.live_stop_btn.setStyleSheet(_BTN_RED)
        self.live_stop_btn.setEnabled(False)
        self.live_stop_btn.clicked.connect(self.stop_live_download)

        act_lyt.addWidget(self.live_start_btn)
        act_lyt.addWidget(self.live_stop_btn)
        layout.addWidget(action_row)

        # Recording Status
        status_container = QWidget()
        status_container.setStyleSheet("QWidget{background-color:#2d2d2d;border-radius:8px;border:1px solid #3d3d3d;padding:12px;}")
        st_lyt = QVBoxLayout(status_container)
        st_lyt.setContentsMargins(8, 8, 8, 8)
        st_lyt.setSpacing(4)

        self.live_status_lbl = QLabel("Idle")
        self.live_status_lbl.setStyleSheet("font-size:13px;font-weight:bold;color:#b0b0b0;")
        st_lyt.addWidget(self.live_status_lbl)

        self.live_folder_lbl = QLabel("")
        self.live_folder_lbl.setStyleSheet("font-size:11px;color:#7986cb;padding:2px;")
        self.live_folder_lbl.setWordWrap(True)
        st_lyt.addWidget(self.live_folder_lbl)

        self.live_progress_bar = QProgressBar()
        self.live_progress_bar.setRange(0, 0)
        self.live_progress_bar.setMinimumHeight(14)
        self.live_progress_bar.setVisible(False)
        st_lyt.addWidget(self.live_progress_bar)

        det_row = QWidget()
        det_lyt = QHBoxLayout(det_row)
        det_lyt.setContentsMargins(0, 0, 0, 0)
        det_lyt.setSpacing(15)

        self.live_size_lbl = QLabel("Downloaded: --")
        self.live_speed_lbl = QLabel("Speed: --")
        self.live_frags_lbl = QLabel("Frags: --")
        self.live_time_lbl = QLabel("Recorded: --:--")
        for lbl in (self.live_size_lbl, self.live_speed_lbl, self.live_frags_lbl, self.live_time_lbl):
            lbl.setStyleSheet("color:#b0b0b0;font-size:11px;")
            det_lyt.addWidget(lbl)
        st_lyt.addWidget(det_row)

        layout.addWidget(status_container)
        layout.addStretch()

    def paste_live_url(self):
        text = QApplication.clipboard().text().strip()
        if text:
            self.live_url_input.setText(text)

    def _fetch_live_info(self, url: str, info: dict = None):
        """Fetch and display stream metadata in the Live tab."""
        if not url:
            return

        def _apply(info: dict):
            self.live_fetch_btn.setText("Fetch Stream Info")
            self.live_fetch_btn.setEnabled(True)
            if not info:
                return

            title   = info.get("title") or "Unknown Title"
            channel = info.get("uploader") or info.get("channel") or "—"
            viewers = info.get("concurrent_view_count") or info.get("view_count") or 0
            status  = info.get("live_status") or ("Live" if info.get("is_live") else "—")
            thumbnail = info.get("thumbnail") or ""

            self.live_info_title.setText(title)
            self.live_info_channel.setText(f"👤 {channel}")
            self.live_info_status.setText(f"🔴 {status.replace('_', ' ').title()}")
            if viewers:
                v = f"{viewers/1000:.1f}K" if viewers >= 1000 else str(viewers)
                self.live_info_viewers.setText(f"👁 {v} viewers")
            else:
                self.live_info_viewers.setText("—")

                # ── Zaman aralığını duration'dan otomatik doldur ──────
            dur = info.get("duration")
            is_live = info.get("is_live") or info.get("live_status") == "is_live"
            if dur and not is_live:
                # DVR/bitmş yayın — baştan sona otomatik doldur
                h, r = divmod(int(dur), 3600)
                m, s = divmod(r, 60)
                self.live_start_time.setText("00:00:00")
                self.live_end_time.setText(f"{h:02d}:{m:02d}:{s:02d}")
                self.live_start_time.setEnabled(True)
                self.live_end_time.setEnabled(True)
            else:
                # Gerçek canlı yayın — alanları temizle ve devre dışı bırak
                self.live_start_time.clear()
                self.live_end_time.clear()
                self.live_start_time.setEnabled(False)
                self.live_end_time.setEnabled(False)
                self.live_start_time.hide()
                self.live_end_time.hide()
            # ──────────────────────────────────────────────────────

            # Download and display thumbnail
            if thumbnail:
                try:
                    thumb_thread = ThumbnailThread(thumbnail)
                    thumb_thread.finished.connect(self._on_live_thumbnail_ready)
                    self._live_thumb_thread = thumb_thread
                    thumb_thread.start()
                except Exception:
                    pass

            self.live_info_group.show()

        if info:
            _apply(info)
            return

        self.live_fetch_btn.setText("Fetching...")
        self.live_fetch_btn.setEnabled(False)

        thread = InfoFetchThread(url)
        thread.info_ready.connect(_apply)
        thread.error.connect(lambda e: (
            self.live_fetch_btn.setText("Fetch Stream Info"),
            self.live_fetch_btn.setEnabled(True),
        ))
        self._live_info_thread = thread
        thread.start()

    def _on_live_thumbnail_ready(self, data: bytes):
        """Display downloaded thumbnail in live tab."""
        if data:
            px = QPixmap()
            px.loadFromData(data)
            self.live_thumbnail.setPixmap(px.scaledToWidth(280))

    def download_live_thumbnail(self):
        if not hasattr(self, 'live_thumbnail') or not self.live_thumbnail.pixmap():
            QMessageBox.warning(self, "Warning", "No thumbnail loaded yet. Fetch stream info first.")
            return
        
        raw_title = self.live_info_title.text().strip()
        if raw_title:
            safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw_title).strip(". ")[:100]
        else:
            safe_title = "live_thumbnail"

        default_path = os.path.join(self.get_download_path(), f"{safe_title}.jpg")

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Thumbnail", default_path,
            "JPEG (*.jpg);;PNG Images (*.png);;All Files (*)"
        )
        if filepath:
            if not filepath.lower().endswith(('.png', '.jpg')):
                filepath += '.jpg'
            if self.live_thumbnail.pixmap().save(filepath):
                QMessageBox.information(self, "Success", f"Thumbnail saved:\n{filepath}")
            else:
                QMessageBox.warning(self, "Error", "Could not save thumbnail.")


    def start_live_download(self):
        url = self.live_url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Warning", "Please enter a live stream URL.")
            return

        base_path = self.get_download_path()
        output_fmt = self.live_format_combo.currentText()

        live_dir = os.path.join(base_path, "LiveStreams")
        os.makedirs(live_dir, exist_ok=True)

        # Use best format for reliable live stream recording
        fmt = "bestvideo+bestaudio/best"

        safe_outtmpl = os.path.join(live_dir, "%(id)s.%(ext)s")
        ydl_args = [
            "--format",               fmt,
            "--output",               safe_outtmpl,
            "--merge-output-format",  output_fmt,
            "--buffer-size",          "16K",
            "--no-mtime",
            "--progress",
            "--newline",
            "--live-from-start",
            "--print", "after_move:%(title)s\t%(id)s\t%(filepath)s",
        ]

        # ── Controls ──────────────────────
        start_t = self.live_start_time.text().strip()
        end_t   = self.live_end_time.text().strip()
        if start_t and end_t:
            ydl_args += ["--download-sections", f"*{start_t}-{end_t}"]
        elif start_t:
            ydl_args += ["--download-sections", f"*{start_t}-inf"]
        # ─────────────────────────────────────────────────────

        self.live_start_btn.setEnabled(False)
        self.live_stop_btn.setEnabled(True)
        self.live_status_lbl.setText("Recording fragments...")
        self.live_status_lbl.setStyleSheet("font-size:15px; font-weight:bold; color:#f44336;")
        self.live_progress_bar.setVisible(True)
        self.live_folder_lbl.setText(f"Saving to: {live_dir}")
        self._live_dir = live_dir
        self._live_record_start = datetime.now()
        self._live_speed_samples.clear()
        self._live_streams = {}

        self.active_live_dl = LiveStreamThread(url, ydl_args, live_dir, output_fmt)
        self.active_live_dl.progress_signal.connect(self.update_live_progress)
        self.active_live_dl.status_signal.connect(self.on_live_status)
        self.active_live_dl.error_signal.connect(self.on_live_error)
        self.active_live_dl.finished_signal.connect(self.on_live_done)
        self.active_live_dl.start()

    def on_live_status(self, status: str):
        """Called when yt-dlp finishes fragment downloading and starts merging."""
        if status == "merging":
            self.live_status_lbl.setText("🔀  Merging fragments with FFmpeg...")
            self.live_status_lbl.setStyleSheet(
                "font-size:15px; font-weight:bold; color:#ffb300;"
            )
            self.live_frags_lbl.setText("Fragments: all downloaded — merging...")
            self.live_progress_bar.setRange(0, 0)   # indeterminate while merging

    def update_live_progress(self, d: dict):
        """Works with both DownloadThread (yt-dlp API) and LiveStreamThread (subprocess) dicts."""
        stream_id  = d.get("stream_id", 1)
        downloaded = d.get("downloaded",  0) or d.get("downloaded_bytes", 0) or 0
        raw_speed  = d.get("speed",       0) or 0
        frag_idx   = d.get("frag_idx")   or d.get("fragment_index")  or 0
        frag_count = d.get("frag_count") or d.get("fragment_count")  or 0

        if not hasattr(self, "_live_streams"):
            self._live_streams = {}
        stream = self._live_streams.setdefault(stream_id, {
            "downloaded": 0, "speed": 0, "frag_idx": 0, "frag_count": 0
        })
        stream["downloaded"] = downloaded
        stream["speed"]      = raw_speed
        stream["frag_idx"]   = frag_idx
        stream["frag_count"] = frag_count

        # Combined totals
        total_dl    = sum(s["downloaded"] for s in self._live_streams.values())
        total_speed = sum(s["speed"]      for s in self._live_streams.values())

        if total_dl > 1024 ** 3:
            self.live_size_lbl.setText(f"Downloaded: {total_dl/1024**3:.2f} GB")
        else:
            self.live_size_lbl.setText(f"Downloaded: {total_dl/1024**2:.1f} MB")

        if total_speed > 0:
            self._live_speed_samples.append(total_speed)
        speed = (sum(self._live_speed_samples) / len(self._live_speed_samples)
                 if self._live_speed_samples else 0)
        if speed > 1024 ** 2:
            self.live_speed_lbl.setText(f"Speed: {speed/1024**2:.1f} MB/s")
        elif speed > 0:
            self.live_speed_lbl.setText(f"Speed: {speed/1024:.1f} KB/s")
        else:
            self.live_speed_lbl.setText("Speed: --")

        if len(self._live_streams) > 1:
            parts = []
            for i, (sid, s) in enumerate(sorted(self._live_streams.items()), 1):
                lbl = "V" if i == 1 else "A"
                fc  = s["frag_count"]
                fi  = s["frag_idx"]
                parts.append(f"{lbl}: {fi}/{fc}" if fc else f"{lbl}: {fi}")
            self.live_frags_lbl.setText("Frags  " + "   ".join(parts))
        else:
            s  = list(self._live_streams.values())[0]
            fi, fc = s["frag_idx"], s["frag_count"]
            self.live_frags_lbl.setText(f"Fragments: {fi}/{fc}" if fc else f"Fragments: {fi}")

        # ── Recorded content duration estimation ─────────────────────────
        # YouTube live HLS segments are typically ~2 seconds each.
        # So: content_recorded ≈ video_frag_idx * YT_SEG_SECS
        # Wall-clock elapsed is useless in DVR mode (downloading fast from history).
        try:
            YT_SEG_SECS = 2.0   # YouTube's standard HLS segment duration
            video_stream = self._live_streams.get(1) or list(self._live_streams.values())[0]
            fi = video_stream["frag_idx"]
            fc = video_stream["frag_count"]

            if fi and fi > 0:
                done_secs = fi * YT_SEG_SECS

                def _fmt(secs):
                    h, r = divmod(int(secs), 3600)
                    m, s = divmod(r, 60)
                    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

                if fc and fc > 0:
                    # DVR: show "downloaded_so_far / total_content"
                    total_secs = fc * YT_SEG_SECS
                    self.live_time_lbl.setText(f"~{_fmt(done_secs)} / {_fmt(total_secs)}")
                else:
                    # Live edge: just show approximate recorded duration
                    self.live_time_lbl.setText(f"~{_fmt(done_secs)} recorded")
            else:
                # No frag info yet — fall back to wall-clock elapsed
                if self._live_record_start:
                    elapsed = (datetime.now() - self._live_record_start).total_seconds()
                    h, r = divmod(int(elapsed), 3600)
                    m, s = divmod(r, 60)
                    self.live_time_lbl.setText(
                        f"Elapsed: {h}:{m:02d}:{s:02d}" if h else f"Elapsed: {m:02d}:{s:02d}"
                    )
        except Exception:
            pass

        best = max(self._live_streams.values(), key=lambda s: s["frag_count"] or 0)
        fi, fc = best["frag_idx"], best["frag_count"]
        if fc:
            try:
                pct = int(fi / fc * 100)
                self.live_progress_bar.setRange(0, 100)
                self.live_progress_bar.setValue(pct)
            except (ZeroDivisionError, TypeError):
                self.live_progress_bar.setRange(0, 0)
        else:
            self.live_progress_bar.setRange(0, 0)

    def on_live_error(self, error: str):
        self.live_status_lbl.setText("❌  Error")
        self.live_status_lbl.setStyleSheet("font-size:15px; font-weight:bold; color:#f44336;")
        QMessageBox.critical(self, "Live Stream Error", error)
        self.reset_live_state()

    def on_live_done(self, filepath: str):
        self.live_status_lbl.setText("✅  Recording saved.")
        self.live_status_lbl.setStyleSheet("font-size:15px; font-weight:bold; color:#4caf50;")
        self.live_progress_bar.setRange(0, 100)
        self.live_progress_bar.setValue(100)
        if filepath:
            # Clean up .ytdl and .part files left beside the merged output
            self._cleanup_temp_files(os.path.dirname(filepath))
            self.add_to_history(
                os.path.basename(filepath),
                self.live_url_input.text(),
                "Finished",
                filepath,
            )
            self._show_done_dialog(filepath, title="Recording Complete")
        self.reset_live_state()

    def stop_live_download(self):
        if not self.active_live_dl:
            return

        self.live_stop_btn.setEnabled(False)
        self.live_status_lbl.setText("⏳  Stopping...")
        self.live_status_lbl.setStyleSheet("font-size:15px; font-weight:bold; color:#ffb300;")

        thread   = self.active_live_dl
        live_dir = getattr(self, "_live_dir", "")

        def _on_finished():
            # yt-dlp subprocess has exited — check what was saved
            if live_dir and os.path.isdir(live_dir):
                final_output = self._merge_live_fragments(live_dir)
                if final_output:
                    self.on_live_done(final_output)
            else:
                self.live_status_lbl.setText("⏹  Stopped.")
                self.live_status_lbl.setStyleSheet(
                    "font-size:15px; font-weight:bold; color:#ffb300;"
                )
            self.reset_live_state()

        thread.finished.connect(_on_finished)
        # CTRL_C_EVENT / SIGTERM → yt-dlp saves current fragment and exits
        thread.cancel()

    def _merge_live_fragments(self, live_dir: str) -> str:
        """
        Handle two cases after stop:

        Case A — yt-dlp downloaded complete stream files (no .part suffix):
          ePzWqox8T-A.f299.mkv  (video)
          ePzWqox8T-A.f140.mkv  (audio)
          → FFmpeg -i video -i audio -c copy output.mkv

        Case B — yt-dlp left fragment files mid-download:
          Title.f299.mkv.part-Frag0 .. part-Frag500
          → concat all fragments per stream, then mux
        
        Returns the final output filepath, or empty string on error.
        """
        if not os.path.isdir(live_dir):
            self.live_status_lbl.setText("\u29b9  Stopped. No folder found.")
            return

        all_files = [f for f in os.listdir(live_dir)
                     if os.path.isfile(os.path.join(live_dir, f))]

        output_fmt = getattr(self, "live_format_combo", None)
        output_fmt = output_fmt.currentText() if output_fmt else "mkv"

        def _set_status(text, color="#ffb300"):
            self.live_status_lbl.setText(text)
            self.live_status_lbl.setStyleSheet(
                f"font-size:15px; font-weight:bold; color:{color};"
            )

        def _run_ffmpeg(cmd, source_files, output):
            try:
                result = subprocess.run(
                    cmd, capture_output=True,
                    encoding="utf-8", errors="replace",
                    timeout=600,
                )
                if result.returncode == 0 and os.path.exists(output):
                    for f in source_files:
                        try: os.remove(f)
                        except Exception: pass
                    self._cleanup_temp_files(live_dir)
                    size_mb = os.path.getsize(output) / 1024 ** 2
                    _set_status(f"\u2705  Saved \u2192 {size_mb:.1f} MB", "#4caf50")
                    self._show_done_dialog(output, title="Recording Stopped \u2014 Recovered")
                    return output  # ← Return the output path
                else:
                    err = ((result.stderr or "") + (result.stdout or ""))[-300:]
                    _set_status(f"\u274c  FFmpeg error: {err[:120]}", "#f44336")
                    return ""
            except FileNotFoundError:
                _set_status("\u274c  FFmpeg not found. Files kept.", "#f44336")
                return ""
            except subprocess.TimeoutExpired:
                _set_status("\u274c  FFmpeg timed out (>10 min).", "#f44336")
                return ""
            except Exception as e:
                _set_status(f"\u274c  Error: {e}", "#f44336")
                return ""

        # ── Case A: complete stream files (ePzWqox8T-A.f299.mkv style) ──
        stream_files = [
            os.path.join(live_dir, f) for f in all_files
            if re.search(r"\.f\d+\.[a-z0-9]{2,4}$", f, re.IGNORECASE)
            and not re.search(r"\.(part|ytdl)", f, re.IGNORECASE)
        ]
        if stream_files:
            stream_files.sort(key=os.path.getsize, reverse=True)
            video_file = stream_files[0]
            audio_file = stream_files[1] if len(stream_files) > 1 else None

            raw_base = re.sub(r"\.f\d+\.[a-z0-9]{2,4}$", "",
                              os.path.basename(video_file), flags=re.IGNORECASE)
            output = os.path.join(live_dir, f"{raw_base}_merged.{output_fmt}")

            if audio_file:
                _set_status("\U0001f500  Muxing video + audio with FFmpeg...")
                QApplication.processEvents()
                result = _run_ffmpeg(
                    ["ffmpeg", "-y", "-fflags", "+igndts", "-i", video_file, "-i", audio_file,
                     "-c", "copy", "-shortest", "-movflags", "+faststart", output],
                    stream_files, output
                )
                if result:
                    return result
            else:
                _set_status("\U0001f500  Remuxing with FFmpeg...")
                QApplication.processEvents()
                result = _run_ffmpeg(
                    ["ffmpeg", "-y", "-i", video_file, "-c", "copy", output],
                    stream_files, output
                )
                if result:
                    return result
            return ""

        # ── Case B: accumulating part files (id.fNNN.ext.part-FragN) ────
        # yt-dlp writes ALL fragment content into ONE accumulating file per stream.
        # "part-Frag68" means 68 fragments have been written to that single file.
        # We just need to DIRECTLY MUX the two partial files — no concat needed.
        part_files = []
        for fname in all_files:
            # Match both ePzWqox8T-A.f299.mkv.part-Frag68  AND  title.f299.mkv.part
            if re.search(r"\.f\d+\.[a-z0-9]{2,4}\.part(-Frag\d+)?$", fname, re.IGNORECASE):
                part_files.append(os.path.join(live_dir, fname))

        if not part_files:
            _set_status("⏹  Stopped. No recoverable files found.")
            return

        # Largest = video stream, second = audio stream
        part_files.sort(key=os.path.getsize, reverse=True)
        video_part = part_files[0]
        audio_part = part_files[1] if len(part_files) > 1 else None

        # Build clean output name: strip .part-FragN and .fNNN.ext
        raw_base = re.sub(r"\.part(-Frag\d+)?$", "",
                          os.path.basename(video_part), flags=re.IGNORECASE)
        raw_base = re.sub(r"\.f\d+\.[a-z0-9]{2,4}$", "", raw_base, flags=re.IGNORECASE)
        output = os.path.join(live_dir, f"{raw_base}_recovered.{output_fmt}")

        if audio_part:
            _set_status(f"🔀  Muxing {len(part_files)} stream files with FFmpeg...")
            QApplication.processEvents()
            cmd = ["ffmpeg", "-y", "-fflags", "+igndts",
                   "-i", video_part, "-i", audio_part,
                   "-c", "copy", "-shortest", "-movflags", "+faststart", output]
        else:
            _set_status("🔀  Remuxing partial recording with FFmpeg...")
            QApplication.processEvents()
            cmd = ["ffmpeg", "-y", "-fflags", "+igndts", "-i", video_part, "-c", "copy", "-movflags", "+faststart", output]

        return _run_ffmpeg(cmd, part_files, output)
    def _cleanup_temp_files(self, directory: str):
        """Remove .ytdl, .part, .part-FragN, and leftover concat list files."""
        if not os.path.isdir(directory):
            return
        for f in os.listdir(directory):
            if (re.search(r"\.(ytdl|part)(-Frag\d+)?$", f, re.IGNORECASE)
                    or f in ("_ytl_v.txt", "_ytl_a.txt")):
                try:
                    os.remove(os.path.join(directory, f))
                except Exception:
                    pass

    def reset_live_state(self):
        self.active_live_dl = None
        self.live_start_btn.setEnabled(True)
        self.live_stop_btn.setEnabled(False)
        self.live_progress_bar.setVisible(False)

    # ══════════════════════════════════════════════════════
    #  4. VIDEO CODEC TAB
    # ══════════════════════════════════════════════════════

    def setup_codec_tab(self):
        layout = QVBoxLayout(self.codec_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header (simplified)
        header = QWidget()
        header.setStyleSheet("QWidget{background-color:#363636;border-radius:8px;padding:8px;}")
        h_lyt = QHBoxLayout(header)
        h_lyt.setContentsMargins(10, 0, 10, 0)
        h_lyt.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(QPixmap("icon.ico").scaled(32, 32,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        h_lyt.addWidget(ic)
        h_lyt.addWidget(_make_label("Video Codec Editor", "color:#fff;font-size:16px;font-weight:bold;"))
        h_lyt.addWidget(_make_label("Convert video files to different codecs.",
                                 "color:#b0b0b0;font-size:12px;"), 1)
        layout.addWidget(header)

        # File selection (simplified)
        file_container = QWidget()
        file_container.setStyleSheet("QWidget{background-color:#363636;border-radius:8px;padding:8px;}")
        fc_lyt = QHBoxLayout(file_container)
        fc_lyt.setContentsMargins(10, 5, 10, 5)
        fc_lyt.setSpacing(8)
        self.codec_file_input = QLineEdit()
        self.codec_file_input.setPlaceholderText("Select a video file to convert...")
        self.codec_file_input.setMinimumHeight(36)
        self.codec_file_input.setStyleSheet(_INPUT)
        self.codec_browse_button = QPushButton("Browse")
        self.codec_browse_button.setMinimumHeight(36)
        self.codec_browse_button.setFixedWidth(100)
        self.codec_browse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.codec_browse_button.setStyleSheet(_BTN_BLUE)
        self.codec_browse_button.clicked.connect(self.browse_codec_file)
        fc_lyt.addWidget(self.codec_file_input)
        fc_lyt.addWidget(self.codec_browse_button)
        layout.addWidget(file_container)

        # Codec options (using QFormLayout for cleaner structure)
        codec_container = QGroupBox("🎞  Codec Settings")
        form_layout = QFormLayout(codec_container)
        form_layout.setSpacing(12)
        form_layout.setContentsMargins(10, 10, 10, 10)

        self.video_codec_combo = QComboBox()
        self.video_codec_combo.addItems(["H.264", "H.265", "VP9", "AV1"])
        self.video_codec_combo.setStyleSheet(_COMBO)
        self.video_codec_combo.currentTextChanged.connect(self._on_codec_changed)
        form_layout.addRow("🎥  Video Codec:", self.video_codec_combo)

        self.audio_codec_combo = QComboBox()
        self.audio_codec_combo.addItems(["AAC", "MP3", "Opus", "FLAC", "Copy"])
        self.audio_codec_combo.setStyleSheet(_COMBO)
        form_layout.addRow("🔊  Audio Codec:", self.audio_codec_combo)

        self.acceleration_mode_combo = QComboBox()
        modes = getattr(self, '_cached_accel_modes', self.get_available_acceleration_modes())
        if not hasattr(self, '_cached_accel_modes'):
            self._cached_accel_modes = modes
        self.acceleration_mode_combo.addItems(modes)
        self.acceleration_mode_combo.setStyleSheet(_COMBO)
        form_layout.addRow("⚡  Acceleration:", self.acceleration_mode_combo)

        self.codec_preset_combo = QComboBox()
        self.codec_preset_combo.addItems(["veryfast", "fast", "medium (balanced)", "slow", "veryslow"])
        self.codec_preset_combo.setCurrentIndex(2)  # Default to balanced
        self.codec_preset_combo.setStyleSheet(_COMBO)
        form_layout.addRow("🎚  Preset:", self.codec_preset_combo)

        layout.addWidget(codec_container)

        # Compatibility hint
        self.compat_hint = QLabel("")
        self.compat_hint.setStyleSheet("color:#ffb300; font-size:12px; padding:8px; background-color:#2a2a2a; border-radius:4px;")
        self.compat_hint.setWordWrap(True)
        layout.addWidget(self.compat_hint)

        # Convert button
        self.convert_button = QPushButton("🔄 Convert")
        self.convert_button.setMinimumHeight(40)
        self.convert_button.setStyleSheet(_BTN_BLUE)
        self.convert_button.clicked.connect(self.start_conversion)
        layout.addWidget(self.convert_button)

        # Progress (simplified)
        progress_container = QGroupBox("📊  Conversion Progress")
        prog_lyt = QVBoxLayout(progress_container)
        prog_lyt.setSpacing(10)

        self.codec_progress = QProgressBar()
        self.codec_progress.setMinimumHeight(25)
        prog_lyt.addWidget(self.codec_progress)

        det_row = QWidget()
        det_lyt = QHBoxLayout(det_row)
        det_lyt.setContentsMargins(0, 0, 0, 0)
        det_lyt.setSpacing(15)
        self.conversion_speed   = QLabel("⚡ Speed: -- fps")
        self.conversion_time    = QLabel("⏱ Time: --:--:--")
        self.conversion_eta     = QLabel("🕒 ETA: --:--:--")
        self.conversion_percent = QLabel("📊 Progress: 0%")
        for lbl in (self.conversion_speed, self.conversion_time,
                    self.conversion_eta, self.conversion_percent):
            lbl.setStyleSheet("color:#b0b0b0; font-size:12px;")
            det_lyt.addWidget(lbl, 1)
        prog_lyt.addWidget(det_row)
        layout.addWidget(progress_container)
        layout.addStretch()


    def _on_codec_changed(self):
        """Update compatibility hint when codec selection changes."""
        vc = self.video_codec_combo.currentText()
        ac = self.audio_codec_combo.currentText()
        hint = self._get_compat_hint(vc, ac)
        self.compat_hint.setText(hint)

    def _get_compat_hint(self, video_codec: str, audio_codec: str) -> str:
        hints = []
        if video_codec == "VP9":
            hints.append("VP9 requires .webm or .mkv output (not .mp4).")
        if video_codec == "AV1":
            hints.append("AV1 is best stored in .mkv (very slow on CPU — use GPU if available).")
        if audio_codec == "FLAC":
            hints.append("FLAC audio is not compatible with .mp4 — output will use .mkv.")
        if audio_codec == "Opus":
            hints.append("Opus audio is not standard in .mp4 — output will use .mkv.")
        return "  ⚠  " + "  |  ".join(hints) if hints else ""

    def _get_best_container(self, video_codec: str, audio_codec: str) -> str:
        if video_codec in ("libvpx-vp9", "libvpx"):
            return ".webm"
        if audio_codec in ("flac", "libopus") or video_codec == "libaom-av1":
            return ".mkv"
        return ".mp4"

    def browse_codec_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a Video File",
            self.get_download_path(),
            "Video Files (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.ts);;All (*.*)",
        )
        if path:
            self.codec_file_input.setText(path)
            self._on_codec_changed()

    def detect_gpu(self) -> str:
        if shutil.which("nvidia-smi"):
            return "NVIDIA"
        if os.name == "nt":
            try:
                out = subprocess.check_output(
                    ["wmic", "path", "win32_VideoController", "get", "Name"],
                    encoding='utf-8', errors='replace', stderr=subprocess.DEVNULL,
                )
                up = out.upper()
                if "AMD" in up:
                    return "AMD_APU" if "APU" in up else "AMD"
            except Exception:
                pass
        # Linux: try vainfo for Intel QSV / AMD VAAPI
        if shutil.which("vainfo"):
            return "VAAPI"
        return "CPU"

    def get_available_acceleration_modes(self) -> list:
        modes = ["CPU"]
        if shutil.which("nvidia-smi"):
            modes.append("NVIDIA (NVENC)")
        if os.name == "nt":
            try:
                out = subprocess.check_output(
                    ["wmic", "path", "win32_VideoController", "get", "Name"],
                    encoding='utf-8', errors='replace', stderr=subprocess.DEVNULL,
                ).upper()
                if "AMD" in out:
                    modes.append("AMD APU (AMF)" if "APU" in out else "AMD (AMF)")
            except Exception:
                pass
        if shutil.which("vainfo"):
            modes.append("Intel/AMD (VAAPI)")
        return modes

    def start_conversion(self):
        input_file = self.codec_file_input.text().strip()
        if not input_file or not os.path.exists(input_file):
            QMessageBox.warning(self, "Error", "Please select a valid video file.")
            return

        # Check FFmpeg
        if not shutil.which("ffmpeg"):
            QMessageBox.warning(self, "Error",
                "FFmpeg is not installed. Please install it from the Settings tab.")
            return

        # Verify input file is readable / not zero-length
        if os.path.getsize(input_file) == 0:
            QMessageBox.warning(self, "Error", "Selected file is empty.")
            return

        # Codec maps
        video_codec_map = {
            "H.264":  "libx264",
            "H.265":  "libx265",
            "VP9":    "libvpx-vp9",
            "AV1":    "libaom-av1",
        }
        audio_codec_map = {
            "AAC":   "aac",
            "MP3":   "libmp3lame",
            "Opus":  "libopus",
            "FLAC":  "flac",
            "Copy":  "copy",
        }
        
        # Optimized preset mapping (faster presets with good quality)
        preset_map_cpu = {
            "veryfast":         "superfast",
            "fast":             "fast",
            "medium (balanced)":"medium",
            "slow":             "slow",
            "veryslow":         "veryslow",
        }
        preset_map_hwenc = {
            "veryfast":         "p1",   # Fastest
            "fast":             "p2",
            "medium (balanced)":"p3",   # Balanced
            "slow":             "p4",
            "veryslow":         "p5",   # Slowest but best quality
        }
        
        acc_mode    = self.acceleration_mode_combo.currentText()
        cur_vc      = self.video_codec_combo.currentText()
        cur_ac      = self.audio_codec_combo.currentText()
        preset_raw  = self.codec_preset_combo.currentText()

        # CPU codec (also used as fallback)
        cpu_video_codec = video_codec_map.get(cur_vc, "libx264")
        audio_codec     = audio_codec_map.get(cur_ac, "aac")

        # Hardware encoder selection with optimized settings
        extra_params = []
        if "NVIDIA" in acc_mode:
            hw_map  = {"H.264": "h264_nvenc", "H.265": "hevc_nvenc"}
            video_codec = hw_map.get(cur_vc, cpu_video_codec)
            # NVIDIA NVENC optimizations
            extra_params = ["-rc:v", "vbr", "-cq:v", "23"]  # VBR with quality focus
            if cur_vc == "H.265":
                extra_params += ["-preset:v", preset_map_hwenc.get(preset_raw, "p3")]
            else:
                extra_params += ["-preset:v", preset_map_hwenc.get(preset_raw, "p3")]
        elif "AMD" in acc_mode:
            hw_map  = {"H.264": "h264_amf", "H.265": "hevc_amf"}
            video_codec = hw_map.get(cur_vc, cpu_video_codec)
            # AMD AMF optimizations
            extra_params = ["-quality", "balanced"]  # or "speed" for faster
        elif "VAAPI" in acc_mode:
            hw_map  = {"H.264": "h264_vaapi", "H.265": "hevc_vaapi"}
            video_codec = hw_map.get(cur_vc, cpu_video_codec)
            # Intel QSV / AMD VAAPI
            extra_params = ["-low_power", "0"]
        else:
            video_codec = cpu_video_codec
            cpu_video_codec = ""   # no fallback needed for CPU
            # CPU codec optimizations
            if cur_vc in ("H.264", "H.265"):
                preset_val = preset_map_cpu.get(preset_raw, "medium")
                extra_params = ["-preset", preset_val, "-crf", "23"]

        # Determine best output container
        best_ext        = self._get_best_container(cpu_video_codec, audio_codec)
        in_base, in_ext = os.path.splitext(input_file)
        in_dir          = os.path.dirname(input_file)
        acc_tag         = "_gpu" if acc_mode != "CPU" else ""
        suggested_name  = (f"{os.path.basename(in_base)}"
                           f"_{cur_vc}_{cur_ac}{acc_tag}{best_ext}")
        suggested_out   = os.path.join(in_dir, suggested_name)

        filter_str = "Video Files (*.mp4 *.mkv *.webm *.avi);;All Files (*.*)"
        output_file, _ = QFileDialog.getSaveFileName(
            self, "Save Converted File", suggested_out, filter_str
        )
        if not output_file:
            return

        # Warn if user chose a container that may be incompatible
        out_ext = os.path.splitext(output_file)[1].lower()
        if cpu_video_codec == "libvpx-vp9" and out_ext == ".mp4":
            reply = QMessageBox.warning(
                self, "Container Warning",
                "VP9 in .mp4 is not widely supported.\n"
                "Consider saving as .webm or .mkv instead.\n\n"
                "Continue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        if audio_codec == "flac" and out_ext == ".mp4":
            reply = QMessageBox.warning(
                self, "Container Warning",
                "FLAC audio is incompatible with .mp4.\n"
                "Please save as .mkv.\n\n"
                "Continue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.convert_button.setEnabled(False)
        self.convert_button.setText("Converting...")
        self.codec_progress.setValue(0)

        self.conversion_thread = ConversionThread(
            input_file, output_file,
            video_codec, audio_codec,
            extra_params,
            cpu_fallback_video=cpu_video_codec,
        )
        self.conversion_thread.progress_signal.connect(self.update_conversion_progress)
        self.conversion_thread.finished_signal.connect(self.conversion_finished)
        self.conversion_thread.error_signal.connect(self.conversion_error)
        self.conversion_thread.start()

    def update_conversion_progress(self, d: dict):
        pct = d.get("percent", 0)
        self.codec_progress.setValue(int(pct))
        self.conversion_speed.setText(f"⚡ Speed: {d.get('speed', '?')} fps")
        self.conversion_time.setText(f"⏱ Time: {d.get('time', '--:--:--')}")
        eta = d.get("eta", "--:--:--")
        # eta might say "Retrying with CPU..."
        self.conversion_eta.setText(f"🕒 Remaining: {eta}")
        self.conversion_percent.setText(f"📊 Progress: {pct:.1f}%")

    def conversion_finished(self):
        QMessageBox.information(self, "Success", "Conversion complete!")
        self.convert_button.setEnabled(True)
        self.convert_button.setText("🔄 Convert")
        self.codec_progress.setValue(100)
        self._reset_conversion_labels()

    def conversion_error(self, error: str):
        QMessageBox.critical(self, "Conversion Error", error)
        self.convert_button.setEnabled(True)
        self.convert_button.setText("🔄 Convert")
        self.codec_progress.setValue(0)
        self._reset_conversion_labels()

    def _reset_conversion_labels(self):
        self.conversion_speed.setText("⚡ Speed: -- fps")
        self.conversion_time.setText("⏱ Time: --:--:--")
        self.conversion_eta.setText("🕒 Remaining: --:--:--")
        self.conversion_percent.setText("📊 Progress: 0%")

    # ══════════════════════════════════════════════════════
    #  5. HISTORY TAB
    # ══════════════════════════════════════════════════════

    def setup_history_tab(self):
        layout = QVBoxLayout(self.history_tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels(
            ["Date", "File Name", "URL", "Status", "FilePath"]
        )
        hdr = self.history_table.horizontalHeader()
        # Date — fixed
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        # File Name — stretch to fill available space
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        # URL — interactive (user can resize)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.history_table.setColumnWidth(2, 220)
        # Status — fixed
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        # Hidden filepath
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setColumnHidden(4, True)
        self.history_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setWordWrap(False)
        layout.addWidget(self.history_table)

        btn_widget = QWidget()
        btn_lyt    = QHBoxLayout(btn_widget)
        btn_lyt.setContentsMargins(0, 0, 0, 0)

        self.open_file_button      = QPushButton("📂  Open File")
        self.show_in_folder_button = QPushButton("📁  Show in Folder")
        self.clear_history_button  = QPushButton("🗑  Clear History")
        for b in (self.open_file_button, self.show_in_folder_button):
            b.setStyleSheet(_BTN_BLUE)
            b.setMinimumHeight(36)
        self.clear_history_button.setStyleSheet(_BTN_RED)
        self.clear_history_button.setMinimumHeight(36)

        self.open_file_button.clicked.connect(self.open_selected_file)
        self.show_in_folder_button.clicked.connect(self.show_in_folder)
        self.clear_history_button.clicked.connect(self.clear_history)

        self.open_file_button.setEnabled(False)
        self.show_in_folder_button.setEnabled(False)

        btn_lyt.addWidget(self.open_file_button)
        btn_lyt.addWidget(self.show_in_folder_button)
        btn_lyt.addStretch()
        btn_lyt.addWidget(self.clear_history_button)
        layout.addWidget(btn_widget)

        self.history_table.itemSelectionChanged.connect(self.update_history_buttons)

        self.init_database()
        self.load_history()

    def init_database(self):
        try:
            db_path    = os.path.join(self.get_app_data_dir(), "download_history.db")
            self.conn  = sqlite3.connect(db_path, check_same_thread=False)
            cursor     = self.conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS downloads (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    date     TEXT,
                    filename TEXT,
                    url      TEXT,
                    status   TEXT,
                    filepath TEXT
                )
            """)
            self.conn.commit()
        except Exception as e:
            QMessageBox.warning(self, "Database Error",
                f"Could not initialize database:\n{e}")

    def add_to_history(self, filename: str, url: str,
                       status: str, filepath: str):
        try:
            cur  = self.conn.cursor()
            date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                "INSERT INTO downloads (date,filename,url,status,filepath) "
                "VALUES (?,?,?,?,?)",
                (date, filename, url, status, filepath),
            )
            self.conn.commit()
            self.load_history()
        except Exception as e:
            print(f"History add error: {e}")

    def load_history(self):
        try:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT date,filename,url,status,filepath "
                "FROM downloads ORDER BY date DESC"
            )
            rows = cur.fetchall()
            self.history_table.setRowCount(0)
            for row_data in rows:
                row = self.history_table.rowCount()
                self.history_table.insertRow(row)
                for col, data in enumerate(row_data):
                    text = str(data)
                    # Col 1: strip intermediate format tag for display (.f251.webm → .mkv hint)
                    if col == 1:
                        text = re.sub(r"\.[a-z0-9]+\.([a-z0-9]{2,4})$",
                                      r".\1", text, flags=re.IGNORECASE)
                    item = QTableWidgetItem(text)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    # Store the *original* data as user role for filepath lookups
                    item.setData(Qt.ItemDataRole.UserRole, str(data))
                    # Color status
                    if col == 3 and "Not Found" in text:
                        item.setForeground(QColor("#f44336"))
                    self.history_table.setItem(row, col, item)
        except Exception as e:
            print(f"History load error: {e}")

    def clear_history(self):
        reply = QMessageBox.question(
            self, "Clear History",
            "Are you sure you want to delete all download history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.conn.cursor().execute("DELETE FROM downloads")
                self.conn.commit()
                self.load_history()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not clear history:\n{e}")

    def update_history_buttons(self):
        rows = self.history_table.selectionModel().selectedRows()
        if not rows:
            self.open_file_button.setEnabled(False)
            self.show_in_folder_button.setEnabled(False)
            return

        row = rows[0].row()
        fp_item = self.history_table.item(row, 4)
        if not fp_item:
            self.open_file_button.setEnabled(False)
            self.show_in_folder_button.setEnabled(False)
            return

        stored_path = fp_item.data(Qt.ItemDataRole.UserRole) or fp_item.text()
        real_path   = self._resolve_history_path(stored_path)

        exists = bool(real_path and os.path.exists(real_path))
        self.open_file_button.setEnabled(exists)
        self.show_in_folder_button.setEnabled(exists)

        # Update status cell if needed
        st_item = self.history_table.item(row, 3)
        if st_item:
            if exists:
                # If it was "File Not Found" but now exists (path resolved), fix it
                if "Not Found" in st_item.text():
                    st_item.setText("Finished")
                    st_item.setForeground(QColor("#e0e0e0"))
                    # Persist the corrected filepath
                    self._update_history_filepath(stored_path, real_path)
            else:
                st_item.setText("File Not Found")
                st_item.setForeground(QColor("#f44336"))

    def _resolve_history_path(self, stored: str) -> str:
        """
        Given a stored path (possibly stale intermediate file), find the real file.
        Tries: stored → merged variant → same dir same stem different ext.
        """
        if not stored:
            return ""
        if os.path.exists(stored):
            return stored

        directory = os.path.dirname(stored)
        if not os.path.isdir(directory):
            return ""

        # Try common merge output formats
        base = re.sub(r"\.[a-z0-9]+\.[a-z0-9]{2,4}$", "", stored, flags=re.IGNORECASE)
        for ext in ("mkv", "mp4", "webm", "mov", "avi"):
            candidate = f"{base}.{ext}"
            if os.path.exists(candidate):
                return candidate

        # Last resort: find any file in the same directory with the same stem
        stem = re.sub(r"(\.[a-z0-9]+)?\.[a-z0-9]{2,4}$", "",
                      os.path.basename(stored), flags=re.IGNORECASE)
        stem_clean = re.sub(r"\.f\d+$", "", stem)
        try:
            for f in os.listdir(directory):
                f_stem = re.sub(r"(\.[a-z0-9]+)?\.[a-z0-9]{2,4}$", "",
                                f, flags=re.IGNORECASE)
                if f_stem == stem_clean:
                    return os.path.join(directory, f)
        except Exception:
            pass
        return ""

    def _update_history_filepath(self, old_path: str, new_path: str):
        """Update a stale filepath in the DB."""
        try:
            self.conn.cursor().execute(
                "UPDATE downloads SET filepath=?, status='Finished' WHERE filepath=?",
                (new_path, old_path),
            )
            self.conn.commit()
        except Exception as e:
            print(f"History filepath update error: {e}")

    def open_selected_file(self):
        rows = self.history_table.selectionModel().selectedRows()
        if not rows:
            return
        fp_item  = self.history_table.item(rows[0].row(), 4)
        stored   = fp_item.data(Qt.ItemDataRole.UserRole) if fp_item else ""
        filepath = self._resolve_history_path(stored)
        if not filepath:
            QMessageBox.warning(self, "Error", "File not found.")
            return
        try:
            if os.name == "nt":   os.startfile(filepath)
            elif os.name == "darwin": subprocess.run(["open", filepath])
            else: subprocess.run(["xdg-open", filepath])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open file:\n{e}")

    def show_in_folder(self):
        rows = self.history_table.selectionModel().selectedRows()
        if not rows:
            return
        fp_item  = self.history_table.item(rows[0].row(), 4)
        stored   = fp_item.data(Qt.ItemDataRole.UserRole) if fp_item else ""
        filepath = self._resolve_history_path(stored)
        if not filepath:
            QMessageBox.warning(self, "Error", "File not found.")
            return
        try:
            if os.name == "nt":
                subprocess.run(f'explorer /select,"{filepath}"', shell=True)
            elif os.name == "darwin":
                subprocess.run(["open", "-R", filepath])
            else:
                subprocess.run(["xdg-open", os.path.dirname(filepath)])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open folder:\n{e}")

    # ══════════════════════════════════════════════════════
    #  6. SETTINGS TAB
    # ══════════════════════════════════════════════════════

    def setup_settings_tab(self):
        layout = QVBoxLayout(self.settings_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        header = QWidget()
        header.setStyleSheet(
            "QWidget{background-color:#363636;border-radius:8px;padding:5px;}"
        )
        h_lyt = QHBoxLayout(header)
        h_lyt.setContentsMargins(0, 0, 0, 0)
        ic = QLabel()
        ic.setPixmap(
            QPixmap("icon.ico").scaled(
                32, 32,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        h_lyt.addWidget(ic)
        tc = QWidget()
        tl = QVBoxLayout(tc)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(2)
        tl.addWidget(_make_label("App Settings", "color:#fff;font-size:16px;font-weight:bold;"))
        tl.addWidget(_make_label("Configure download folder and quality defaults.",
                                 "color:#b0b0b0;font-size:12px;"))
        h_lyt.addWidget(tc, 1)
        layout.addWidget(header)

        # Download folder
        folder_group = QGroupBox("📥  Download Folder")
        folder_lyt   = QHBoxLayout(folder_group)

        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText("Select a download folder...")
        self.folder_input.setStyleSheet(_INPUT)

        self.folder_browse_button = QPushButton("Browse")
        self.folder_browse_button.setStyleSheet(_BTN_BLUE)
        self.folder_browse_button.clicked.connect(self.browse_download_folder)

        folder_lyt.addWidget(self.folder_input)
        folder_lyt.addWidget(self.folder_browse_button)
        layout.addWidget(folder_group)

        # FFmpeg status
        ffmpeg_group = QGroupBox("🎬  FFmpeg Status")
        ffmpeg_lyt   = QVBoxLayout(ffmpeg_group)

        self.ffmpeg_status = QLabel("Checking FFmpeg status...")
        self.ffmpeg_status.setStyleSheet("color:#fff; font-size:13px; padding:5px;")
        ffmpeg_lyt.addWidget(self.ffmpeg_status)

        self.ffmpeg_download_button = QPushButton("Download & Install FFmpeg")
        self.ffmpeg_download_button.setStyleSheet(_BTN_BLUE)
        self.ffmpeg_download_button.clicked.connect(self.download_ffmpeg)
        self.ffmpeg_download_button.hide()
        ffmpeg_lyt.addWidget(self.ffmpeg_download_button)
        layout.addWidget(ffmpeg_group)

        # Quality defaults
        quality_group = QGroupBox("⚙️  Default Quality")
        quality_lyt   = QVBoxLayout(quality_group)

        def _q_row(label_text, combo_widget):
            row = QWidget()
            rl  = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color:#fff; font-size:13px;")
            rl.addWidget(lbl)
            rl.addWidget(combo_widget)
            rl.addStretch()
            return row

        self.video_quality_combo = QComboBox()
        self.video_quality_combo.addItems(["Best", "1080p", "720p", "480p", "360p"])
        self.video_quality_combo.setStyleSheet(_COMBO)
        quality_lyt.addWidget(_q_row("🎥  Video Quality:", self.video_quality_combo))

        self.audio_quality_combo = QComboBox()
        self.audio_quality_combo.addItems(["Best", "320k", "256k", "192k", "128k", "96k"])
        self.audio_quality_combo.setStyleSheet(_COMBO)
        quality_lyt.addWidget(_q_row("🔊  Audio Quality:", self.audio_quality_combo))
        layout.addWidget(quality_group)

        # Save button
        save_btn = QPushButton("💾  Save Settings")
        save_btn.setStyleSheet(_BTN_BLUE)
        save_btn.setMinimumHeight(42)
        save_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_btn)
        layout.addStretch()

        # Check FFmpeg on load
        self.update_ffmpeg_status()

    # ── Settings helpers ──────────────────────────────────

    def browse_download_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Download Folder",
            self.folder_input.text() or os.path.expanduser("~"),
        )
        if folder:
            self.folder_input.setText(folder)

    def update_ffmpeg_status(self):
        """Cross-platform FFmpeg detection via shutil.which."""
        # FIXED: was using subprocess(['where', 'ffmpeg']) which only works on Windows
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            # Get version string
            try:
                ver_out = subprocess.run(
                    ["ffmpeg", "-version"],
                    capture_output=True, encoding='utf-8', errors='replace', timeout=5,
                ).stdout
                ver_match = re.search(r"ffmpeg version ([\w.-]+)", ver_out)
                ver_str = ver_match.group(1) if ver_match else "unknown"
            except Exception:
                ver_str = "unknown"

            self.ffmpeg_status.setText(f"✅  FFmpeg {ver_str} — installed and ready.")
            self.ffmpeg_status.setStyleSheet(
                "QLabel{color:#4caf50;font-size:13px;padding:5px;}"
            )
            self.ffmpeg_download_button.hide()
            if hasattr(self, "ffmpeg_warning_banner"):
                self.ffmpeg_warning_banner.hide()
        else:
            self.ffmpeg_status.setText("❌  FFmpeg not found on this system.")
            self.ffmpeg_status.setStyleSheet(
                "QLabel{color:#f44336;font-size:13px;padding:5px;}"
            )
            self.ffmpeg_download_button.show()
            if hasattr(self, "ffmpeg_warning_banner"):
                self.ffmpeg_warning_banner.show()

    def download_ffmpeg(self):
        """Install FFmpeg via winget (Windows only)."""
        if os.name != "nt":
            QMessageBox.warning(self, "Error",
                "Automatic FFmpeg installation is only available on Windows.\n"
                "Please install FFmpeg manually from https://ffmpeg.org/download.html")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Installing FFmpeg...")
        dlg.setFixedSize(350, 150)
        dlg.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
        )
        d_lyt   = QVBoxLayout(dlg)
        d_info  = QLabel("Installing FFmpeg via winget...")
        d_bar   = QProgressBar()
        d_bar.setRange(0, 0)
        d_stat  = QLabel("Starting installation...")
        d_lyt.addWidget(d_info)
        d_lyt.addWidget(d_bar)
        d_lyt.addWidget(d_stat)
        dlg.show()
        QApplication.processEvents()

        self.ffmpeg_download_button.setEnabled(False)
        self.ffmpeg_status.setText("Installing FFmpeg...")

        try:
            d_stat.setText("Running winget... this may take a few minutes.")
            QApplication.processEvents()

            ps_cmd = (
                'Start-Process powershell '
                '-ArgumentList "-Command &{winget install --id Gyan.FFmpeg '
                '--accept-source-agreements --accept-package-agreements}" '
                '-Verb RunAs -Wait'
            )
            result = subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True, encoding='utf-8', errors='replace',
            )
            dlg.close()
            dlg.deleteLater()

            if result.returncode == 0:
                self.update_ffmpeg_status()
                QMessageBox.information(self, "Success",
                    "FFmpeg installed successfully! You can now use all features.")
            else:
                raise Exception(result.stderr or "winget returned non-zero exit code")

        except Exception as e:
            try:
                dlg.close()
                dlg.deleteLater()
            except Exception:
                pass
            QMessageBox.warning(self, "Error", f"FFmpeg installation failed:\n{e}")
        finally:
            self.ffmpeg_download_button.setEnabled(True)
            self.update_ffmpeg_status()

    def get_app_data_dir(self) -> str:
        if os.name == "nt":
            base = os.path.join(os.environ.get("APPDATA", "~"), "Youtility")
        elif os.name == "darwin":
            base = os.path.expanduser("~/Library/Application Support/Youtility")
        else:
            base = os.path.expanduser("~/.config/youtility")
        os.makedirs(base, exist_ok=True)
        return base

    def get_settings_path(self) -> str:
        return os.path.join(self.get_app_data_dir(), "settings.json")

    def get_download_path(self) -> str:
        return self.folder_input.text().strip() or os.path.expanduser("~/Downloads")

    def load_settings(self):
        try:
            path = self.get_settings_path()
            if not os.path.exists(path):
                return
            with open(path, "r", encoding="utf-8") as f:
                settings = json.load(f)

            self.folder_input.setText(settings.get("download_path", ""))

            for combo, key in (
                (self.video_quality_combo, "video_quality"),
                (self.audio_quality_combo, "audio_quality"),
            ):
                val = settings.get(key)
                if val:
                    idx = combo.findText(val)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
        except Exception as e:
            print(f"Settings load error: {e}")

    def save_settings(self):
        try:
            settings = {
                "download_path": self.folder_input.text(),
                "video_quality": self.video_quality_combo.currentText(),
                "audio_quality": self.audio_quality_combo.currentText(),
            }
            with open(self.get_settings_path(), "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
            QMessageBox.information(self, "Saved", "Settings saved successfully!")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not save settings:\n{e}")


# ─────────────────────────────────────────────────────────
#  Utility helper
# ─────────────────────────────────────────────────────────

def _make_label(text: str, style: str = "") -> QLabel:
    lbl = QLabel(text)
    if style:
        lbl.setStyleSheet(style)
    return lbl


# ─────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VideoDownloader()
    window.show()
    sys.exit(app.exec())
