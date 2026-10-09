# 🚀 v5.0.3 - Sturdier Downloads & Automated Builds! 🛠️

---

## Youtility v5.0.3 - Release Notes 🚀

---

## ✨ Improvements

### 📊 More Reliable Download Progress
* **Structured Progress Output:** Progress, speed and ETA now come from yt-dlp's machine-readable progress template instead of scraping its human-readable console text. Values such as `Unknown B/s`, `~` size estimates and non-English units no longer confuse the progress bar.
* **Smoother UI:** Progress updates are throttled (about 10 per second), so busy downloads and large playlists keep the window responsive.
* **Exact Output Path:** The final file path is reported directly by yt-dlp (after merging), so "open file / open folder" and temp-file cleanup always target the right file.

### 🌐 Better Network Resilience
* **Automatic Retries:** Downloads now retry failed requests and fragments up to 10 times, with a 20-second socket timeout, instead of giving up on the first hiccup.
* **YouTube Extraction:** If `deno` isn't installed, Youtility now points yt-dlp at `node` or `bun` when one of them is available, so YouTube formats are less likely to be missed.
* **Real Error Messages:** When a download fails, the actual yt-dlp error line is shown instead of just an exit code.

### 🎞️ Formats, Trimming & Audio
* **Smarter Format Ordering:** Qualities are sorted by resolution, then frame rate, then bitrate. Sizes fall back to yt-dlp's approximate size when the exact size isn't known.
* **Trim / Section Downloads:** Clip ranges (start–end and start–end-of-video) are passed to yt-dlp as download sections.
* **MP3 Conversion:** Audio extraction and MP3 conversion are now handled by yt-dlp itself in the same step, using the bitrate you picked in the app.
* **Single Video vs Playlist:** Fetching info for a single video no longer pulls in the whole playlist behind it.

### 🔄 yt-dlp Update Check
* **Correct Version Comparison:** Versions are compared numerically (`2026.08.19` vs `2026.10.02.1`) rather than as text, so the update prompt shows up exactly when a newer yt-dlp exists.
* **Safer Updater:** The downloaded yt-dlp.exe is swapped in with an atomic replace, and downloads use larger chunks.

---

## 🐛 Stability Fixes

* **Cancel Really Cancels:** Cancelling now stops yt-dlp **and** its child processes (ffmpeg and friends) without freezing the window.
* **No More Forced Thread Termination:** Background threads are no longer killed abruptly (a Qt thread destroyed while running can crash the app). They are detached, kept alive until they finish, and their late results are ignored.
* **Cleaner Temp Files:** After a cancel, only the partial files (`.part`, `.temp`, `.ytdl`, `-Frag*`) created by *that* download are removed, never your other downloads or unrelated files. Cleanup retries briefly while Windows releases file handles. Successful downloads also clear their leftover `.part`/`.ytdl` files.
* **Completion Dialog:** The "Merging…" animation no longer keeps spinning behind the completion dialog.
* **Safer Thumbnails:** A corrupt thumbnail image is skipped instead of causing an error.
* **Live Stream Detection:** Videos without a duration are only treated as live when they really aren't finished broadcasts.

### ⚡ Large Playlists
* The playlist table is now filled in one batch, which makes big playlists load noticeably faster.

---

## 🧰 Build & Packaging

* **Automated Builds:** The Windows EXE is now built automatically by GitHub Actions on every change to `main` and published to the Release when a `v*` tag is pushed, together with a `SHA256SUMS.txt` so you can verify your download.
* **Fixed `requirements.txt`:** Removed two unused FFmpeg Python packages (one of them doesn't exist on PyPI), so `pip install -r requirements.txt` works again for anyone building from source.

> ℹ️ FFmpeg is still required and is called as a regular system command (it can be installed from the **Settings** tab on Windows).

---

*Youtility Version v5.0.3 — October 2026 Made with ❤️ by ConsolAktif aka Murat Güler*
