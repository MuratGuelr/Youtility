# 🚀 v5.0.2 - yt-dlp Auto-Update Engine! 🔄

---

## Youtility v5.0.2 - Release Notes 🚀

---

## ✨ New Features & Improvements

### 🔄 yt-dlp Auto-Update System
* **Auto Update Check on Startup:** Youtility now automatically checks for yt-dlp updates when the app launches. If a newer version is available, a friendly dialog asks whether you'd like to update — no more manual reinstalling!
* **One-Click Update:** A brand new **"yt-dlp Engine"** card in the Settings tab lets you check for updates and download the latest yt-dlp.exe with a single click. Progress is shown with a smooth progress bar.
* **Standalone yt-dlp.exe:** The updated yt-dlp binary is downloaded to `%APPDATA%/Youtility/bin/` and is used automatically for all download operations. This means your app stays up to date without needing a new Youtility release.
* **Smart Fallback:** If the standalone yt-dlp.exe is not yet downloaded, Youtility gracefully falls back to the bundled version — no crashes, no errors.

### ⚡ Subprocess-Based Downloads
* **External Engine Support:** All download operations (single video, playlist, audio, info fetching) now use the standalone yt-dlp.exe via subprocess when available. This ensures the latest YouTube extractors are always used.
* **Live Stream Already Covered:** Live stream downloads already used the subprocess approach and now benefit from the same auto-update path.

---

## 🐛 Bug Fixes

### 🔧 HTTP 403: Forbidden — FIXED!
* **Root Cause:** YouTube frequently updates its API and blocks outdated yt-dlp versions. The bundled yt-dlp (2026.03.17) was 5 months behind the latest release (2026.08.19), causing `HTTP Error 403: Forbidden` on nearly all downloads.
* **Solution:** With the new auto-update system, yt-dlp stays current and download errors caused by outdated extractors are eliminated.

### 🧹 Code Cleanup
* **Duplicate Code Removed:** Fixed duplicated `setup_settings_tab()` and `update_ffmpeg_status()` methods that were accidentally left in the codebase.
* **Consistent Architecture:** All download threads now follow the same dual-mode pattern (subprocess + Python API fallback).

---

## ⚙️ Settings Tab Improvements

The Settings tab now includes a new **yt-dlp Engine** card with:
* 📦 Current version display (with source: bundled vs standalone)
* 🔍 "Check for Updates" button
* ⬇️ "Update yt-dlp" button (appears when update is available)
* 📊 Download progress bar
* ℹ️ Helpful description explaining why keeping yt-dlp updated matters

---

*Youtility Version v5.0.2 — August 2026 Made with ❤️ by ConsolAktif aka Murat Güler*
