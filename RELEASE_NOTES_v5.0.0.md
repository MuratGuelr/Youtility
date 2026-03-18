# 🔥 v5.0.0 Bigger, Smarter, Faster! 🚀

---

## Youtility v5.0.0 - Release Notes 🚀

---

## ✨ New Features

### 📋 Playlist Downloader
* **Full Playlist Support:** Download entire YouTube playlists or channels in one click
* **Video Selection Table:** See all videos listed with individual status tracking (Pending / Downloading / Done / Error)
* **Selective Downloads:** Check/uncheck individual videos before starting
* **Select All / Deselect All:** Bulk selection controls with live selected count display
* **Audio-Only Mode:** Download entire playlists as MP3 directly
* **Auto Subfolder:** Each playlist is saved into its own named folder automatically

### 🔴 Live Stream Recorder
* **Live Stream Recording:** Record active YouTube live streams and DVR replays
* **Stream Info Panel:** Displays title, channel, thumbnail, viewer count and live status before recording
* **Fragment Progress Tracking:** Real-time speed, downloaded size and estimated recorded duration
* **Time Range Support:** Set start/end times for DVR streams — auto-filled from video duration
* **Stop & Recover:** Stopping mid-recording automatically merges all fragments via FFmpeg
* **Output Format Selection:** Choose between MKV, MP4 or TS output
* **Thumbnail Download:** Save the stream thumbnail directly from the Live tab

### ⏱ Time Range Download (YouTube Tab)
* **Segment Download:** Download only a specific portion of a video
* **HH:MM:SS Inputs:** Start and end time fields auto-filled from video duration
* **Accurate Cuts:** Uses `force_keyframes_at_cuts` for frame-accurate trimming

---

## ⚡ Improvements

### 🎥 YouTube Tab
* **Enter Key Support:** Press Enter in the URL field to instantly start fetching
* **Smart URL Detection:** Playlist URLs auto-redirect to the Playlist tab; live stream URLs auto-redirect to the Live Stream tab
* **Non-Blocking Thumbnail Load:** Thumbnail now fetches in a background thread — UI stays responsive
* **Non-Blocking Info Fetch:** Video info loading moved to background thread — no more UI freeze
* **Custom Completion Dialog:** Download complete dialog now includes Open File and Show in Folder buttons
* **Smoother Speed Display:** Download speed averaged over 8 samples for stable readings
* **Indeterminate Progress Bar:** Shown during FFmpeg merge/remux phase for better feedback

### 🎬 Codec Editor
* **Preset Selector:** New veryfast → veryslow preset control, mapped to hardware encoder equivalents for NVIDIA/AMD
* **Compatibility Hints:** Real-time warnings when codec and container combinations are incompatible (e.g. VP9 in MP4, FLAC in MP4)
* **Smart Container Selection:** Output container auto-selected based on codec (VP9 → .webm, AV1/FLAC/Opus → .mkv)
* **Container Warning Dialogs:** User is warned and can confirm before saving to an incompatible format
* **Intel/AMD VAAPI Support:** New acceleration mode for Linux systems
* **CPU Fallback:** If GPU encoder fails, conversion automatically retries with CPU encoder

### 📜 History Tab
* **Stale Path Resolution:** If a stored file path no longer exists, Youtility searches for the final merged output automatically
* **Auto DB Correction:** Resolved paths are saved back to the database silently
* **Cleaner File Names:** Intermediate format tags (e.g. `.f251.webm`) stripped from display

### ⚙️ Settings Tab
* **Cross-Platform FFmpeg Detection:** Replaced Windows-only `where` command with `shutil.which` for macOS and Linux compatibility
* **FFmpeg Version Display:** Installed FFmpeg version now shown in the status label
* **Manual Install Guidance:** Non-Windows users shown a direct link to ffmpeg.org instead of the winget button

---

## 🐛 Bug Fixes

* **MP3 Conversion Fixed:** Switched from `libshine` (not included in standard FFmpeg) to `libmp3lame` — MP3 downloads now work reliably
* **Final File Path Fixed:** Download thread now correctly captures the merged output path via postprocessor hook instead of the intermediate fragment file
* **Threading Crash Fixed:** `DownloadManager` was missing `self._lock` — concurrent download crashes resolved
* **Playlist URL Normalization:** `watch?v=X&list=Y` URLs correctly converted to `playlist?list=Y` before fetching
* **History False "Not Found":** Files that exist at a resolved path no longer permanently show as missing
* **Non-ASCII FFmpeg Output:** Codec conversion no longer crashes on systems with Turkish or other non-ASCII locale output

---

## 💻 System Requirements

* **Operating Systems:** Windows 10/11, macOS 10.15+, or Linux
* **Python:** Version 3.8 or higher
* **FFmpeg:** (Automatic installation available on Windows)
* **Minimum RAM:** 4GB
* **Internet:** Active connection required

---

## 🌟 Key Features

* One-click video, playlist and live stream downloads
* Time range / segment download support
* Full playlist management with selective video picking
* Live stream recording with fragment recovery
* Advanced codec conversion with hardware acceleration
* Smart FFmpeg merge & path resolution
* Modern dark UI with tray integration
* Comprehensive download history with smart file tracking
* Cross-platform: Windows, macOS, Linux

---

*Youtility Version v5.0.0 — 2026 Made with ❤️ by ConsolAktif aka Murat Güler*
