import sys
import os
import urllib.request
from datetime import datetime
from PyQt5.QtCore import ( Qt, QThread, pyqtSignal,QSettings, 
                         QPropertyAnimation, QRect, QTimer, )
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                           QWidget, QLabel, QLineEdit, QPushButton, QComboBox, 
                           QProgressBar, QFileDialog, QMessageBox, QCheckBox, 
                           QTextEdit, QTableWidget, QTableWidgetItem,
                           QDialog, QGridLayout)
from PyQt5.QtGui import QIcon, QImage, QPixmap
from yt_dlp.utils import DownloadError
from imageio_ffmpeg import get_ffmpeg_exe
import yt_dlp

def ensure_ffmpeg():
    ffmpeg_path = get_ffmpeg_exe()
    os.environ["FFMPEG_BINARY"] = ffmpeg_path
    return ffmpeg_path

class YTLogger:
    def __init__(self, hata_sinyali):
        self.hata_sinyali = hata_sinyali

    def debug(self, msg):
        if "has already been downloaded" in msg:
            self.hata_sinyali.emit("Bu video zaten indirilmiş.")

    def warning(self, msg):
        pass

    def error(self, msg):
        self.hata_sinyali.emit(f"Hata: {msg}")


class DownloaderThread(QThread):
    ilerleme = pyqtSignal(int)
    hiz = pyqtSignal(str)
    indirme_bitti = pyqtSignal(str)
    cevirme_bitti = pyqtSignal(str)
    hata = pyqtSignal(str)

    def __init__(self, url, format_option, output_path, quality, subtitle=False, 
                 subtitle_lang='tr', speed_limit=None):
        super().__init__()
        self.url = url
        self.format_option = format_option
        self.output_path = output_path
        self.quality = quality
        self.subtitle = subtitle
        self.subtitle_lang = subtitle_lang
        self.speed_limit = speed_limit
        self.downloaded_file = None

    def run(self):
        ffmpeg_path = ensure_ffmpeg()
        logger = YTLogger(self.hata)
        
        ydl_opts = {
            'ffmpeg_location': ffmpeg_path,
            'logger': logger,
            'progress_hooks': [self.progress_hook]
        }

        if self.speed_limit:
            ydl_opts['ratelimit'] = self.speed_limit * 1024

        if self.subtitle:
            ydl_opts.update({
                'writesubtitles': True,
                'subtitleslangs': [self.subtitle_lang],
                'writeautomaticsub': True
            })

        if self.format_option == 'mp3':
            ydl_opts.update({
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(self.output_path, '%(title)s.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': self.quality,
                }],
                'prefer_ffmpeg': True
            })
        else:  # mp4
            ydl_opts.update({
                'format': f'bestvideo[height<={self.quality}]+bestaudio/best',
                'merge_output_format': 'mp4',
                'outtmpl': os.path.join(self.output_path, '%(title)s.%(ext)s')
            })

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                if info:
                    self.downloaded_file = os.path.join(
                        self.output_path,
                        f"{info['title']}.{self.format_option}"
                    )
                    self.indirme_bitti.emit(self.downloaded_file)
        except Exception as e:
            self.hata.emit(f"İndirme sırasında hata oluştu: {str(e)}")

    def progress_hook(self, d):
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '0.0%').strip('%')
            speed = d.get('_speed_str', '0.0KiB/s').strip()
            try:
                self.ilerleme.emit(int(float(percent)))
            except ValueError:
                pass
            self.hiz.emit(f"İndirme Hızı: {speed}")
        elif d['status'] == 'finished':
            if self.downloaded_file:
                self.indirme_bitti.emit(self.downloaded_file)

                
class YouTubeDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Downloader by ConsolAktif")

        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else: 
            base_path = os.path.dirname(__file__)

        icon_path = os.path.join(base_path, "icon.ico")
        self.setWindowIcon(QIcon(icon_path))

        self.setGeometry(800, 300, 400, 700)
        self.default_output_path = os.path.expanduser("~/Downloads")

        self.video_formats = []
        self.audio_formats = []
        self.qualities = []
        self.download_history = []
        self.current_thumbnail = None

        self.init_ui()

    def __init__(self):
        super().__init__()
        self.load_saved_location()
        self.setWindowTitle("YouTube Downloader by ConsolAktif")
        self.setGeometry(800, 300, 500, 700)
        self.center_window()

    def center_window(self):
        # Ekran boyutlarını al
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        window_geometry = self.frameGeometry()

        # Merkez noktasını hesapla
        center_point = screen_geometry.center()

        # Merkezin biraz yukarısına taşı
        center_point.setY(center_point.y() - 40)  # 100 piksel yukarı kaydır

        # Merkezin biraz yukarısına taşı
        center_point.setX(center_point.x() - 150)  # 100 piksel yukarı kaydır
        

        # Pencerenin geometrisini yeni noktaya taşı
        window_geometry.moveCenter(center_point)

        # Pencereyi taşımak
        self.move(window_geometry.topLeft())

        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else: 
            base_path = os.path.dirname(__file__)

        icon_path = os.path.join(base_path, "icon.ico")
        self.setWindowIcon(QIcon(icon_path))

        self.default_output_path = os.path.expanduser("~/Downloads")
        self.video_formats = []
        self.audio_formats = []
        self.qualities = []
        self.download_history = []
        self.current_thumbnail = None
        self.expanded = False

        self.init_ui()
        self.init_expanded_ui()  # Genişletilmiş UI'yi başlangıçta gizli olarak oluştur

    def select_output_directory(self):
        try:
            directory = QFileDialog.getExistingDirectory(
                self,
                "İndirme Konumunu Seç",
                self.default_output_path,
                QFileDialog.ShowDirsOnly
            )
            if directory:
                self.default_output_path = directory
                self.location_label.setText(f"İndirme Konumu: {directory}")
                settings = QSettings("ConsolAktif", "Downloader")
                settings.setValue("download_location", directory)
        except Exception as e:
            self.show_error(f"İndirme konumu seçilirken hata oluştu: {str(e)}")


    def load_saved_location(self):
        try:
            settings = QSettings("ConsolAktif", "Downloader")
            saved_location = settings.value("download_location", type=str)

            if saved_location:
                self.default_output_path = saved_location
            else:
                self.default_output_path = os.path.expanduser("~/Downloads")
        except Exception as e:
            self.default_output_path = os.path.expanduser("~/Downloads")
            self.show_error(f"Kaydedilen konum yüklenirken hata oluştu: {str(e)}")

    def init_ui(self):
        # Ana widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout()  # Ana layout yatay
        central_widget.setLayout(main_layout)
        
        
        # Sol Panel - Video URL Girişi
        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_panel.setLayout(left_layout)
        left_panel.setMaximumWidth(600)
        

        # Başlık ve açıklama
        title_label = QLabel()
        title_label.setText("""
            YouTube Video Downloader <br> 
            <span style="color: gray; font-size: 16px;"><span style="font-size: 12px;">by </span>ConsolAktif</span>
        """)
        title_label.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: white;
                margin-bottom: 20px;
            }
        """)

        title_label.setAlignment(Qt.AlignCenter)
        
        desc_label = QLabel("Video URL'sini yapıştırın.")
        desc_label.setStyleSheet("color: #aaa; font-size: 14px;")
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignCenter)

        # URL girişi için zarif bir kutu
        url_container = QWidget()
        url_container.setStyleSheet("""
            QWidget {
                background-color: #2d2d2d;
                border-radius: 10px;
                padding: 25px;
            }
        """)
        url_layout = QVBoxLayout()
        url_container.setLayout(url_layout)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("YouTube video URL'si yapıştırın | Aramak istediğiniz videoyu yazın...")
        self.url_input.setStyleSheet("""
            QLineEdit {
                padding: 12px;
                background-color: #333;
                border: 1px solid #444;
                border-radius: 5px;
                color: white;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #0078D7;
            }
        """)

        
        # VEYA ayırıcı
        or_label = QLabel("VEYA")
        or_label.setAlignment(Qt.AlignCenter)
        or_label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 12px;
                margin: 10px 0;
            }
        """)

        self.url_list = QTextEdit()
        self.url_list.setPlaceholderText("Toplu indirme için her satıra bir URL gelecek şekilde yapıştırın")
        self.url_list.setStyleSheet("""
            QTextEdit {
                padding: 12px;
                background-color: #333;
                border: 1px solid #444;
                border-radius: 5px;
                color: white;
                font-size: 14px;
            }
            QTextEdit:focus {
                border: 1px solid #0078D7;
            }
        """)
        self.url_list.setMaximumHeight(100)

        self.fetch_button = QPushButton("Video Bilgilerini Getir")
        self.fetch_button.setStyleSheet("""
            QPushButton {
                background-color: #00b51c;
                color: white;
                padding: 12px;
                border-radius: 5px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #02d422;
            }
            QPushButton:pressed {
                background-color: #009900;
            }
            QPushButton:disabled {
                background-color: #444;
            }
        """)
        self.fetch_button.clicked.connect(self.fetch_video_info)

        # Widget'ları URL container'a ekle
        url_layout.addWidget(self.url_input)
        url_layout.addWidget(self.fetch_button)

        # Sol panel layout'a widget'ları ekle
        left_layout.addWidget(title_label)
        left_layout.addWidget(desc_label)
        left_layout.addSpacing(20)
        left_layout.addWidget(url_container)
        left_layout.addStretch()

        # Sağ Panel - Genişletilmiş Özellikler (başlangıçta gizli)
        self.right_panel = QWidget()
        self.right_panel.setVisible(False)
        right_layout = QVBoxLayout()
        self.right_panel.setLayout(right_layout)

        # Ana layout'a panelleri ekle
        main_layout.addWidget(left_panel)
        main_layout.addWidget(self.right_panel)

        # Ana pencere stili
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
                
            }
            QWidget {
                background-color: #1e1e1e;
            }
        """)
    def init_expanded_ui(self):
        right_layout = self.right_panel.layout()

        # Thumbnail ve video bilgisi container'ı
        info_container = QWidget()
        info_container.setStyleSheet("""
            QWidget {
                background-color: #171717;
                border-radius: 10px;
                padding: 5px;
                margin-top: 5px;
            }
        """)
        info_layout = QVBoxLayout()
        info_container.setLayout(info_layout)

        # Thumbnail
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(480, 270)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setStyleSheet("""
            QLabel {
                background-color: #333;
                border-radius: 15px;
            }
        """)

        # Video bilgisi
        self.info_label = QLabel("Video bilgileri yükleniyor...")
        self.info_label.setStyleSheet("color: white; font-size: 14px; font-weight: bold;")
        self.info_label.setWordWrap(True)

        info_layout.addWidget(self.thumbnail_label)
        info_layout.addWidget(self.info_label)

       # İndirme seçenekleri container'ı
        options_container = QWidget()
        options_container.setStyleSheet("""
            QWidget {
                border-radius: 10px;
                border: 1px solid #444;
            }
        """)
        options_layout = QGridLayout()
        options_container.setLayout(options_layout)

        # Format seçimi
        format_label = QLabel("Format:")
        format_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 14px;
                font-weight: bold;
                border:none;
            }
        """)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["MP4", "MP3"])
        self.format_combo.setStyleSheet("""
            QComboBox {
                padding: 0;
            }
        """)


        self.format_combo.currentTextChanged.connect(self.update_quality_options)

        # Kalite seçimi
        quality_label = QLabel("Kalite:")
        quality_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 14px;
                font-weight: bold;
                border:none;
            }
        """)
        self.quality_combo = QComboBox()
        self.quality_combo.currentIndexChanged.connect(self.update_download_button_text)

        # Altyazı seçenekleri
        self.subtitle_check = QCheckBox("Altyazı İndir")
        self.subtitle_check.setStyleSheet("""
            QCheckBox {
                color: white;
                font-size: 14px;
                spacing: 5px;
                border:none;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                background-color: #444;
                border: 1px solid #666;
                border-radius: 3px;
                border:none;
            }
            QCheckBox::indicator:checked {
                background-color: #0da802;
                border:none;
            }
        """)
        self.subtitle_lang = QComboBox()
        self.subtitle_lang.addItems(["Türkçe", "İngilizce", "Otomatik"])
       

        # Hız limiti
        self.speed_limit_check = QCheckBox("Hız Limiti")
        self.speed_limit_check.setStyleSheet("""
            QCheckBox {
                color: white;
                font-size: 14px;
                spacing: 5px;
                border:none;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                background-color: #444;
                border: 1px solid #666;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background-color: #0da802;
                border: 1px solid #0a8a01;
            }
        """)
        self.speed_limit_input = QLineEdit()
        self.speed_limit_input.setPlaceholderText("KB/s")
        self.speed_limit_input.setStyleSheet("""
            QLineEdit {
                padding: 5px;
                background-color: #292929;
                border:none;
                border-radius: 5px;
                color: white;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #1E90FF;
            }
        """)


        # Grid'e seçenekleri ekle
        options_layout.addWidget(format_label, 0, 0)
        options_layout.addWidget(self.format_combo, 0, 1)
        options_layout.addWidget(quality_label, 1, 0)
        options_layout.addWidget(self.quality_combo, 1, 1)
        options_layout.addWidget(self.subtitle_check, 2, 0)
        options_layout.addWidget(self.subtitle_lang, 2, 1)
        options_layout.addWidget(self.speed_limit_check, 3, 0)
        options_layout.addWidget(self.speed_limit_input, 3, 1)

        # İndirme butonu
        self.download_button = QPushButton("İndir")
        self.download_button.setStyleSheet("""
            QPushButton {
                background-color: #0da802;
                color: white;
                padding: 12px;
                border-radius: 5px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0ebd02;
            }
            QPushButton:disabled {
                background-color: #444;
            }
        """)
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self.download_video)

        self.location_label = QLabel(f"İndirme Konumu: {self.default_output_path}")
        self.location_label.setStyleSheet("color: white; font-size: 12px;")
            
            # İndirme konumu seçme butonu
        self.select_location_button = QPushButton("İndirme Yerini Seç")
        self.select_location_button.setStyleSheet("""
                QPushButton {
                    background-color: #0078D7;
                    color: white;
                    border: none;
                    padding: 8px 15px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #005BB5;
                }
            """)
        self.select_location_button.clicked.connect(self.select_output_directory)

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #444;
                border-radius: 3px;
                text-align: center;
                color: white;
            }
            QProgressBar::chunk {
                background-color: #087d00;
            }
        """)

        self.speed_label = QLabel("İndirme Hızı: 0.0KiB/s")
        self.speed_label.setStyleSheet("color: white;")

        # Playlist seçeneği
        self.playlist_check = QCheckBox("Playlist'teki Tüm Videoları İndir")
        self.playlist_check.setStyleSheet("color: white;")
        self.playlist_check.setVisible(False)  # Başlangıçta gizli olsun

        # Grid'e playlist seçeneğini ekle (4. satıra)
        options_layout.addWidget(self.playlist_check, 4, 0, 1, 2)  # 4. satır, 0. sütun, 1 satır yükseklik, 2 sütun genişlik

        # Widget'ları sağ panel layout'a ekle
        right_layout.addWidget(info_container)
        right_layout.addWidget(options_container)
        right_layout.addWidget(self.download_button)
        right_layout.addWidget(self.progress_bar)
        right_layout.addWidget(self.speed_label)
        right_layout.addWidget(self.select_location_button)
        right_layout.addStretch()

        def get_combo_style():
            return """
                QComboBox {
                    padding: 5px;
                    background-color: #292929;
                    border: 1px solid #444;
                    border-radius: 5px;
                    color: white;
                    font-size: 14px;
                }
                QComboBox::drop-down {
                    border: none;
                    background: #292929;
                }
                QComboBox::down-arrow {
                    image: none;
                    border-width: 0px;
                }
                QComboBox QAbstractItemView {
                    background-color: #292929;
                    border: 1px solid #444;
                    selection-background-color: #444;
                    selection-color: white;
                    color: white;
                }
                QComboBox QScrollBar:vertical {
                    background-color: #292929;
                    width: 10px;
                    border: none;
                }
                QComboBox QScrollBar::handle:vertical {
                    background-color: #444;
                    min-height: 30px;
                    border-radius: 5px;
                }
                QComboBox QScrollBar::add-line:vertical, QComboBox QScrollBar::sub-line:vertical {
                    border: none;
                    background: none;
                }
            """
        
        # ComboBox'lara stili uygula
        self.format_combo.setStyleSheet(get_combo_style())
        self.quality_combo.setStyleSheet(get_combo_style())
        self.subtitle_lang.setStyleSheet(get_combo_style())


    
    def show_expanded_ui(self):
        if not self.expanded:
            self.right_panel.setVisible(True)
            self.expanded = True


    def fetch_video_info(self):
        url = self.url_input.text()
        if not url and not self.url_list.toPlainText().strip():
            self.show_error("Lütfen en az bir URL girin.")
            return

        self.fetch_button.setText("Bilgiler Alınıyor...")
        self.fetch_button.setEnabled(False)
        self.show_expanded_ui()  # Genişletilmiş UI'yi göster
        QTimer.singleShot(100, lambda: self.get_video_info(url))
        

    def get_video_info(self, url):
        try:
            ydl_opts = {
                'ignoreerrors': True,
                'quiet': True
            }
            
            # URL boş veya None ise ve URL listesi doluysa
            if not url and self.url_list.toPlainText().strip():
                urls = self.url_list.toPlainText().strip().split('\n')
                if urls:
                    url = urls[0]  # İlk URL'yi kullan
            
            # URL'yi düzelt - YouTube araması için
            if not url.startswith(('http://', 'https://')):
                url = f'ytsearch:{url}'
                
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            
            # Eğer arama sonucu ise
            if info.get('entries'):
                info = info['entries'][0]  # İlk sonucu al
            
            # Geri kalan kod aynı...
            if info.get('thumbnail'):
                self.load_thumbnail(info['thumbnail'])
                
                # Thumbnail yükleme
                if info.get('thumbnail'):
                    self.load_thumbnail(info['thumbnail'])
                
                title = info.get('title', 'Bilinmeyen Başlık')
                duration = info.get('duration', 0)
                minutes, seconds = divmod(duration, 60)

                self.info_label.setText(f"""
                    <div style="padding: 10px; color: white; border-radius: 10px; width: fit-content; text-align: center;">
                        <p style="margin: 0;">
                            <span style="font-weight: bold; font-size: 16px;">Başlık:</span>
                            <span style="font-weight: normal; font-size: 14px;"> {title}</span>
                        </p>
                        <p style="margin: 0; margin-top: 5px;">
                            <span style="font-weight: bold; font-size: 14px;">Süre:</span>
                            <span style="font-weight: normal; font-size: 14px;"> {minutes}<span style="font-size: 11px;">dk</span></span>
                            <span style="font-weight: normal; font-size: 12px;"> {seconds}<span style="font-size: 10px;">sn</span></span>
                        </p>
                    </div>
                """)

                # Playlist kontrolü
                if info.get('_type') == 'playlist':
                    self.playlist_check.setVisible(True)
                    self.playlist_check.setChecked(False)
                else:
                    self.playlist_check.setVisible(False)

                # Format ve kalite bilgilerini ayır
                self.video_formats = []
                self.audio_formats = []
                
                for f in info['formats']:
                    size = f.get('filesize') or f.get('filesize_approx')
                    height = f.get('height')
                    vcodec = f.get('vcodec')
                    acodec = f.get('acodec')
                    abr = f.get('abr')
                    
                    if size:
                        if vcodec != 'none' and height:
                            self.video_formats.append({
                                'height': height,
                                'size': size
                            })
                        elif acodec != 'none' and abr:
                            self.audio_formats.append({
                                'abr': abr,
                                'size': size
                            })

                self.format_combo.setEnabled(True)
                self.quality_combo.setEnabled(True)
                self.update_quality_options()

        except Exception as e:
            self.show_error(f"Video bilgisi alınamadı: {str(e)}")
        finally:
            self.fetch_button.setText("Video Bilgisi Getir")
            self.fetch_button.setEnabled(True)


    def load_thumbnail(self, url):
        try:
            data = urllib.request.urlopen(url).read()
            image = QImage()
            image.loadFromData(data)
            pixmap = QPixmap(image).scaled(450, 250, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            self.thumbnail_label.setPixmap(pixmap)

            self.thumbnail_label.setStyleSheet("""
                QLabel {
                    border-radius: 15px;
                    padding: 5px;
                    background-color: #121212;
                }
            """)
        except Exception as e:
            print(f"Thumbnail yüklenemedi: {e}")



    def update_quality_options(self):
        selected_format = self.format_combo.currentText().lower()
        self.quality_combo.clear()
        self.qualities = []
        
        if selected_format == 'mp3':
            standard_qualities = [128, 192, 256, 320]
            
            available_bitrates = set()
            for audio in self.audio_formats:
                if audio['abr']:
                    available_bitrates.add(int(audio['abr']))
            
            quality_map = {}
            for abr in available_bitrates:
                closest_quality = min(standard_qualities, key=lambda x: abs(x - abr))
                if closest_quality not in quality_map:
                    size = next((a['size'] for a in self.audio_formats 
                               if a['abr'] and abs(a['abr'] - closest_quality) < 30), 0)
                    quality_map[closest_quality] = size
            
            for quality in sorted(quality_map.keys(), reverse=True):
                self.qualities.append((f"{quality}kbps", quality_map[quality]))
                self.quality_combo.addItem(f"{quality}kbps")
                
        else:  # mp4
            resolution_map = {}
            
            for video in self.video_formats:
                if video['height']:
                    height = video['height']
                    if height not in resolution_map or video['size'] > resolution_map[height]:
                        resolution_map[height] = video['size']
            
            for height in sorted(resolution_map.keys(), reverse=True):
                self.qualities.append((f"{height}p", resolution_map[height]))
                self.quality_combo.addItem(f"{height}p")

        if self.qualities:
            self.update_download_button_text()
            self.download_button.setEnabled(True)
        else:
            self.download_button.setEnabled(False)
            self.download_button.setText("İndir")

    def update_download_button_text(self):
        if self.qualities and self.quality_combo.currentIndex() >= 0:
            current_quality, size = self.qualities[self.quality_combo.currentIndex()]
            size_mb = size / (1024 * 1024)
            self.download_button.setText(f"İndir ({size_mb:.1f} MB)")
        else:
            self.download_button.setText("İndir")

    def change_output_path(self):
        selected_dir = QFileDialog.getExistingDirectory(
            self, "Kayıt Klasörü Seçin", self.default_output_path
        )
        if selected_dir:
            self.default_output_path = selected_dir
            self.output_path_label.setText(f"Kayıt Yolu: {self.default_output_path}")

    def start_pulse_animation(self, button):
        self.animation = QPropertyAnimation(button, b"geometry")
        original_geometry = button.geometry()
        self.animation.setDuration(500)
        self.animation.setLoopCount(6)
        self.animation.setKeyValueAt(0, original_geometry)
        self.animation.setKeyValueAt(0.5, QRect(
            original_geometry.x() - 5,
            original_geometry.y() - 5,
            original_geometry.width() + 10,
            original_geometry.height() + 10
        ))
        self.animation.setKeyValueAt(1, original_geometry)
        self.animation.start()

    def show_download_history(self):
        history_dialog = QDialog(self)
        history_dialog.setWindowTitle("İndirme Geçmişi")
        history_dialog.setModal(True)
        history_dialog.setStyleSheet("background-color: #121212; color: white;")
        
        layout = QVBoxLayout()
        
        table = QTableWidget()
        table.setStyleSheet("""
            QTableWidget {
                background-color: #121212;
                color: white;
                gridline-color: #444;
            }
            QHeaderView::section {
                background-color: #242424;
                color: white;
                padding: 4px;
            }
        """)
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Tarih", "URL", "Format", "Kalite"])
        
        table.setRowCount(len(self.download_history))
        for i, download in enumerate(self.download_history):
            table.setItem(i, 0, QTableWidgetItem(download['date']))
            table.setItem(i, 1, QTableWidgetItem(download['url']))
            table.setItem(i, 2, QTableWidgetItem(download['format']))
            table.setItem(i, 3, QTableWidgetItem(download['quality']))
        
        layout.addWidget(table)
        history_dialog.setLayout(layout)
        history_dialog.resize(600, 400)
        history_dialog.exec_()

    def download_video(self):
        if self.url_list.toPlainText().strip():
            self.batch_download()
            return

        url = self.url_input.text()
        format_option = self.format_combo.currentText().lower()
        quality = self.quality_combo.currentText().replace('p', '').replace('kbps', '')

        if not url or not format_option or not quality:
            self.show_error("Lütfen tüm alanları doldurun.")
            return

        self.download_button.setText("İndiriliyor...")
        self.download_button.setEnabled(False)

        # İndirme geçmişine ekle
        self.download_history.append({
            'url': url,
            'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'format': format_option,
            'quality': self.quality_combo.currentText()
        })

        self.downloader_thread = DownloaderThread(
            url=url,
            format_option=format_option,
            output_path=self.default_output_path,
            quality=quality,
            subtitle=self.subtitle_check.isChecked(),
            subtitle_lang=self.subtitle_lang.currentText().lower(),
            speed_limit=int(self.speed_limit_input.text()) if self.speed_limit_check.isChecked() and self.speed_limit_input.text().isdigit() else None
        )
        self.downloader_thread.ilerleme.connect(self.progress_bar.setValue)
        self.downloader_thread.hiz.connect(self.speed_label.setText)
        self.downloader_thread.indirme_bitti.connect(self.download_finished)
        self.downloader_thread.hata.connect(self.download_error)
        self.downloader_thread.start()

    def batch_download(self):
        urls = [url.strip() for url in self.url_list.toPlainText().strip().split('\n') if url.strip()]
        if not urls:
            self.show_error("Lütfen en az bir URL girin.")
            return
            
        for url in urls:
            # URL'yi düzelt
            if not url.startswith(('http://', 'https://')):
                url = f'ytsearch:{url}'
                
            format_option = self.format_combo.currentText().lower()
            quality = self.quality_combo.currentText().replace('p', '').replace('kbps', '')

            self.download_history.append({
                'url': url,
                'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'format': format_option,
                'quality': self.quality_combo.currentText()
            })

            downloader = DownloaderThread(
                url=url,
                format_option=format_option,
                output_path=self.default_output_path,
                quality=quality,
                subtitle=self.subtitle_check.isChecked(),
                subtitle_lang=self.subtitle_lang.currentText().lower(),
                speed_limit=int(self.speed_limit_input.text()) if self.speed_limit_check.isChecked() and self.speed_limit_input.text().isdigit() else None
            )
            downloader.ilerleme.connect(self.progress_bar.setValue)
            downloader.hiz.connect(self.speed_label.setText)
            downloader.indirme_bitti.connect(self.download_finished)
            downloader.hata.connect(self.download_error)
            downloader.start()



    def download_finished(self, downloaded_file):
        self.progress_bar.setValue(100)
        self.speed_label.setText("İndirme tamamlandı!")
        
        msg = QMessageBox()
        msg.setWindowTitle("İndirme Tamamlandı")
        msg.setText(f"Dosya başarıyla indirildi!\n\nDosya: {os.path.basename(downloaded_file)}\nKonum: {os.path.dirname(downloaded_file)}")
        msg.setStandardButtons(QMessageBox.Ok)
        
        open_folder_button = msg.addButton("Klasörü Aç", QMessageBox.ActionRole)
        open_folder_button.clicked.connect(lambda: os.startfile(os.path.dirname(downloaded_file)))
        
        msg.exec_()
        
        self.download_button.setText("İndir")
        self.download_button.setEnabled(True)

    def download_error(self, error_message):
        self.download_button.setText("İndir")
        self.download_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.speed_label.setText("İndirme Hızı: 0.0KiB/s")
        self.show_error(error_message)

    # MessageBox stilini güncelle (show_error metodunda)
    def show_error(self, message):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Hata")
        msg.setText(message)
        msg.setStyleSheet("""
            QMessageBox {
                padding: 10px;
            }
            QMessageBox QLabel {
                color: white;
                font-size: 14px;
            }
            QPushButton {
                color: white;
                border: 1px solid #555;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #555;
            }
        """)
        msg.exec_()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = YouTubeDownloader()
    window.show()
    sys.exit(app.exec_())