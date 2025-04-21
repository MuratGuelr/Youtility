import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QTabWidget,
                            QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                            QPushButton, QComboBox, QProgressBar, QMessageBox,
                            QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
                            QGroupBox, QSpinBox, QCheckBox,QSystemTrayIcon, QMenu, QDialog)
from PyQt6.QtCore import (Qt, QThread, pyqtSignal, QDateTime, QUrl, QMetaObject,
                         Q_ARG, pyqtSlot, QTimer)
from PyQt6.QtGui import QPixmap, QDesktopServices, QColor, QIcon
import yt_dlp
import requests
from datetime import timedelta
import subprocess
import json
import threading
import shutil
import webbrowser
import ffmpeg
import re
import time
import sqlite3
from datetime import datetime
import signal
import zipfile

class VideoDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Youtility")

        # İkon yolunu doğru şekilde al
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        
        # İkonu yükle ve kontrol et
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
            self.setWindowIcon(icon)  # Pencere ikonu
            
            # Tray icon ayarları
            self.tray_icon = QSystemTrayIcon(self)
            self.tray_icon.setIcon(icon)  # Aynı ikonu tray için kullan
            self.tray_icon.setToolTip("Youtility")
            
            # Windows'ta görev çubuğu ikonu için
            if os.name == 'nt':  # Windows ise
                import ctypes
                myappid = 'consolaktif.youtubedownloader.1.0'  # Arbitrary string
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        else:
            print(f"İkon dosyası bulunamadı: {icon_path}")
        
        # Tray menüsü oluştur
        tray_menu = QMenu()
        show_action = tray_menu.addAction("Göster")
        show_action.triggered.connect(self.show)
        quit_action = tray_menu.addAction("Çıkış")
        quit_action.triggered.connect(app.quit)
        self.tray_icon.setContextMenu(tray_menu)
        
        self.tray_icon.setVisible(True)

        # Diğer başlangıç ayarları
        self.active_download = None
        self.download_path = os.path.expanduser("~/Downloads")
        self.setup_ui_style()
        self.init_ui()
        self.download_manager = DownloadManager()
        self.load_settings()


    def setup_ui_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QTabWidget {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QTabWidget::pane {
                border: 1px solid #3a3a3a;
            }
            QTabBar::tab {
                background-color: #3a3a3a;
                color: #ffffff;
                padding: 8px 20px;
                margin: 2px;
            }
            QTabBar::tab:selected {
                background-color: #4a4a4a;
            }
            QLabel {
                color: #ffffff;
            }
            QLineEdit {
                background-color: #3a3a3a;
                color: #ffffff;
                padding: 5px;
                border: 1px solid #4a4a4a;
            }
            QPushButton {
                background-color: #0d47a1;
                color: #ffffff;
                padding: 8px 15px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
            QComboBox {
                background-color: #3a3a3a;
                color: #ffffff;
                padding: 5px;
                border: 1px solid #4a4a4a;
            }
            QProgressBar {
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                text-align: center;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #0d47a1;
                border-radius: 3px;
            }
            QTableWidget {
                background-color: #2b2b2b;
                color: #e0e0e0;
                gridline-color: #383838;
                border: 1px solid #383838;
                border-radius: 4px;
                selection-background-color: #1976d2;
                selection-color: #ffffff;
            }
            QTableWidget::item {
                padding: 6px;
                border: none;
                border-bottom: 1px solid #383838;
                font-size: 13px;
            }
            QTableWidget::item:selected {
                background-color: #1976d2;
                color: #ffffff;
            }
            QTableWidget::item:focus {
                border: none;
                background-color: #1976d2;
                color: #ffffff;
            }
            QTableWidget::item:selected:active {
                border: none;
                background-color: #1976d2;
                color: #ffffff;
            }
            QTableWidget::item:selected:!active {
                border: none;
                background-color: #1976d2;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #232323;
                color: #90caf9;
                padding: 8px;
                border: none;
                border-right: 1px solid #383838;
                border-bottom: 2px solid #1976d2;
                font-weight: bold;
                font-size: 13px;
            }
            QTableWidget QTableCornerButton::section {
                background-color: #232323;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #2b2b2b;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background-color: #424242;
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #4f4f4f;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background-color: #2b2b2b;
            }
        """)

    def init_ui(self):
        self.setMinimumSize(700, 650)
        
        # Ana widget ve layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Tab widget oluşturma
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tabları oluştur
        self.youtube_tab = QWidget()
        self.web_video_tab = QWidget()
        self.codec_tab = QWidget()
        self.history_tab = QWidget()
        self.settings_tab = QWidget()

        # Tabları ekle
        self.tabs.addTab(self.youtube_tab, "YouTube Video")
        self.tabs.addTab(self.codec_tab, "Video Codec")
        self.tabs.addTab(self.settings_tab, "Ayarlar")

        # Tab içeriklerini oluştur
        self.setup_youtube_tab()
        self.setup_web_video_tab()
        self.setup_codec_tab()
        self.setup_history_tab()
        self.setup_settings_tab()

    def setup_youtube_tab(self):
        layout = QVBoxLayout(self.youtube_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # FFmpeg uyarı banner'ı
        self.ffmpeg_warning_banner = QWidget()
        self.ffmpeg_warning_banner.setStyleSheet("""
                QWidget {
                    border-radius: 4px;
                    padding: 10px;
                    margin-bottom: 10px;
                }
            """)
        banner_layout = QHBoxLayout(self.ffmpeg_warning_banner)
        banner_layout.setContentsMargins(10, 10, 10, 10)
        
        warning_text = QLabel("⚠️ FFmpeg kurulu değil. Video indirme işlemi için FFmpeg gereklidir.")
        warning_text.setStyleSheet("color: #ffffff; font-size: 13px;border: 1px solid #404040;")
        banner_layout.addWidget(warning_text)
        
        install_button = QPushButton("FFmpeg Kur")
        install_button.setStyleSheet("""
            QPushButton {
                background-color: #cf0000;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 15px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e30202;
            }
        """)
        install_button.clicked.connect(self.download_ffmpeg)
        banner_layout.addWidget(install_button)
        
        layout.addWidget(self.ffmpeg_warning_banner)
        self.ffmpeg_warning_banner.hide()  # Başlangıçta gizle

        # Ana container'ı oluştur
        main_container = QWidget()
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(30)
        
        # URL container'ını merkeze almak için
        self.url_wrapper = QWidget()
        self.url_wrapper_layout = QVBoxLayout(self.url_wrapper)  # Layout'u self ile erişilebilir yap
        self.url_wrapper_layout.setContentsMargins(0, 50, 0, 50)
        
        # Logo ve başlık container'ı
        self.logo_container = QWidget()  # self ile erişilebilir yap
        logo_layout = QVBoxLayout(self.logo_container)
        logo_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Logo
        logo_label = QLabel()
        logo_pixmap = QPixmap("icon.ico").scaled(128,128, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        logo_label.setPixmap(logo_pixmap)
        logo_layout.addWidget(logo_label, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Başlık
        title_label = QLabel("YouTube Video İndir")
        title_label.setStyleSheet("color: #ffffff; font-size: 24px; font-weight: bold; margin-top: 10px;")
        logo_layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Alt başlık
        subtitle_label = QLabel("Video indirmek için YouTube bağlantısını yapıştırın")
        subtitle_label.setStyleSheet("color: #b0b0b0; font-size: 14px;")
        logo_layout.addWidget(subtitle_label, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.url_wrapper_layout.addWidget(self.logo_container)
        
        # URL girişi container'ı
        self.url_container = QWidget()  # self ile erişilebilir yap
        self.url_container.setStyleSheet("""
            QWidget {
                background-color: #363636;
                border-radius: 8px;
                padding: 20px;
            }
        """)
        url_layout = QHBoxLayout(self.url_container)
        url_layout.setContentsMargins(10, 10, 10, 10)
        url_layout.setSpacing(8)
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("YouTube URL'sini buraya yapıştırın")
        self.url_input.setMinimumHeight(45)
        self.url_input.setStyleSheet("""
            QLineEdit {
                background-color: #2b2b2b;
                color: #ffffff;
                border: 2px solid #1e1e1e;
                border-radius: 4px;
                padding: 5px 15px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #0d47a1;
            }
        """)
        
        self.paste_button = QPushButton("Yapıştır")
        self.paste_button.setMinimumHeight(45)
        self.paste_button.setFixedWidth(120)
        self.paste_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.paste_button.clicked.connect(self.paste_url)
        self.paste_button.setStyleSheet("""
            QPushButton {
                background-color: #0d47a1;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 15px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
            QPushButton:pressed {
                background-color: #0a3d8f;
            }
        """)
        
        url_layout.addWidget(self.url_input)
        url_layout.addWidget(self.paste_button)
        self.url_wrapper_layout.addWidget(self.url_container)
        
        main_layout.addWidget(self.url_wrapper)  # Burayı düzelttik
        layout.addWidget(main_container)
        
        # Video bilgileri container'ı (başlangıçta gizli)
        self.video_info_container = QWidget()
        video_info_layout = QVBoxLayout(self.video_info_container)
        video_info_layout.setContentsMargins(0, 0, 0, 0)
        video_info_layout.setSpacing(15)
        
        # Thumbnail ve bilgiler için container
        info_row = QWidget()
        info_row_layout = QHBoxLayout(info_row)
        info_row_layout.setContentsMargins(0, 0, 0, 0)
        info_row_layout.setSpacing(15)
        
        # Sol panel (thumbnail)
        left_panel = QWidget()
        left_panel.setFixedWidth(320)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(320, 180)
        self.thumbnail_label.setStyleSheet("border: 1px solid #3a3a3a; border-radius: 4px;")
        self.thumbnail_label.setScaledContents(True)
        
        self.download_thumbnail_btn = QPushButton("Thumbnail'i İndir")
        self.download_thumbnail_btn.setFixedWidth(320)
        self.download_thumbnail_btn.setStyleSheet("""
            QPushButton {
                background-color: #125ac9;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 15px;
                font-size: 12px;
                margin-top: 0;
                z-index: 1000;
            }
            QPushButton:hover {
                background-color: #4f4f4f;
            }
        """)
        self.download_thumbnail_btn.clicked.connect(self.download_thumbnail)
        
        left_layout.addWidget(self.thumbnail_label)
        left_layout.addWidget(self.download_thumbnail_btn)
        info_row_layout.addWidget(left_panel)
        
        # Sağ panel (video bilgileri)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)  # Bilgiler arası boşluğu artırdım
        
        # Video bilgileri
        self.title_label = QLabel()
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 15px;
                font-weight: bold;
                padding: 8px 12px;
                background-color: #2d2d2d;
                border-radius: 6px;
                border: 1px solid #3d3d3d;
            }
        """)

        self.channel_label = QLabel()
        self.channel_label.setStyleSheet("""
            QLabel {
                color: #8721fc;
                font-size: 14px;
                font-weight: bold;
                padding: 8px 12px;
                background-color: #2d2d2d;
                border-radius: 6px;
                border: 1px solid #3d3d3d;
            }
        """)

        # İstatistik bilgileri için container
        stats_container = QWidget()
        stats_layout = QVBoxLayout(stats_container)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(8)

        # İstatistik etiketleri için ortak stil
        stats_style = """
            QLabel {
                color: #e0e0e0;
                font-size: 13px;
                padding: 8px 12px;
                background-color: #2d2d2d;
                border-radius: 6px;
                border: 1px solid #3d3d3d;
            }
            QLabel:hover {
                background-color: #333333;
                border: 1px solid #4d4d4d;
            }
        """

        # İstatistik bilgileri
        self.duration_label = QLabel()
        self.duration_label.setStyleSheet(stats_style)
        
        self.views_label = QLabel()
        self.views_label.setStyleSheet(stats_style)
        
        self.upload_date_label = QLabel()
        self.upload_date_label.setStyleSheet(stats_style)

        # Bilgileri düzene ekle
        right_layout.addWidget(self.title_label)
        right_layout.addWidget(self.channel_label)
        
        # İstatistikleri container'a ekle
        stats_layout.addWidget(self.duration_label)
        stats_layout.addWidget(self.views_label)
        stats_layout.addWidget(self.upload_date_label)
        
        # İstatistik container'ını ana düzene ekle
        right_layout.addWidget(stats_container)
        right_layout.addStretch()
        info_row_layout.addWidget(right_panel)
        
        # Önce thumbnail ve bilgileri ekle
        video_info_layout.addWidget(info_row)
        
        # Format tablosu
        format_container = QWidget()
        format_layout = QVBoxLayout(format_container)
        format_layout.setContentsMargins(0, 0, 0, 0)
        format_layout.setSpacing(10)
        
        # Format tablosu
        self.format_table = QTableWidget()
        self.format_table.setMinimumHeight(150)
        self.format_table.setColumnCount(5)
        self.format_table.setHorizontalHeaderLabels([
            "Kalite", "Format", "Çözünürlük", "FPS", "Boyut"
        ])
        
        # Tablo sütunlarının genişliklerini ayarla
        header = self.format_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Kalite
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Format
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)           # Çözünürlük
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # FPS
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Boyut
        
        # Dikey header'ı gizle
        self.format_table.verticalHeader().setVisible(False)
        
        # Tablo özelliklerini ayarla
        self.format_table.setShowGrid(True)
        self.format_table.setGridStyle(Qt.PenStyle.SolidLine)
        self.format_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.format_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        
        format_layout.addWidget(self.format_table)
        video_info_layout.addWidget(format_container)
        
        # İndirme butonları en sona
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(10)
        
        self.download_button = QPushButton("Video İndir")
        self.mp3_download_button = QPushButton("MP3 Olarak İndir")
        
        # Butonlara tıklama olaylarını bağla
        self.download_button.clicked.connect(lambda: self.start_download(mp3_only=False))
        self.mp3_download_button.clicked.connect(lambda: self.start_download(mp3_only=True))
        
        for btn in [self.download_button, self.mp3_download_button]:
            btn.setMinimumHeight(36)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #0d47a1;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 5px 20px;
                    font-size: 13px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #1565c0;
                }
            """)
        
        button_layout.addWidget(self.download_button)
        button_layout.addWidget(self.mp3_download_button)
        video_info_layout.addWidget(button_container)
        
        # İlerleme çubuğu ve durum
        self.progress_container = QWidget()
        progress_layout = QVBoxLayout(self.progress_container)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(5)
        
        # Progress bar ve iptal butonu
        progress_row = QWidget()
        progress_row_layout = QHBoxLayout(progress_row)
        progress_row_layout.setContentsMargins(0, 0, 0, 0)
        progress_row_layout.setSpacing(10)
        
        self.download_progress = QProgressBar()
        self.download_progress.setMinimumHeight(25)
        
        self.cancel_button = QPushButton("⏹️ İptal")
        self.cancel_button.setEnabled(False)
        self.cancel_button.setFixedWidth(100)
        self.cancel_button.clicked.connect(self.cancel_download)
        
        progress_row_layout.addWidget(self.download_progress)
        progress_row_layout.addWidget(self.cancel_button)
        progress_layout.addWidget(progress_row)
        
        # İndirme detayları
        details_row = QWidget()
        details_layout = QHBoxLayout(details_row)
        details_layout.setContentsMargins(0, 0, 0, 0)
        
        self.download_speed = QLabel("Hız: -- MB/s")
        self.download_eta = QLabel("Kalan Süre: --:--:--")
        self.download_size = QLabel("Boyut: -- MB / -- MB")
        self.download_percent = QLabel("İlerleme: %0")
        
        for label in [self.download_speed, self.download_eta, self.download_size, self.download_percent]:
            label.setStyleSheet("color: #b0b0b0; font-size: 12px;")
            details_layout.addWidget(label)
        
        progress_layout.addWidget(details_row)
        video_info_layout.addWidget(self.progress_container)
        
        layout.addWidget(self.video_info_container)
        self.video_info_container.hide()  # Başlangıçta gizle
        
        layout.addStretch()
        
        # Bağlantılar
        self.format_table.itemSelectionChanged.connect(self.update_download_button)
        self.url_input.textChanged.connect(self.on_url_changed)

    def update_download_button(self):
        """Format seçimine göre indirme butonunu güncelle"""
        selected_items = self.format_table.selectedItems()
        self.download_button.setEnabled(len(selected_items) > 0)

    def setup_web_video_tab(self):
        layout = QVBoxLayout(self.web_video_tab)
        
        # URL girişi
        url_group = QGroupBox("Video URL")
        url_layout = QHBoxLayout(url_group)
        self.web_url_input = QLineEdit()
        self.web_url_input.setPlaceholderText("Video URL'sini yapıştırın")
        self.web_paste_button = QPushButton("Yapıştır")
        url_layout.addWidget(self.web_url_input)
        url_layout.addWidget(self.web_paste_button)
        layout.addWidget(url_group)
        
        # İndirme butonu
        self.web_download_button = QPushButton("İndir")
        layout.addWidget(self.web_download_button)
        
        # İlerleme çubuğu
        self.web_progress = QProgressBar()
        layout.addWidget(self.web_progress)
        
        layout.addStretch()

    def setup_codec_tab(self):
        layout = QVBoxLayout(self.codec_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Dosya seçimi container'ı
        file_container = QWidget()
        file_container.setStyleSheet("""
            QWidget {
                background-color: #363636;
                border-radius: 8px;
                padding: 5px;
            }
        """)
        file_layout = QVBoxLayout(file_container)
        file_layout.setSpacing(10)
        
        # Başlık ve açıklama
        header_container = QWidget()
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # Logo
        logo_label = QLabel()
        logo_label.setPixmap(QPixmap("icon.ico").scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        header_layout.addWidget(logo_label)
        
        # Başlık ve açıklama için dikey layout
        text_container = QWidget()
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        
        title_label = QLabel("Video Codec Düzenleyici")
        title_label.setStyleSheet("color: #ffffff; font-size: 16px; font-weight: bold;")
        text_layout.addWidget(title_label)
        
        info_label = QLabel("Düzenlemek istediğiniz video dosyasını seçin")
        info_label.setStyleSheet("color: #b0b0b0; font-size: 12px;")
        text_layout.addWidget(info_label)
        
        header_layout.addWidget(text_container, 1)
        file_layout.addWidget(header_container)
        
        # Dosya seçimi ve gözat butonu
        input_container = QWidget()
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)
        
        self.codec_file_input = QLineEdit()
        self.codec_file_input.setPlaceholderText("Video dosyası seçin")
        self.codec_file_input.setMinimumHeight(36)
        self.codec_file_input.setStyleSheet("""
            QLineEdit {
                background-color: #2b2b2b;
                color: #ffffff;
                border: 2px solid #1e1e1e;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 2px solid #0d47a1;
            }
        """)
        
        self.codec_browse_button = QPushButton("Gözat")
        self.codec_browse_button.setMinimumHeight(36)
        self.codec_browse_button.setFixedWidth(100)
        self.codec_browse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.codec_browse_button.clicked.connect(self.browse_codec_file)
        self.codec_browse_button.setStyleSheet("""
            QPushButton {
                background-color: #0d47a1;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
            QPushButton:pressed {
                background-color: #0a3d8f;
            }
        """)
        
        input_layout.addWidget(self.codec_file_input)
        input_layout.addWidget(self.codec_browse_button)
        file_layout.addWidget(input_container)
        
        layout.addWidget(file_container)
        
        # Codec ayarları container'ı
        codec_container = QWidget()
        codec_container.setStyleSheet("""
            QWidget {
                background-color: #2d2d2d;
                border-radius: 6px;
                border: 1px solid #3d3d3d;
            }
        """)
        codec_layout = QVBoxLayout(codec_container)
        codec_layout.setSpacing(15)
        
        # Video codec seçimi
        video_codec_container = QWidget()
        video_codec_layout = QHBoxLayout(video_codec_container)
        video_codec_layout.setContentsMargins(10, 10, 10, 10)
        
        video_codec_label = QLabel("🎥  Video Codec:")
        video_codec_label.setStyleSheet("color: #ffffff; font-size: 13px;")
        self.video_codec_combo = QComboBox()
        self.video_codec_combo.addItems(["H.264", "H.265", "VP9", "AV1"])
        self.video_codec_combo.setStyleSheet("""
            QComboBox {
                background-color: #363636;
                color: #ffffff;
                border: 1px solid #4a4a4a;
                border-radius: 4px;
                padding: 5px 10px;
                min-height: 30px;
                font-size: 13px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: url(down_arrow.png);
                width: 12px;
                height: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: #363636;
                color: #ffffff;
                selection-background-color: #0d47a1;
                selection-color: #ffffff;
            }
        """)
        
        video_codec_layout.addWidget(video_codec_label)
        video_codec_layout.addWidget(self.video_codec_combo)
        codec_layout.addWidget(video_codec_container)
        
        # Ses codec seçimi
        audio_codec_container = QWidget()
        audio_codec_layout = QHBoxLayout(audio_codec_container)
        audio_codec_layout.setContentsMargins(10, 10, 10, 10)
        
        audio_codec_label = QLabel("🔊  Ses Codec:")
        audio_codec_label.setStyleSheet("color: #ffffff; font-size: 13px;")
        self.audio_codec_combo = QComboBox()
        self.audio_codec_combo.addItems(["AAC", "MP3", "Opus", "FLAC"])
        self.audio_codec_combo.setStyleSheet("""
            QComboBox {
                background-color: #363636;
                color: #ffffff;
                border: 1px solid #4a4a4a;
                border-radius: 4px;
                padding: 5px 10px;
                min-height: 30px;
                font-size: 13px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: url(down_arrow.png);
                width: 12px;
                height: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: #363636;
                color: #ffffff;
                selection-background-color: #0d47a1;
                selection-color: #ffffff;
            }
        """)
        
        audio_codec_layout.addWidget(audio_codec_label)
        audio_codec_layout.addWidget(self.audio_codec_combo)
        codec_layout.addWidget(audio_codec_container)
        
        # Hızlandırma modunu seçme (CPU / NVIDIA / AMD / AMD APU)
        acceleration_container = QWidget()
        acceleration_layout = QHBoxLayout(acceleration_container)
        acceleration_layout.setContentsMargins(10, 10, 10, 10)
        acceleration_label = QLabel("Hızlandırma Modu:")
        acceleration_label.setStyleSheet("color: #ffffff; font-size: 13px;")
        self.acceleration_mode_combo = QComboBox()
        self.acceleration_mode_combo.setStyleSheet("""
            QComboBox {
                background-color: #363636;
                color: #ffffff;
                border: 1px solid #4a4a4a;
                border-radius: 4px;
                padding: 5px 10px;
                min-height: 30px;
                font-size: 13px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #363636;
                color: #ffffff;
                selection-background-color: #0d47a1;
                selection-color: #ffffff;
            }
        """)
        # Populate the acceleration combobox with available options.
        modes = self.get_available_acceleration_modes()
        self.acceleration_mode_combo.addItems(modes)
        acceleration_layout.addWidget(acceleration_label)
        acceleration_layout.addWidget(self.acceleration_mode_combo)
        codec_layout.addWidget(acceleration_container)
        
        layout.addWidget(codec_container)
        
        # Dönüştür butonu
        self.convert_button = QPushButton("🔄  Dönüştür")
        self.convert_button.setMinimumHeight(36)
        self.convert_button.clicked.connect(self.start_conversion)
        self.convert_button.setStyleSheet("""
            QPushButton {
                background-color: #0d47a1;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 15px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
            QPushButton:pressed {
                background-color: #0a3d8f;
            }
        """)
        layout.addWidget(self.convert_button)
        
        # İlerleme durumu container'ı
        progress_container = QWidget()
        progress_container.setStyleSheet("""
            QWidget {
                background-color: #2d2d2d;
                border-radius: 6px;
                border: 1px solid #3d3d3d;
            }
        """)
        progress_layout = QVBoxLayout(progress_container)
        progress_layout.setSpacing(10)
        
        # Progress bar
        self.codec_progress = QProgressBar()
        self.codec_progress.setMinimumHeight(25)
        self.codec_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                text-align: center;
                color: white;
                background-color: #2b2b2b;
            }
            QProgressBar::chunk {
                background-color: #0d47a1;
                border-radius: 3px;
            }
        """)
        progress_layout.addWidget(self.codec_progress)
        
        # Dönüştürme detayları
        details_container = QWidget()
        details_layout = QHBoxLayout(details_container)
        details_layout.setSpacing(20)
        
        self.conversion_speed = QLabel("⚡ Hız: -- fps")
        self.conversion_time = QLabel("⏱️ Süre: --:--:--")
        self.conversion_eta = QLabel("🕒 Kalan: --:--:--")
        self.conversion_percent = QLabel("📊 İlerleme: %0")
        
        for label in [self.conversion_speed, self.conversion_time, 
                     self.conversion_eta, self.conversion_percent]:
            label.setStyleSheet("""
                QLabel {
                    color: #b0b0b0;
                    font-size: 12px;
                    padding: 5px;
                }
            """)
            details_layout.addWidget(label)
        
        progress_layout.addWidget(details_container)
        layout.addWidget(progress_container)
        
        layout.addStretch()

    def setup_history_tab(self):
        layout = QVBoxLayout(self.history_tab)
        
        # İndirme geçmişi tablosu
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels([
            "Tarih", "Dosya Adı", "URL", "Durum", "Dosya Yolu"
        ])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        
        # Tablo seçim ayarları
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)  # Satır seçimi
        self.history_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)     # Tek satır seçimi
        
        # Alternatif satır renkleri
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setStyleSheet("""
            QTableWidget {
                selection-background-color: #0078D7;  /* Windows mavi rengi */
                selection-color: white;
                alternate-background-color: #f5f5f5;  /* Açık gri */
            }
        """)
        
        # Dosya yolu sütununu gizle (ama veriyi tut)
        self.history_table.setColumnHidden(4, True)
        
        layout.addWidget(self.history_table)
        
        # Butonlar için widget
        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        
        # Seçili dosyayı aç butonu
        self.open_file_button = QPushButton("Dosyayı Aç")
        self.open_file_button.clicked.connect(self.open_selected_file)
        self.open_file_button.setEnabled(False)
        
        # Klasörde göster butonu
        self.show_in_folder_button = QPushButton("Klasörde Göster")
        self.show_in_folder_button.clicked.connect(self.show_in_folder)
        self.show_in_folder_button.setEnabled(False)
        
        # Temizle butonu
        self.clear_history_button = QPushButton("Geçmişi Temizle")
        self.clear_history_button.clicked.connect(self.clear_history)
        
        button_layout.addWidget(self.open_file_button)
        button_layout.addWidget(self.show_in_folder_button)
        button_layout.addWidget(self.clear_history_button)
        
        layout.addWidget(button_widget)
        
        # Tablo seçim değişikliğini izle
        self.history_table.itemSelectionChanged.connect(self.update_history_buttons)
        
        # Veritabanını oluştur/yükle
        self.init_database()
        
        # Geçmişi yükle
        self.load_history()

    def init_database(self):
        """Veritabanını oluştur"""
        try:
            db_path = os.path.join(self.get_app_data_dir(), 'download_history.db')
            self.conn = sqlite3.connect(db_path)
            cursor = self.conn.cursor()
            
            # İndirme geçmişi tablosunu oluştur
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    filename TEXT,
                    url TEXT,
                    status TEXT,
                    filepath TEXT
                )
            ''')
            
            self.conn.commit()
            
        except Exception as e:
            QMessageBox.warning(self, "Veritabanı Hatası", f"Veritabanı oluşturulamadı: {str(e)}")

    def add_to_history(self, filename, url, status, filepath):
        """İndirme geçmişine yeni kayıt ekle"""
        try:
            cursor = self.conn.cursor()
            date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            cursor.execute('''
                INSERT INTO downloads (date, filename, url, status, filepath)
                VALUES (?, ?, ?, ?, ?)
            ''', (date, filename, url, status, filepath))
            
            self.conn.commit()
            self.load_history()  # Tabloyu güncelle
            
        except Exception as e:
            print(f"Geçmişe ekleme hatası: {str(e)}")

    def load_history(self):
        """Geçmişi tabloya yükle"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT date, filename, url, status, filepath FROM downloads ORDER BY date DESC')
            downloads = cursor.fetchall()
            
            self.history_table.setRowCount(0)
            for row_data in downloads:
                row = self.history_table.rowCount()
                self.history_table.insertRow(row)
                
                for column, data in enumerate(row_data):
                    item = QTableWidgetItem(str(data))
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # Düzenlemeyi engelle
                    self.history_table.setItem(row, column, item)
            
        except Exception as e:
            print(f"Geçmiş yükleme hatası: {str(e)}")

    def clear_history(self):
        """Geçmişi temizle"""
        reply = QMessageBox.question(
            self,
            'Geçmişi Temizle',
            'Tüm indirme geçmişini silmek istediğinizden emin misiniz?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                cursor = self.conn.cursor()
                cursor.execute('DELETE FROM downloads')
                self.conn.commit()
                self.load_history()
                
            except Exception as e:
                QMessageBox.warning(self, "Hata", f"Geçmiş temizlenemedi: {str(e)}")

    def update_history_buttons(self):
        """Seçili öğeye göre butonları güncelle"""
        selected_rows = self.history_table.selectionModel().selectedRows()
        has_selection = len(selected_rows) > 0
        
        if has_selection:
            row = selected_rows[0].row()
            filepath = self.history_table.item(row, 4).text()  # Dosya yolu sütunu
            file_exists = os.path.exists(filepath)
            
            self.open_file_button.setEnabled(file_exists)
            self.show_in_folder_button.setEnabled(file_exists)
            
            if not file_exists:
                # Dosya bulunamadıysa durumu güncelle
                self.history_table.item(row, 3).setText("Dosya Bulunamadı")
                self.history_table.item(row, 3).setForeground(QColor("#f44336"))  # Kırmızı
        else:
            self.open_file_button.setEnabled(False)
            self.show_in_folder_button.setEnabled(False)

    def open_selected_file(self):
        """Seçili dosyayı aç"""
        selected_rows = self.history_table.selectionModel().selectedRows()
        if selected_rows:
            row = selected_rows[0].row()
            filepath = self.history_table.item(row, 4).text()
            if os.path.exists(filepath):
                try:
                    if os.name == 'nt':  # Windows
                        os.startfile(filepath)
                    elif os.name == 'darwin':  # macOS
                        subprocess.run(['open', filepath])
                    else:  # Linux
                        subprocess.run(['xdg-open', filepath])
                except Exception as e:
                    QMessageBox.warning(self, "Hata", f"Dosya açılırken hata oluştu: {str(e)}")
            else:
                QMessageBox.warning(self, "Hata", "Dosya bulunamadı!")

    def show_in_folder(self):
        """Seçili dosyayı klasörde göster"""
        selected_rows = self.history_table.selectionModel().selectedRows()
        if selected_rows:
            row = selected_rows[0].row()
            filepath = self.history_table.item(row, 4).text()
            if os.path.exists(filepath):
                try:
                    if os.name == 'nt':  # Windows
                        subprocess.run(['explorer', '/select,', filepath])
                    elif os.name == 'darwin':  # macOS
                        subprocess.run(['open', '-R', filepath])
                    else:  # Linux
                        subprocess.run(['xdg-open', os.path.dirname(filepath)])
                except Exception as e:
                    QMessageBox.warning(self, "Hata", f"Klasör açılırken hata oluştu: {str(e)}")
            else:
                QMessageBox.warning(self, "Hata", "Dosya bulunamadı!")

    def paste_url(self):
        """Panodaki URL'yi yapıştır"""
        try:
            # Önce butonu güncelle
            self.paste_button.setText("Alınıyor...")
            self.paste_button.setEnabled(False)
            QApplication.processEvents()  # UI'ın hemen güncellenmesini sağla
            
            # Sonra URL'yi yapıştır
            clipboard = QApplication.clipboard()
            self.url_input.setText(clipboard.text())
            
            # Butonu eski haline getir
            self.paste_button.setText("Yapıştır")
            self.paste_button.setEnabled(True)
            
        except Exception as e:
            QMessageBox.warning(self, "Hata", f"Pano verisi alınamadı: {str(e)}")
            self.paste_button.setText("Yapıştır")
            self.paste_button.setEnabled(True)

    def on_url_changed(self):
        """URL değiştiğinde video bilgilerini güncelle"""
        url = self.url_input.text().strip()
        if url:
            try:
                # URL container'ını kompakt moda geçir
                self.url_wrapper.setStyleSheet("""
                    QWidget {
                        margin: 0;
                        padding: 0;
                    }
                """)
                self.url_wrapper_layout.setContentsMargins(0, 10, 0, 10)  # Üst ve alt boşluğu azalt
                self.logo_container.hide()  # Logo ve başlıkları gizle
                self.url_container.setStyleSheet("""
                    QWidget {
                        background-color: #363636;
                        border-radius: 4px;
                        padding: 8px;
                        margin: 0;
                    }
                """)
                self.url_input.setMinimumHeight(36)  # Input boyutunu küçült
                self.paste_button.setMinimumHeight(36)  # Buton boyutunu küçült
                
                # Butonu güncelle
                self.paste_button.setText("Veri Alınıyor...")
                self.paste_button.setEnabled(False)
                self.fetch_video_info(url)
            except Exception as e:
                # Hata durumunda ana sayfa görünümüne geri dön
                self.reset_url_view()
                QMessageBox.warning(self, "Hata", str(e))
        else:
            self.reset_url_view()

    def reset_url_view(self):
        """URL görünümünü ana sayfa haline getir"""
        self.url_wrapper.setStyleSheet("")
        self.url_wrapper_layout.setContentsMargins(0, 50, 0, 50)  # Normal boşlukları geri yükle
        self.logo_container.show()  # Logo ve başlıkları göster
        self.url_container.setStyleSheet("""
            QWidget {
                background-color: #363636;
                border-radius: 8px;
                padding: 20px;
            }
        """)
        self.url_input.setMinimumHeight(45)  # Input boyutunu normale döndür
        self.paste_button.setMinimumHeight(45)  # Buton boyutunu normale döndür
        self.paste_button.setText("Yapıştır")
        self.paste_button.setEnabled(True)
        self.video_info_container.hide()

    def fetch_video_info(self, url):
        """Video bilgilerini al"""
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                self.update_video_info(info)
                
        except Exception as e:
            self.reset_url_view()  # Hata durumunda ana sayfa görünümüne dön
            QMessageBox.warning(self, "Hata", f"Video bilgileri alınamadı: {str(e)}")
        finally:
            self.paste_button.setText("Yapıştır")
            self.paste_button.setEnabled(True)

    def update_video_info(self, info):
        """Video bilgilerini güncelle"""
        try:
            # Video bilgilerini göster
            self.video_info_container.show()
            
            # Thumbnail URL'sini sakla
            self.current_thumbnail_url = info.get('thumbnail')
            
            # Thumbnail
            if self.current_thumbnail_url:
                thumbnail_data = requests.get(self.current_thumbnail_url).content
                pixmap = QPixmap()
                pixmap.loadFromData(thumbnail_data)
                self.thumbnail_label.setPixmap(pixmap)
                self.thumbnail_label.setScaledContents(True)
            
            # Video başlığı
            title = info.get('title', 'Başlık bulunamadı')
            self.title_label.setText(f"📹  {title}")
            self.title_label.setWordWrap(True)
            self.title_label.setMaximumWidth(500)  # Çok uzun başlıkların yayılmasını önler
            self.title_label.setStyleSheet("""
                QLabel {
                    font-size: 14px;
                    font-weight: bold;
                    color: #ffffff;
                    padding: 5px;
                    background-color: #1e1e1e;
                    border-radius: 4px;
                }
            """)
            
            # Kanal adı
            channel = info.get('uploader', 'Kanal bulunamadı')
            self.channel_label.setText(f"👤  {channel}")
            self.channel_label.setStyleSheet("""
                QLabel {
                    font-weight: bold;
                    color: #8721fc;
                    font-size: 14px;
                    padding: 2px;
                    background-color: #2d2d2d;
                    border-radius: 6px;
                    border: 1px solid #3d3d3d;
                }
            """)
            
            # Video süresi
            duration = info.get('duration')
            if duration:
                hours = duration // 3600
                minutes = (duration % 3600) // 60
                seconds = duration % 60
                if hours > 0:
                    duration_str = f"{hours}:{minutes:02d}:{seconds:02d}"
                else:
                    duration_str = f"{minutes:02d}:{seconds:02d}"
                self.duration_label.setText(f"⏱️  Süre: {duration_str}")
            else:
                self.duration_label.setText("⏱️  Süre: Bilinmiyor")
            self.duration_label.setStyleSheet("""
                QLabel {
                    color: #e0e0e0;
                    font-size: 13px;
                    padding: 3px;
                    background-color: #2d2d2d;
                    border-radius: 6px;
                    border: 1px solid #3d3d3d;
                }
            """)
            
            # Görüntülenme sayısı
            views = info.get('view_count', 0)
            if views >= 1000000:
                views_str = f"{views/1000000:.1f}M"
            elif views >= 1000:
                views_str = f"{views/1000:.1f}K"
            else:
                views_str = str(views)
            self.views_label.setText(f"👁️  Görüntülenme: {views_str}")
            self.views_label.setStyleSheet("""
                QLabel {
                    color: #e0e0e0;
                    font-size: 13px;
                    padding: 3px;
                    background-color: #2d2d2d;
                    border-radius: 6px;
                    border: 1px solid #3d3d3d;
                }
            """)
            
            # Yüklenme tarihi
            upload_date = info.get('upload_date', '')
            if upload_date:
                try:
                    # YYYYMMDD formatını datetime nesnesine çevir
                    date_obj = datetime.strptime(upload_date, '%Y%m%d')
                    # Türkçe ay isimleri
                    turkish_months = {
                        1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan",
                        5: "Mayıs", 6: "Haziran", 7: "Temmuz", 8: "Ağustos",
                        9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
                    }
                    # Formatlanmış tarih
                    formatted_date = f"{date_obj.day} {turkish_months[date_obj.month]} {date_obj.year}"
                    self.upload_date_label.setText(f"📅  Yayınlanma: {formatted_date}")
                except:
                    self.upload_date_label.setText(f"📅  Yayınlanma: Bilinmiyor")
            else:
                self.upload_date_label.setText("📅  Yayınlanma: Bilinmiyor")
            self.upload_date_label.setStyleSheet("""
                QLabel {
                    color: #e0e0e0;
                    font-size: 13px;
                    padding: 3px;
                    background-color: #2d2d2d;
                    border-radius: 6px;
                    border: 1px solid #3d3d3d;
                }
            """)

            # Format tablosunu güncelle
            self.update_format_table(info)
            
        except Exception as e:
            print(f"Video bilgileri güncellenirken hata: {str(e)}")

    def update_format_table(self, info):
        """Format tablosunu güncelle"""
        try:
            self.format_table.setRowCount(0)
            formats = info.get('formats', [])
            
            # Sadece video formatlarını filtrele (ses olup olmadığına bakmadan)
            video_formats = [
                f for f in formats 
                if f.get('vcodec') != 'none' 
                and f.get('height') is not None
            ]
            
            # Formatları çözünürlüğe göre sırala
            video_formats.sort(key=lambda x: (
                x.get('height', 0) or 0,
                x.get('filesize', 0) or 0
            ), reverse=True)
            
            # Daha önce eklenmiş çözünürlükleri takip et
            added_resolutions = set()
            
            for f in video_formats:
                resolution = f.get('height', 0)
                
                # Aynı çözünürlükte başka bir format zaten eklenmişse atla
                if resolution in added_resolutions:
                    continue
                    
                added_resolutions.add(resolution)
                
                row = self.format_table.rowCount()
                self.format_table.insertRow(row)
                
                # Kalite (resolution)
                quality_text = f"{resolution}p"
                if resolution >= 2160:
                    quality_text = "4K"
                elif resolution >= 1440:
                    quality_text = "2K"
                    
                quality_item = QTableWidgetItem(quality_text)
                quality_item.setData(Qt.ItemDataRole.UserRole, f.get('format_id'))
                quality_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # Format
                format_item = QTableWidgetItem(f.get('ext', 'N/A'))
                format_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # Çözünürlük
                width = f.get('width', 'N/A')
                resolution_text = f"{width}x{resolution}" if width != 'N/A' else 'N/A'
                resolution_item = QTableWidgetItem(resolution_text)
                resolution_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # FPS
                fps = f.get('fps', 'N/A')
                fps_item = QTableWidgetItem(f"{fps} FPS" if fps != 'N/A' else 'N/A')
                fps_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # Boyut
                filesize = f.get('filesize', 0)
                if filesize:
                    if filesize > 1024*1024*1024:  # GB
                        size_str = f"{filesize/1024/1024/1024:.1f} GB"
                    else:  # MB
                        size_str = f"{filesize/1024/1024:.1f} MB"
                else:
                    size_str = "N/A"
                size_item = QTableWidgetItem(size_str)
                size_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # Öğeleri tabloya ekle
                self.format_table.setItem(row, 0, quality_item)
                self.format_table.setItem(row, 1, format_item)
                self.format_table.setItem(row, 2, resolution_item)
                self.format_table.setItem(row, 3, fps_item)
                self.format_table.setItem(row, 4, size_item)
                
                # Satır stilini ayarla
                for col in range(5):
                    item = self.format_table.item(row, col)
                    item.setForeground(QColor("#e0e0e0"))
            
            # İlk satırı seç
            if self.format_table.rowCount() > 0:
                self.format_table.selectRow(0)
            
        except Exception as e:
            print(f"Format tablosu güncellenirken hata: {str(e)}")

    def download_thumbnail(self):
        """Thumbnail'i video başlığı ile jpg olarak indir"""
        if hasattr(self, 'current_thumbnail_url'):
            try:
                # Video başlığını al ve geçersiz karakterleri temizle
                video_title = self.title_label.text().replace("📹 ", "")  # Emoji'yi kaldır
                # Dosya adı için geçersiz karakterleri temizle
                invalid_chars = '<>:"/\\|?*'
                for char in invalid_chars:
                    video_title = video_title.replace(char, '')
                
                response = requests.get(self.current_thumbnail_url)
                if response.status_code == 200:
                    # Thumbnail verisini QPixmap'e yükle
                    pixmap = QPixmap()
                    pixmap.loadFromData(response.content)
                    
                    file_path, _ = QFileDialog.getSaveFileName(
                        self,
                        "Thumbnail'i Kaydet",
                        os.path.join(self.download_path, f"{video_title}.jpg"),
                        "JPEG Images (*.jpg)"
                    )
                    
                    if file_path:
                        # JPG olarak kaydet
                        pixmap.save(file_path, "JPG", quality=100)
                        QMessageBox.information(self, "Başarılı", "Thumbnail kaydedildi!")
                else:
                    QMessageBox.warning(self, "Hata", f"Thumbnail indirilemedi! HTTP Kodu: {response.status_code}")
            except Exception as e:
                QMessageBox.warning(self, "Hata", f"Thumbnail indirilemedi: {str(e)}")

    def start_download(self, mp3_only=False):
        try:
            url = self.url_input.text()
            if not url:
                QMessageBox.warning(self, "Uyarı", "Lütfen bir URL girin.")
                return

            download_path = self.folder_input.text() or os.path.expanduser("~/Downloads")
            
            self.download_button.setEnabled(False)
            self.mp3_download_button.setEnabled(False)
            
            # Instead of using postprocessor_args in the options, we download the audio stream in its original format.
            if mp3_only:
                self.mp3_download_button.setText("MP3 İndiriliyor...")
                # Set a flag so later we know to convert manually.
                self.mp3_conversion_mode = True
                ydl_opts = {
                    'format': 'worstaudio/worst',
                    # Download using the original extension (e.g., m4a) first.
                    'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
                    'quiet': True,
                    'no_warnings': True
                }
            else:
                self.mp3_conversion_mode = False
                self.download_button.setText("Video İndiriliyor...")
                selected_items = self.format_table.selectedItems()
                if not selected_items:
                    QMessageBox.warning(self, "Uyarı", "Lütfen bir video formatı seçin.")
                    self.reset_download_state()
                    return
                
                row = selected_items[0].row()
                format_id = self.format_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                
                ydl_opts = {
                    'format': f'{format_id}+bestaudio/best',
                    'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
                    'merge_output_format': 'mkv',
                    'quiet': True,
                    'no_warnings': True,
                    'postprocessors': [{
                        'key': 'FFmpegVideoConvertor',
                        'preferedformat': 'mkv',
                    }, {
                        'key': 'FFmpegVideoRemuxer',
                        'preferedformat': 'mkv',
                    }]
                }

            self.active_download = DownloadThread(url, download_path, ydl_opts)
            self.active_download.progress_signal.connect(self.update_progress)
            self.active_download.error_signal.connect(self.on_download_error)
            self.active_download.finished_signal.connect(self.on_download_complete)
            self.active_download.start()

            self.cancel_button.setEnabled(True)

        except Exception as e:
            self.on_download_error(str(e))

    def update_progress(self, d):
        """İndirme ilerlemesini güncelle"""
        try:
            if d['status'] == 'downloading':
                # Hız hesaplama
                speed = d.get('speed', 0)
                if speed:
                    if speed > 1024*1024:  # MB/s
                        speed_str = f"Hız: {speed/1024/1024:.1f} MB/s"
                    else:  # KB/s
                        speed_str = f"Hız: {speed/1024:.1f} KB/s"
                else:
                    speed_str = "Hız: -- KB/s"
                self.download_speed.setText(speed_str)
                
                # İlerleme yüzdesi
                total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                if total:
                    percent = (downloaded / total) * 100
                    self.download_progress.setValue(int(percent))
                    self.download_percent.setText(f"İlerleme: %{percent:.1f}")
                
                # Boyut bilgisi
                if total:
                    if total > 1024*1024*1024:  # GB
                        size_str = f"Boyut: {downloaded/1024/1024/1024:.1f} GB / {total/1024/1024/1024:.1f} GB"
                    else:  # MB
                        size_str = f"Boyut: {downloaded/1024/1024:.1f} MB / {total/1024/1024:.1f} MB"
                else:
                    if downloaded > 1024*1024*1024:  # GB
                        size_str = f"Boyut: {downloaded/1024/1024/1024:.1f} GB"
                    else:  # MB
                        size_str = f"Boyut: {downloaded/1024/1024:.1f} MB"
                self.download_size.setText(size_str)
                
                # Kalan süre
                try:
                    eta = d.get('eta', None)
                    if eta:
                        if isinstance(eta, str):
                            self.download_eta.setText(f"Kalan Süre: {eta}")
                        else:
                            minutes = int(eta // 60)
                            seconds = int(eta % 60)
                            self.download_eta.setText(f"Kalan Süre: {minutes:02d}:{seconds:02d}")
                    else:
                        self.download_eta.setText("Kalan Süre: --:--")
                except:
                    self.download_eta.setText("Kalan Süre: --:--")

            elif d['status'] == 'finished':
                self.downloaded_file = d['filename']

        except Exception as e:
            print(f"İlerleme güncellenirken hata: {str(e)}")

    def on_download_error(self, error):
        """İndirme hatası olduğunda çağrılır"""
        QMessageBox.critical(self, "İndirme Hatası", str(error))
        self.reset_download_state()

    def on_download_complete(self, downloaded_file):
        """Called once download is complete."""
        try:
            if downloaded_file:
                # If in MP3 conversion mode, convert the downloaded audio
                if hasattr(self, 'mp3_conversion_mode') and self.mp3_conversion_mode:
                    converted_file = self.convert_to_mp3_with_libshine(downloaded_file)
                    if converted_file:
                        final_file = converted_file
                    else:
                        final_file = downloaded_file
                else:
                    final_file = downloaded_file

                self.add_to_history(
                    os.path.basename(final_file),
                    self.url_input.text(),
                    "Tamamlandı",
                    final_file
                )
                QMessageBox.information(self, "Başarılı", "İndirme tamamlandı!")
        except Exception as e:
            print(f"İndirme geçmişi eklenirken hata: {str(e)}")
        finally:
            self.reset_download_state()

    def convert_to_mp3_with_libshine(self, input_file):
        """
        Converts the downloaded audio file to MP3 using FFmpeg with libshine.
        Make sure your FFmpeg build has libshine support.
        """
        import subprocess
        # Remove the original extension and add .mp3
        output_file = f"{os.path.splitext(input_file)[0]}.mp3"
        command = [
            'ffmpeg',
            '-i', input_file,
            '-c:a', 'libshine',  # Use libshine for faster MP3 encoding
            '-b:a', '128k',
            '-y', output_file
        ]
        try:
            subprocess.run(command, check=True)
            return output_file
        except subprocess.CalledProcessError as e:
            QMessageBox.warning(self, "Conversion Error", f"MP3 dönüştürme başarısız: {str(e)}")
            return None

    def reset_download_state(self):
        """İndirme durumunu sıfırla"""
        try:
            if hasattr(self, 'active_download') and self.active_download:
                self.active_download.is_cancelled = True
                self.active_download.quit()
                self.active_download.wait()
                self.active_download = None
            
            # Butonları sıfırla
            self.download_button.setText("Video İndir")
            self.mp3_download_button.setText("MP3 Olarak İndir")
            self.download_button.setEnabled(True)
            self.mp3_download_button.setEnabled(True)
            
            # İlerleme bilgilerini sıfırla
            self.download_progress.setValue(0)
            self.download_speed.setText("Hız: -- MB/s")
            self.download_eta.setText("Kalan Süre: --:--:--")
            self.download_size.setText("Boyut: -- MB / -- MB")
            self.download_percent.setText("İlerleme: %0")
            
        except Exception as e:
            print(f"İndirme durumu sıfırlanırken hata: {str(e)}")

    def get_download_path(self):
        """İndirme yolunu ayarlardan al"""
        return self.folder_input.text() or os.path.expanduser("~/Downloads")

    def browse_download_folder(self):
        """İndirme klasörü seçme dialog'unu aç"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "İndirme Klasörü Seç",
            self.folder_input.text() or os.path.expanduser("~")
        )
        if folder:
            self.folder_input.setText(folder)

    def update_ffmpeg_status(self):
        """FFmpeg durumunu kontrol et ve güncelle"""
        try:
            # FFmpeg'i sistem komutları arasında ara
            result = subprocess.run(['where', 'ffmpeg'], capture_output=True, text=True)
            
            if result.returncode == 0:
                # FFmpeg bulundu
                self.ffmpeg_status.setText("✅  FFmpeg kurulu ve kullanıma hazır")
                self.ffmpeg_status.setStyleSheet("""
                    QLabel {
                        color: #4CAF50;
                        font-size: 13px;
                        padding: 5px;
                    }
                """)
                self.ffmpeg_download_button.hide()
                # YouTube tabindeki banner'ı gizle
                if hasattr(self, 'ffmpeg_warning_banner'):
                    self.ffmpeg_warning_banner.hide()
            else:
                # FFmpeg bulunamadı
                self.ffmpeg_status.setText("❌  FFmpeg kurulu değil")
                self.ffmpeg_status.setStyleSheet("""
                    QLabel {
                        color: #f44336;
                        font-size: 13px;
                        padding: 5px;
                    }
                """)
                self.ffmpeg_download_button.show()
                # YouTube tabindeki banner'ı göster
                if hasattr(self, 'ffmpeg_warning_banner'):
                    self.ffmpeg_warning_banner.show()
            
        except Exception as e:
            # Hata durumunda
            self.ffmpeg_status.setText("❌  FFmpeg durumu kontrol edilemedi")
            self.ffmpeg_status.setStyleSheet("""
                QLabel {
                    color: #f44336;
                    font-size: 13px;
                    padding: 5px;
                }
            """)
            self.ffmpeg_download_button.show()

    def download_ffmpeg(self):
        """FFmpeg'i winget ile indir ve kur"""
        try:
            if os.name != 'nt':
                QMessageBox.warning(self, "Hata", "Bu özellik sadece Windows'ta kullanılabilir.")
                return

            # İndirme başlamadan önce kullanıcıya bilgi ver
            progress_dialog = QDialog(self)
            progress_dialog.setWindowTitle("FFmpeg Kuruluyor")
            progress_dialog.setFixedSize(300, 150)
            progress_dialog.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)
            
            layout = QVBoxLayout(progress_dialog)
            info_label = QLabel("FFmpeg winget ile kuruluyor...")
            layout.addWidget(info_label)
            
            progress_bar = QProgressBar()
            progress_bar.setRange(0, 0)  # Belirsiz ilerleme
            layout.addWidget(progress_bar)
            
            status_label = QLabel("Kurulum başlatılıyor...")
            layout.addWidget(status_label)
            
            progress_dialog.show()
            QApplication.processEvents()

            self.ffmpeg_download_button.setEnabled(False)
            self.ffmpeg_status.setText("FFmpeg kuruluyor...")

            # PowerShell komutunu hazırla
            ps_command = 'Start-Process powershell -ArgumentList "-Command &{winget install --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements}" -Verb RunAs -Wait'
            
            # PowerShell'i çalıştır
            status_label.setText("FFmpeg kuruluyor... Bu işlem birkaç dakika sürebilir.")
            result = subprocess.run(['powershell', '-Command', ps_command], 
                                  capture_output=True, 
                                  text=True)

            if result.returncode == 0:
                progress_dialog.close()
                progress_dialog.deleteLater()
                
                # FFmpeg durumunu güncelle
                self.update_ffmpeg_status()

                # Başarı mesajı
                QMessageBox.information(
                    self, 
                    "Başarılı", 
                    "FFmpeg başarıyla kuruldu. Programı kullanabilirsiniz."
                )
            else:
                raise Exception(f"Winget kurulum hatası: {result.stderr}")

        except Exception as e:
            if 'progress_dialog' in locals():
                progress_dialog.close()
                progress_dialog.deleteLater()
            QMessageBox.warning(self, "Hata", f"FFmpeg kurulurken hata oluştu: {str(e)}")
        finally:
            self.ffmpeg_download_button.setEnabled(True)
            self.update_ffmpeg_status()

    def get_app_data_dir(self):
        """Uygulama veri dizinini al veya oluştur"""
        if os.name == 'nt':  # Windows
            app_data = os.path.join(os.environ['APPDATA'], 'YouTubeDownloader')
        elif os.name == 'darwin':  # macOS
            app_data = os.path.expanduser('~/Library/Application Support/YouTubeDownloader')
        else:  # Linux ve diğerleri
            app_data = os.path.expanduser('~/.config/youtubedownloader')
        
        # Dizin yoksa oluştur
        if not os.path.exists(app_data):
            os.makedirs(app_data)
        
        return app_data

    def get_settings_path(self):
        """Settings.json dosya yolunu al"""
        return os.path.join(self.get_app_data_dir(), 'settings.json')

    def load_settings(self):
        """Ayarları yükle"""
        try:
            settings_path = self.get_settings_path()
            
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                
                self.folder_input.setText(settings.get('download_path', ''))
                
                video_quality = settings.get('video_quality')
                if video_quality:
                    index = self.video_quality_combo.findText(video_quality)
                    if index >= 0:
                        self.video_quality_combo.setCurrentIndex(index)
                    
                audio_quality = settings.get('audio_quality')
                if audio_quality:
                    index = self.audio_quality_combo.findText(audio_quality)
                    if index >= 0:
                        self.audio_quality_combo.setCurrentIndex(index)
                    
        except Exception as e:
            print(f"Ayarlar yüklenirken hata: {str(e)}")

    def save_settings(self):
        """Ayarları kaydet"""
        try:
            settings = {
                'download_path': self.folder_input.text(),
                'video_quality': self.video_quality_combo.currentText(),
                'audio_quality': self.audio_quality_combo.currentText()
            }
            
            settings_path = self.get_settings_path()
            
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
            
            QMessageBox.information(self, "Başarılı", "Ayarlar kaydedildi!")
            
        except Exception as e:
            QMessageBox.warning(self, "Hata", f"Ayarlar kaydedilemedi: {str(e)}")

    def cancel_download(self):
        """İndirmeyi iptal et"""
        if not self.active_download:
            return
        
        try:
            reply = QMessageBox.question(
                self, 
                'İndirmeyi İptal Et',
                'İndirmeyi iptal etmek istediğinizden emin misiniz?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # İndirme klasörünü al
                download_dir = self.folder_input.text() or os.path.expanduser("~/Downloads")
                
                # İndirmeyi iptal et
                self.active_download.is_cancelled = True
                self.active_download.quit()
                self.active_download.wait()
                
                # Part dosyalarını bul ve sil
                try:
                    # İndirme klasöründeki tüm .part dosyalarını kontrol et
                    for filename in os.listdir(download_dir):
                        if filename.endswith(".part"):
                            file_path = os.path.join(download_dir, filename)
                            try:
                                os.remove(file_path)
                                print(f"Part dosyası silindi: {file_path}")
                            except Exception as e:
                                print(f"Dosya silinirken hata: {str(e)}")
                        
                        # .temp ve .ytdl dosyalarını da kontrol et
                        elif filename.endswith((".temp", ".ytdl")):
                            file_path = os.path.join(download_dir, filename)
                            try:
                                os.remove(file_path)
                                print(f"Geçici dosya silindi: {file_path}")
                            except Exception as e:
                                print(f"Dosya silinirken hata: {str(e)}")
                
                except Exception as e:
                    print(f"Dosyalar silinirken hata oluştu: {str(e)}")
                
                self.reset_download_state()
                QMessageBox.information(self, "İptal", "İndirme iptal edildi ve geçici dosyalar temizlendi.")
            
        except Exception as e:
            print(f"İndirme iptal edilirken hata: {str(e)}")
            self.reset_download_state()

    def browse_codec_file(self):
        """Video dosyası seçme dialog'unu aç"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Video Dosyası Seç",
            self.folder_input.text() or os.path.expanduser("~"),
            "Video Dosyaları (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm);;Tüm Dosyalar (*.*)"
        )
        if file_path:
            self.codec_file_input.setText(file_path)

    def detect_gpu(self):
        """
        Detects the type of GPU available:
          - Returns "NVIDIA" if an NVIDIA GPU is detected.
          - Returns "AMD" or "AMD_APU" if an AMD GPU is detected.
          - Otherwise returns "CPU".
        """
        import shutil
        # Check if NVIDIA is available by trying to locate nvidia-smi
        if shutil.which("nvidia-smi"):
            return "NVIDIA"
        
        # For AMD on Windows, use WMIC to inspect video controllers
        if os.name == "nt":
            try:
                output = subprocess.check_output(
                    ["wmic", "path", "win32_VideoController", "get", "Name"],
                    text=True
                )
                if "AMD" in output.upper():
                    # Basic check: if "APU" also appears, assume it's an AMD APU.
                    if "APU" in output.upper():
                        return "AMD_APU"
                    return "AMD"
            except Exception:
                pass
        return "CPU"

    def get_available_acceleration_modes(self):
        """
        Returns a list of available acceleration modes.
        Always includes "CPU".
        If an NVIDIA GPU is available, adds "NVIDIA".
        If an AMD GPU/APU is available (on Windows), adds "AMD" or "AMD APU" accordingly.
        """
        modes = ["CPU"]
        import shutil
        if shutil.which("nvidia-smi"):
            modes.append("NVIDIA")
        if os.name == "nt":  # Windows check for AMD GPU/APU
            try:
                output = subprocess.check_output(
                    ["wmic", "path", "win32_VideoController", "get", "Name"],
                    text=True, stderr=subprocess.DEVNULL
                )
                output_upper = output.upper()
                if "AMD" in output_upper:
                    if "APU" in output_upper:
                        modes.append("AMD APU")
                    else:
                        modes.append("AMD")
            except Exception:
                pass
        return modes

    def start_conversion(self):
        """Codec dönüştürme işlemini başlat"""
        input_file = self.codec_file_input.text()
        if not input_file or not os.path.exists(input_file):
            QMessageBox.warning(self, "Hata", "Lütfen geçerli bir video dosyası seçin.")
            return

        self.convert_button.setText("Dönüştürülüyor...")

        # Dosya adını ve uzantısını ayır
        input_path = os.path.dirname(input_file)
        input_filename = os.path.splitext(os.path.basename(input_file))[0]

        # GPU kullanımına bağlı olarak dosya adına ekleme
        # (In this case we append a "_gpu" suffix if the acceleration mode is not CPU)
        acc_mode = self.acceleration_mode_combo.currentText()
        gpu_suffix = "_gpu" if acc_mode != "CPU" else ""

        new_filename = f"{input_filename}_{self.video_codec_combo.currentText()}_{self.audio_codec_combo.currentText()}{gpu_suffix}"

        # Çıktı formatını belirle (codec'e göre en uygun formatı seç)
        output_format = ".mp4"  # Varsayılan
        if self.video_codec_combo.currentText() == "VP9":
            output_format = ".webm"
        elif self.video_codec_combo.currentText() == "AV1":
            output_format = ".mkv"

        # Önerilen çıktı dosyası yolu
        suggested_output = os.path.join(input_path, new_filename + output_format)

        # Çıktı dosyası için kaydetme dialogu
        output_file, _ = QFileDialog.getSaveFileName(
            self,
            "Dönüştürülen Dosyayı Kaydet",
            suggested_output,
            "Video Dosyaları (*.mp4 *.mkv *.webm)"
        )

        if not output_file:
            self.convert_button.setText("Dönüştür")
            return

        # Codec mapping
        video_codec_map = {
            "H.264": "libx264",
            "H.265": "libx265",
            "VP9": "libvpx-vp9",
            "AV1": "libaom-av1"
        }

        audio_codec_map = {
            "AAC": "aac",
            "MP3": "libmp3lame",
            "Opus": "libopus",
            "FLAC": "flac"
        }

        # Determine video encoder based on selected acceleration mode.
        current_codec = self.video_codec_combo.currentText()
        if acc_mode == "NVIDIA":
            if current_codec == "H.264":
                video_codec = "h264_nvenc"
            elif current_codec == "H.265":
                video_codec = "hevc_nvenc"
            else:
                video_codec = video_codec_map.get(current_codec, "")
        elif acc_mode in ["AMD", "AMD APU"]:
            if current_codec == "H.264":
                video_codec = "h264_amf"
            elif current_codec == "H.265":
                video_codec = "hevc_amf"
            else:
                video_codec = video_codec_map.get(current_codec, "")
        else:  # CPU selected
            video_codec = video_codec_map.get(current_codec, "")

        audio_codec = audio_codec_map.get(self.audio_codec_combo.currentText(), "")

        # Dönüştürme thread'ini başlat
        self.convert_button.setEnabled(False)
        self.conversion_thread = ConversionThread(
            input_file,
            output_file,
            video_codec,
            audio_codec
        )
        self.conversion_thread.progress_signal.connect(self.update_conversion_progress)
        self.conversion_thread.finished_signal.connect(self.conversion_finished)
        self.conversion_thread.error_signal.connect(self.conversion_error)
        self.conversion_thread.start()

    def update_conversion_progress(self, progress_dict):
        """Dönüştürme ilerlemesini güncelle"""
        try:
            # İlerleme çubuğunu güncelle
            self.codec_progress.setValue(int(progress_dict['percent']))
            
            # Detayları güncelle
            self.conversion_speed.setText(f"Hız: {progress_dict['speed']} fps")
            self.conversion_time.setText(f"Süre: {progress_dict['time']}")
            self.conversion_eta.setText(f"Kalan: {progress_dict['eta']}")
            self.conversion_percent.setText(f"İlerleme: %{progress_dict['percent']:.1f}")
            
        except Exception as e:
            print(f"İlerleme güncellenirken hata: {str(e)}")

    def conversion_finished(self):
        """Dönüştürme tamamlandığında çağrılır"""
        QMessageBox.information(self, "Başarılı", "Dönüştürme işlemi tamamlandı!")
        self.convert_button.setEnabled(True)
        self.codec_progress.setValue(0)
        self.convert_button.setText("Dönüştür")

        # Detayları güncelle
        self.conversion_speed.setText(f"Hız: -- fps")
        self.conversion_time.setText(f"Süre: --:--:--")
        self.conversion_eta.setText(f"Kalan: --:--:--")
        self.conversion_percent.setText(f"İlerleme: %0")
        

    def conversion_error(self, error):
        """Dönüştürme hatası olduğunda çağrılır"""
        QMessageBox.critical(self, "Dönüştürme Hatası", str(error))
        self.convert_button.setEnabled(True)
        self.codec_progress.setValue(0)
        self.convert_button.setText("Dönüştür")

        # Detayları güncelle
        self.conversion_speed.setText(f"Hız: -- fps")
        self.conversion_time.setText(f"Süre: --:--:--")
        self.conversion_eta.setText(f"Kalan: --:--:--")
        self.conversion_percent.setText(f"İlerleme: %0")

    def setup_settings_tab(self):
        """Ayarlar sekmesini oluştur"""
        layout = QVBoxLayout(self.settings_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Başlık container'ı
        header_container = QWidget()
        header_container.setStyleSheet("""
            QWidget {
                background-color: #363636;
                border-radius: 8px;
                padding: 5px;
            }
        """)
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # Logo
        logo_label = QLabel()
        logo_label.setPixmap(QPixmap("icon.ico").scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        header_layout.addWidget(logo_label)
        
        # Başlık ve açıklama
        text_container = QWidget()
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        
        title_label = QLabel("Uygulama Ayarları")
        title_label.setStyleSheet("color: #ffffff; font-size: 16px; font-weight: bold;")
        text_layout.addWidget(title_label)
        
        info_label = QLabel("İndirme klasörünü ve FFmpeg durumunu yönetin")
        info_label.setStyleSheet("color: #b0b0b0; font-size: 12px;")
        text_layout.addWidget(info_label)
        
        header_layout.addWidget(text_container, 1)
        layout.addWidget(header_container)

        # İndirme klasörü grubu
        folder_group = QGroupBox("📥  İndirme Klasörü")
        folder_group.setStyleSheet("""
            QGroupBox {
                background-color: #2d2d2d;
                border-radius: 6px;
                border: 1px solid #3d3d3d;
                color: #ffffff;
                font-size: 14px;
                font-weight: bold;
                padding: 15px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        folder_layout = QHBoxLayout(folder_group)
        
        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText("İndirme klasörünü seçin")
        self.folder_input.setStyleSheet("""
            QLineEdit {
                background-color: #363636;
                color: #ffffff;
                border: 1px solid #4a4a4a;
                border-radius: 4px;
                padding: 8px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #0d47a1;
            }
        """)
        
        self.folder_browse_button = QPushButton("Gözat")
        self.folder_browse_button.clicked.connect(self.browse_download_folder)
        self.folder_browse_button.setStyleSheet("""
            QPushButton {
                background-color: #0d47a1;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 15px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
        """)
        
        folder_layout.addWidget(self.folder_input)
        folder_layout.addWidget(self.folder_browse_button)
        layout.addWidget(folder_group)
        
        # FFmpeg Durumu grubu
        ffmpeg_group = QGroupBox("🎬  FFmpeg Durumu")
        ffmpeg_group.setStyleSheet("""
            QGroupBox {
                background-color: #2d2d2d;
                border-radius: 6px;
                border: 1px solid #3d3d3d;
                color: #ffffff;
                font-size: 14px;
                font-weight: bold;
                padding: 15px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        ffmpeg_layout = QVBoxLayout(ffmpeg_group)
        
        self.ffmpeg_status = QLabel("FFmpeg durumu kontrol ediliyor...")
        self.ffmpeg_status.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 13px;
                padding: 5px;
            }
        """)
        ffmpeg_layout.addWidget(self.ffmpeg_status)
        
        self.ffmpeg_download_button = QPushButton("FFmpeg İndir ve Kur")
        self.ffmpeg_download_button.clicked.connect(self.download_ffmpeg)
        self.ffmpeg_download_button.hide()
        self.ffmpeg_download_button.setStyleSheet("""
            QPushButton {
                background-color: #0d47a1;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 15px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
        """)
        ffmpeg_layout.addWidget(self.ffmpeg_download_button)
        
        layout.addWidget(ffmpeg_group)
        
        # Kalite ayarları grubu
        quality_group = QGroupBox("⚙️  Varsayılan Kalite Ayarları")
        quality_group.setStyleSheet("""
            QGroupBox {
                background-color: #2d2d2d;
                border-radius: 6px;
                border: 1px solid #3d3d3d;
                color: #ffffff;
                font-size: 14px;
                font-weight: bold;
                padding: 15px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        quality_layout = QVBoxLayout(quality_group)
        
        # Video kalitesi
        video_quality_container = QWidget()
        video_quality_layout = QHBoxLayout(video_quality_container)
        video_quality_layout.setContentsMargins(0, 0, 0, 0)
        
        video_quality_label = QLabel("🎥  Video Kalitesi:")
        video_quality_label.setStyleSheet("color: #ffffff; font-size: 13px;")
        self.video_quality_combo = QComboBox()
        self.video_quality_combo.addItems(["En Yüksek", "1080p", "720p", "480p", "360p"])
        self.video_quality_combo.setStyleSheet("""
            QComboBox {
                background-color: #363636;
                color: #ffffff;
                border: 1px solid #4a4a4a;
                border-radius: 4px;
                padding: 5px;
                min-width: 150px;
                font-size: 13px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #363636;
                color: #ffffff;
                selection-background-color: #0d47a1;
            }
        """)
        
        video_quality_layout.addWidget(video_quality_label)
        video_quality_layout.addWidget(self.video_quality_combo)
        video_quality_layout.addStretch()
        quality_layout.addWidget(video_quality_container)
        
        # Ses kalitesi
        audio_quality_container = QWidget()
        audio_quality_layout = QHBoxLayout(audio_quality_container)
        audio_quality_layout.setContentsMargins(0, 0, 0, 0)
        
        audio_quality_label = QLabel("🔊  Ses Kalitesi:")
        audio_quality_label.setStyleSheet("color: #ffffff; font-size: 13px;")
        self.audio_quality_combo = QComboBox()
        self.audio_quality_combo.addItems(["En Yüksek", "320k", "256k", "192k", "128k", "96k"])
        self.audio_quality_combo.setStyleSheet("""
            QComboBox {
                background-color: #363636;
                color: #ffffff;
                border: 1px solid #4a4a4a;
                border-radius: 4px;
                padding: 5px;
                min-width: 150px;
                font-size: 13px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #363636;
                color: #ffffff;
                selection-background-color: #0d47a1;
            }
        """)
        
        audio_quality_layout.addWidget(audio_quality_label)
        audio_quality_layout.addWidget(self.audio_quality_combo)
        audio_quality_layout.addStretch()
        quality_layout.addWidget(audio_quality_container)
        
        layout.addWidget(quality_group)
        
        # Kaydet butonu
        save_button = QPushButton("💾  Ayarları Kaydet")
        save_button.clicked.connect(self.save_settings)
        save_button.setStyleSheet("""
            QPushButton {
                background-color: #0d47a1;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 12px;
                font-size: 13px;
                font-weight: bold;
                margin-top: 10px;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
        """)
        layout.addWidget(save_button)
        
        layout.addStretch()
        
        # FFmpeg durumunu hemen kontrol et
        self.update_ffmpeg_status()  # Bu satırı ekledik

# İndirme Thread sınıfı
class DownloadThread(QThread):
    progress_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(str)

    def __init__(self, url, download_path, ydl_opts):
        super().__init__()
        self.url = url
        self.download_path = download_path
        self.ydl_opts = ydl_opts.copy()
        self.is_cancelled = False
        self.downloaded_file = None
        self.current_ydl = None
        self.normal_speed = 0  # Normal indirme hızı için

    def run(self):
        try:
            def progress_hook(d):
                if self.is_cancelled:
                    raise Exception("İndirme iptal edildi")
                if d['status'] == 'downloading':
                    
                    self.progress_signal.emit(d)
                elif d['status'] == 'finished':
                    self.downloaded_file = d['filename']

            self.ydl_opts.update({
                'progress_hooks': [progress_hook],
            })

            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                self.current_ydl = ydl
                ydl.download([self.url])
                
            if self.downloaded_file and not self.is_cancelled:
                self.finished_signal.emit(self.downloaded_file)

        except Exception as e:
            if not self.is_cancelled:
                self.error_signal.emit(str(e))

    def cancel(self):
        """İndirmeyi iptal et"""
        self.is_cancelled = True
        if self.current_ydl:
            self.current_ydl.params['ratelimit'] = None
        self.quit()
        self.wait()

# Dönüştürme Thread sınıfı
class ConversionThread(QThread):
    progress_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)
    
    def __init__(self, input_file, output_file, video_codec, audio_codec, extra_params=None):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.video_codec = video_codec
        self.audio_codec = audio_codec
        self.extra_params = extra_params or []
        self.is_running = True
        
    def run(self):
        try:
            # FFmpeg komut parametrelerini oluştur
            command = [
                'ffmpeg', '-i', self.input_file,
                '-c:v', self.video_codec,
                '-c:a', self.audio_codec
            ]
            
            # Ek parametreleri ekle
            command.extend(self.extra_params)
            
            # Çıktı dosyasını ekle
            command.extend(['-y', self.output_file])
            
            # FFmpeg işlemini başlat
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # İlerlemeyi takip et
            duration = None
            pattern = re.compile(r"Duration: (\d{2}):(\d{2}):(\d{2})\.\d{2}")
            time_pattern = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})\.\d{2}")
            fps_pattern = re.compile(r"fps=\s*(\d+)")
            
            for line in process.stderr:
                if not self.is_running:
                    process.terminate()
                    break
                    
                if duration is None:
                    match = pattern.search(line)
                    if match:
                        h, m, s = map(int, match.groups())
                        duration = h * 3600 + m * 60 + s
                
                time_match = time_pattern.search(line)
                fps_match = fps_pattern.search(line)
                
                if time_match and duration:
                    h, m, s = map(int, time_match.groups())
                    current_time = h * 3600 + m * 60 + s
                    progress = (current_time / duration) * 100
                    
                    fps = fps_match.group(1) if fps_match else "0"
                    eta = duration - current_time
                    eta_str = str(timedelta(seconds=eta))
                    
                    self.progress_signal.emit({
                        'percent': progress,
                        'time': f"{h:02d}:{m:02d}:{s:02d}",
                        'speed': fps,
                        'eta': eta_str
                    })
            
            if process.wait() == 0 and self.is_running:
                self.finished_signal.emit()
            else:
                raise Exception("Dönüştürme işlemi başarısız oldu.")
                
        except Exception as e:
            self.error_signal.emit(str(e))

class DownloadManager:
    def __init__(self):
        self.active_downloads = []
        self.download_queue = []
        self.download_history = []
        self.max_concurrent_downloads = 2

    def add_download(self, url, download_path, options=None):
        with self._lock:
            download_thread = DownloadThread(url, download_path, options)
            if len(self.active_downloads) < self.max_concurrent_downloads:
                self._start_download(download_thread)
            else:
                self.download_queue.append(download_thread)

    def _start_download(self, download_thread):
        self.active_downloads.append(download_thread)
        download_thread.finished_signal.connect(lambda: self._on_download_finished(download_thread))
        download_thread.start()

    def _on_download_finished(self, download_thread):
        with self._lock:
            if download_thread in self.active_downloads:
                self.active_downloads.remove(download_thread)
                
                # Sıradaki indirmeyi başlat
                if self.download_queue:
                    next_download = self.download_queue.pop(0)
                    self._start_download(next_download)

    def cancel_all(self):
        with self._lock:
            for download in self.active_downloads:
                download.cancel()
            self.download_queue.clear()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = VideoDownloader()
    window.show()
    sys.exit(app.exec())
