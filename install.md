pyinstaller --noconsole --onefile --hidden-import=yt_dlp --hidden-import=PyQt6 --name "Youtility" --icon=icon.ico --add-data "icon.ico;." --windowed main-en.py
