# 🚀 v5.0.1 - YouTube Mixes and Smart Playlist Limits! 🎵

---

## Youtility v5.0.1 - Release Notes 🚀

---

## ✨ New Features & Improvements

### 📋 Smart Playlist Limits
* **Max Items to Fetch Selector:** Added a new **"Max items to fetch"** dropdown control in the Playlist Tab. 
* **Custom Limits:** You can now limit the number of playlist items extracted to **All, 10, 25, 50, 100, 200, or 500**. This prevents long loading times and lag when processing massive playlists or channels.

---

## 🐛 Bug Fixes & Mix Support

### 📺 YouTube Mixes (list=RD...) Support
* **Mix URL Conversion Fixed:** Resolved a bug where watch links containing YouTube Mix IDs (e.g., `list=RD...`) were incorrectly converted into standalone `/playlist?list=RD...` pages. Since YouTube does not have public playlist pages for Mixes, they resulted in errors. Mixes are now processed directly using the watch page URL.
* **Auto-Limit for Mixes:** When a YouTube Mix is detected, Youtility now automatically defaults the maximum items limit to **50** (if it was set to "All") to prevent infinite/extremely long queue extractions while keeping the UI responsive.
* **Personalized Playlist Warning:** Explained and documented behavior for personalized/private playlists. If a playlist is personal, YouTube returns "does not exist" or "unrecognized". Providing session cookies via terminal (using `--cookies-from-browser`) remains the recommended workaround for personal lists.

---

*Youtility Version v5.0.1 — June 2026 Made with ❤️ by ConsolAktif aka Murat Güler*
