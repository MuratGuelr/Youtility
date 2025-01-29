import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QTabWidget,
                            QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                            QPushButton, QComboBox, QProgressBar, QMessageBox,
                            QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
                            QGroupBox, QSpinBox, QCheckBox)
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

class VideoDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Video Downloader by ConsolAktif")

        # İkonu ayarla
        self.setWindowIcon(QIcon("icon.ico"))  
        self.active_download = None
        self.download_path = os.path.expanduser("~/Downloads")
        self.setup_ui_style()
        self.init_ui()
        self.download_manager = DownloadManager()
        self.load_settings()  # Ayarları yükle

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
        self.setMinimumSize(830, 720)
        
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
        self.tabs.addTab(self.codec_tab, "Video Codec Düzenleme")
        self.tabs.addTab(self.settings_tab, "Ayarlar")

        # Tab içeriklerini oluştur
        self.setup_youtube_tab()
        self.setup_web_video_tab()
        self.setup_codec_tab()
        self.setup_history_tab()
        self.setup_settings_tab()

    def setup_youtube_tab(self):
        layout = QVBoxLayout(self.youtube_tab)
        
        # URL girişi grubu
        url_group = QGroupBox("Video URL")
        url_layout = QHBoxLayout(url_group)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("YouTube video URL'sini yapıştırın")
        self.paste_button = QPushButton("Yapıştır")
        self.paste_button.clicked.connect(self.paste_url)
        url_layout.addWidget(self.url_input)
        url_layout.addWidget(self.paste_button)
        layout.addWidget(url_group)

        # Video bilgileri grubu
        self.video_info_group = QGroupBox("Video Bilgileri")
        self.video_info_group.hide()
        video_info_layout = QHBoxLayout(self.video_info_group)
        
        # Sol panel (thumbnail ve temel bilgiler)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Thumbnail container
        thumbnail_container = QWidget()
        thumbnail_layout = QVBoxLayout(thumbnail_container)
        thumbnail_layout.setContentsMargins(0, 0, 0, 0)
        
        # Thumbnail
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(320, 180)
        self.thumbnail_label.setScaledContents(True)
        self.thumbnail_label.setStyleSheet("border: 1px solid #3a3a3a;")
        
        # Thumbnail indirme butonu
        self.download_thumbnail_btn = QPushButton("Thumbnail'i İndir")
        self.download_thumbnail_btn.clicked.connect(self.download_thumbnail)
        
        thumbnail_layout.addWidget(self.thumbnail_label)
        thumbnail_layout.addWidget(self.download_thumbnail_btn)
        left_layout.addWidget(thumbnail_container)
        
        # Video bilgileri
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        
        self.title_label = QLabel()
        self.channel_label = QLabel()
        self.duration_label = QLabel()
        self.views_label = QLabel()
        self.upload_date_label = QLabel()
        
        for label in [self.title_label, self.channel_label, self.duration_label, 
                     self.views_label, self.upload_date_label]:
            info_layout.addWidget(label)
        
        left_layout.addWidget(info_widget)
        video_info_layout.addWidget(left_panel)

        # Sağ panel (format seçenekleri)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Format tablosu
        self.format_table = QTableWidget()
        self.format_table.setColumnCount(5)
        self.format_table.setHorizontalHeaderLabels([
            "Kalite", "Format", "Çözünürlük", "FPS", "Boyut"
        ])
        
        # Tablo özelliklerini ayarla
        self.format_table.setShowGrid(True)
        self.format_table.setAlternatingRowColors(False)
        self.format_table.verticalHeader().setVisible(False)
        self.format_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.format_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        
        # Sütun genişliklerini ayarla
        self.format_table.setColumnWidth(0, 80)
        self.format_table.setColumnWidth(1, 70)
        self.format_table.setColumnWidth(2, 100)
        self.format_table.setColumnWidth(3, 60)
        self.format_table.setColumnWidth(4, 80)
        
        # Yatay başlık ayarları
        header = self.format_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        
        right_layout.addWidget(self.format_table)
        
        video_info_layout.addWidget(right_panel)
        layout.addWidget(self.video_info_group)

        # İndirme butonları
        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        
        self.download_button = QPushButton("Video İndir")
        self.mp3_download_button = QPushButton("MP3 Olarak İndir")
        self.download_button.clicked.connect(lambda: self.start_download(False))
        self.mp3_download_button.clicked.connect(lambda: self.start_download(True))
        
        button_layout.addWidget(self.download_button)
        button_layout.addWidget(self.mp3_download_button)
        layout.addWidget(button_widget)

        # İndirme durumu göstergesi
        status_widget = QWidget()
        status_layout = QVBoxLayout(status_widget)
        
        # Progress bar ve iptal butonu için yatay layout
        progress_controls = QHBoxLayout()
        
        # Progress bar
        self.download_progress = QProgressBar()
        progress_controls.addWidget(self.download_progress, stretch=1)
        
        # Sadece iptal butonu
        self.cancel_button = QPushButton("⏹️ İptal")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_download)
        self.cancel_button.setFixedWidth(100)
        
        progress_controls.addWidget(self.cancel_button)
        
        status_layout.addLayout(progress_controls)
        
        # İndirme detayları
        details_widget = QWidget()
        details_layout = QHBoxLayout(details_widget)
        
        self.download_speed = QLabel("Hız: -- MB/s")
        self.download_eta = QLabel("Kalan Süre: --:--:--")
        self.download_size = QLabel("Boyut: -- MB / -- MB")
        self.download_percent = QLabel("İlerleme: %0")
        
        for label in [self.download_speed, self.download_eta, self.download_size, self.download_percent]:
            details_layout.addWidget(label)
        
        status_layout.addWidget(details_widget)
        layout.addWidget(status_widget)

        # Tablo seçim değişikliğini izle
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
        
        # Dosya seçimi
        file_group = QGroupBox("Video Dosyası")
        file_layout = QHBoxLayout(file_group)
        self.codec_file_input = QLineEdit()
        self.codec_file_input.setPlaceholderText("Video dosyası seçin")
        self.codec_browse_button = QPushButton("Gözat")
        self.codec_browse_button.clicked.connect(self.browse_codec_file)
        file_layout.addWidget(self.codec_file_input)
        file_layout.addWidget(self.codec_browse_button)
        layout.addWidget(file_group)
        
        # Codec seçenekleri
        codec_group = QGroupBox("Codec Ayarları")
        codec_layout = QVBoxLayout(codec_group)
        
        # Video codec
        video_codec_layout = QHBoxLayout()
        video_codec_label = QLabel("Video Codec:")
        self.video_codec_combo = QComboBox()
        self.video_codec_combo.addItems(["H.264", "H.265", "VP9", "AV1"])
        video_codec_layout.addWidget(video_codec_label)
        video_codec_layout.addWidget(self.video_codec_combo)
        codec_layout.addLayout(video_codec_layout)
        
        # Ses codec
        audio_codec_layout = QHBoxLayout()
        audio_codec_label = QLabel("Ses Codec:")
        self.audio_codec_combo = QComboBox()
        self.audio_codec_combo.addItems(["AAC", "MP3", "Opus", "FLAC"])
        audio_codec_layout.addWidget(audio_codec_label)
        audio_codec_layout.addWidget(self.audio_codec_combo)
        codec_layout.addLayout(audio_codec_layout)
        
        layout.addWidget(codec_group)
        
        # Dönüştür butonu
        self.convert_button = QPushButton("Dönüştür")
        self.convert_button.clicked.connect(self.start_conversion)
        layout.addWidget(self.convert_button)
        
        # İlerleme durumu
        status_widget = QWidget()
        status_layout = QVBoxLayout(status_widget)
        
        # Progress bar
        self.codec_progress = QProgressBar()
        status_layout.addWidget(self.codec_progress)
        
        # Dönüştürme detayları
        details_widget = QWidget()
        details_layout = QHBoxLayout(details_widget)
        
        self.conversion_speed = QLabel("Hız: -- fps")
        self.conversion_time = QLabel("Süre: --:--:--")
        self.conversion_eta = QLabel("Kalan: --:--:--")
        self.conversion_percent = QLabel("İlerleme: %0")
        
        for label in [self.conversion_speed, self.conversion_time, 
                     self.conversion_eta, self.conversion_percent]:
            details_layout.addWidget(label)
        
        status_layout.addWidget(details_widget)
        layout.addWidget(status_widget)
        
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
            self.paste_button.setText("Veri Alınıyor...")
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
            # Butonu güncelle
            self.paste_button.setText("Veri Alınıyor...")
            self.paste_button.setEnabled(False)
            self.fetch_video_info(url)
        else:
            self.video_info_group.hide()

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
            QMessageBox.warning(self, "Hata", f"Video bilgileri alınamadı: {str(e)}")
        finally:
            # İşlem bittiğinde butonu eski haline getir
            self.paste_button.setText("Yapıştır")
            self.paste_button.setEnabled(True)

    def update_video_info(self, info):
        """Video bilgilerini güncelle"""
        try:
            # Thumbnail
            if info.get('thumbnail'):
                thumbnail_data = requests.get(info['thumbnail']).content
                pixmap = QPixmap()
                pixmap.loadFromData(thumbnail_data)
                self.thumbnail_label.setPixmap(pixmap)
                self.thumbnail_label.setScaledContents(True)
                self.video_info_group.show()
            
            # Video başlığı
            title = info.get('title', 'Başlık bulunamadı')
            self.title_label.setText(f"📹 {title}")
            self.title_label.setWordWrap(True)  # Eğer gerekirse satıra kaydır
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
            self.channel_label.setText(f"👤 Kanal: {channel}")
            self.channel_label.setStyleSheet("""
                QLabel {
                    font-weight: bold;
                    color: #8721fc;
                    font-size: 14px;
                    padding: 2px;
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
                self.duration_label.setText(f"⏱️ Süre: {duration_str}")
            else:
                self.duration_label.setText("⏱️ Süre: Bilinmiyor")
            self.duration_label.setStyleSheet("""
                QLabel {
                    color: #e0e0e0;
                    font-size: 13px;
                    padding: 3px;
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
            self.views_label.setText(f"👁️ Görüntülenme: {views_str}")
            self.views_label.setStyleSheet("""
                QLabel {
                    color: #e0e0e0;
                    font-size: 13px;
                    padding: 3px;
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
                    self.upload_date_label.setText(f"📅 Yayınlanma: {formatted_date}")
                except:
                    self.upload_date_label.setText(f"📅 Yayınlanma: Bilinmiyor")
            else:
                self.upload_date_label.setText("📅 Yayınlanma: Bilinmiyor")
            self.upload_date_label.setStyleSheet("""
                QLabel {
                    color: #e0e0e0;
                    font-size: 13px;
                    padding: 3px;
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
        """Thumbnail'i indir"""
        if hasattr(self, 'current_thumbnail_url'):
            try:
                response = requests.get(self.current_thumbnail_url)
                if response.status_code == 200:
                    file_path, _ = QFileDialog.getSaveFileName(
                        self,
                        "Thumbnail'i Kaydet",
                        os.path.join(self.download_path, "thumbnail.jpg"),
                        "Images (*.jpg *.jpeg *.png)"
                    )
                    if file_path:
                        with open(file_path, 'wb') as f:
                            f.write(response.content)
                        QMessageBox.information(self, "Başarılı", "Thumbnail kaydedildi!")
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
            
            if mp3_only:
                self.mp3_download_button.setText("MP3 İndiriliyor...")
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                    'quiet': True,
                    'no_warnings': True
                }
            else:
                self.download_button.setText("Video İndiriliyor...")
                selected_items = self.format_table.selectedItems()
                if not selected_items:
                    QMessageBox.warning(self, "Uyarı", "Lütfen bir video formatı seçin.")
                    self.reset_download_state()
                    return
                
                row = selected_items[0].row()
                format_id = self.format_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                
                ydl_opts = {
                    'format': f'{format_id}+bestaudio/best',  # Video formatı + en iyi ses
                    'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
                    'merge_output_format': 'mkv',  # MP4 formatında birleştir
                    'quiet': True,
                    'no_warnings': True,
                    'postprocessors': [{
                        'key': 'FFmpegVideoConvertor',
                        'preferedformat': 'mkv',  # MP4 formatına dönüştür
                    }, {
                        # H.264 video codec ve AAC ses codec kullan
                        'key': 'FFmpegVideoRemuxer',
                        'preferedformat': 'mkv',
                    }]
                }

            # İndirme thread'ini başlat
            self.active_download = DownloadThread(url, download_path, ydl_opts)
            self.active_download.progress_signal.connect(self.update_progress)
            self.active_download.error_signal.connect(self.on_download_error)
            self.active_download.finished_signal.connect(self.on_download_complete)
            self.active_download.start()

            # Sadece iptal butonunu aktif et
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
                eta = d.get('eta', None)
                if eta is not None:
                    hours = eta // 3600
                    minutes = (eta % 3600) // 60
                    seconds = eta % 60
                    eta_str = f"Kalan Süre: {hours:02d}:{minutes:02d}:{seconds:02d}"
                else:
                    eta_str = "Kalan Süre: --:--:--"
                self.download_eta.setText(eta_str)

            elif d['status'] == 'finished':
                self.downloaded_file = d['filename']

        except Exception as e:
            print(f"İlerleme güncellenirken hata: {str(e)}")

    def on_download_error(self, error):
        """İndirme hatası olduğunda çağrılır"""
        QMessageBox.critical(self, "İndirme Hatası", str(error))
        self.reset_download_state()

    def on_download_complete(self, downloaded_file):
        """İndirme tamamlandığında çağrılır"""
        try:
            if downloaded_file:
                self.add_to_history(
                    os.path.basename(downloaded_file),
                    self.url_input.text(),
                    "Tamamlandı",
                    downloaded_file
                )
                QMessageBox.information(self, "Başarılı", "İndirme tamamlandı!")
            
        except Exception as e:
            print(f"İndirme geçmişi eklenirken hata: {str(e)}")
        finally:
            self.reset_download_state()

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

    def browse_ffmpeg_path(self):
        """FFmpeg yolu seçme dialog'unu aç"""
        file_filter = "FFmpeg (ffmpeg.exe)" if os.name == 'nt' else "FFmpeg (ffmpeg)"
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "FFmpeg Seç",
            os.path.expanduser("~"),
            file_filter
        )
        if file_path:
            self.ffmpeg_path_input.setText(file_path)
            self.update_ffmpeg_status()

    def update_ffmpeg_status(self):
        """FFmpeg durumunu kontrol et ve göster"""
        try:
            # Önce PATH'de ara
            ffmpeg_path = shutil.which('ffmpeg')
            
            # Eğer kullanıcı özel bir yol belirlediyse onu kullan
            if self.ffmpeg_path_input.text():
                ffmpeg_path = self.ffmpeg_path_input.text()
            
            if ffmpeg_path:
                # FFmpeg versiyonunu al
                result = subprocess.run([ffmpeg_path, '-version'], 
                                     capture_output=True, 
                                     text=True)
                version = result.stdout.split('\n')[0]
                
                # FFmpeg yolunu input'a otomatik ekle
                if not self.ffmpeg_path_input.text():
                    self.ffmpeg_path_input.setText(ffmpeg_path)
                
                self.ffmpeg_status.setText(f"FFmpeg bulundu: {version}\nKonum: {ffmpeg_path}")
                self.ffmpeg_download_button.setEnabled(False)
            else:
                self.ffmpeg_status.setText("FFmpeg bulunamadı!")
                self.ffmpeg_download_button.setEnabled(True)
        except Exception as e:
            self.ffmpeg_status.setText(f"FFmpeg kontrol hatası: {str(e)}")
            self.ffmpeg_download_button.setEnabled(True)

    def download_ffmpeg(self):
        """FFmpeg indirme işlemini başlat"""
        try:
            # İşletim sistemine göre indirme URL'si
            if os.name == 'nt':  # Windows
                url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
                msg = """FFmpeg'i indirmek için tarayıcınız açılacak.
                        İndirdikten sonra zip dosyasını çıkarın ve bin klasöründeki ffmpeg.exe dosyasını seçin."""
            else:  # Linux/MacOS
                msg = """FFmpeg'i terminal üzerinden kurmanız önerilir:
                        
                        Ubuntu/Debian: sudo apt-get install ffmpeg
                        MacOS: brew install ffmpeg
                        """
            
            reply = QMessageBox.information(
                self,
                "FFmpeg İndirme",
                msg,
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Ok and os.name == 'nt':
                webbrowser.open(url)
            
        except Exception as e:
            QMessageBox.warning(self, "Hata", f"FFmpeg indirme hatası: {str(e)}")

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

    def save_settings(self):
        """Ayarları kaydet"""
        try:
            settings = {
                'download_path': self.folder_input.text(),
                'ffmpeg_path': self.ffmpeg_path_input.text(),
                'video_quality': self.video_quality_combo.currentText(),
                'audio_quality': self.audio_quality_combo.currentText()
            }
            
            settings_path = self.get_settings_path()
            
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
            
            QMessageBox.information(self, "Başarılı", "Ayarlar kaydedildi!")
            
        except Exception as e:
            QMessageBox.warning(self, "Hata", f"Ayarlar kaydedilemedi: {str(e)}")

    def load_settings(self):
        """Ayarları yükle"""
        try:
            settings_path = self.get_settings_path()
            
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                
                self.folder_input.setText(settings.get('download_path', ''))
                self.ffmpeg_path_input.setText(settings.get('ffmpeg_path', ''))
                
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
                    
            # FFmpeg durumunu güncelle
            self.update_ffmpeg_status()
                    
        except Exception as e:
            print(f"Ayarlar yüklenirken hata: {str(e)}")

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

    def start_conversion(self):
        """Codec dönüştürme işlemini başlat"""
        input_file = self.codec_file_input.text()
        if not input_file or not os.path.exists(input_file):
            QMessageBox.warning(self, "Hata", "Lütfen geçerli bir video dosyası seçin.")
            return
        
        self.convert_button.setText("Dönüştürülüyor...")
        # Seçilen codec'leri al
        video_codec_name = self.video_codec_combo.currentText().lower().replace(".", "")  # h264, h265, vp9, av1
        audio_codec_name = self.audio_codec_combo.currentText().lower()  # aac, mp3, opus, flac
        
        # Dosya adını ve uzantısını ayır
        input_path = os.path.dirname(input_file)
        input_filename = os.path.splitext(os.path.basename(input_file))[0]
        
        # Yeni dosya adını oluştur
        new_filename = f"{input_filename}_{video_codec_name}_{audio_codec_name}"
        
        # Çıktı formatını belirle (codec'e göre en uygun formatı seç)
        output_format = ".mp4"  # Varsayılan
        if video_codec_name == "vp9":
            output_format = ".webm"
        elif video_codec_name == "av1":
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
        
        # FFmpeg komutunu oluştur
        video_codec = video_codec_map[self.video_codec_combo.currentText()]
        audio_codec = audio_codec_map[self.audio_codec_combo.currentText()]
        
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
        
        # İndirme klasörü
        folder_group = QGroupBox("İndirme Klasörü")
        folder_layout = QHBoxLayout(folder_group)
        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText("İndirme klasörünü seçin")
        self.folder_browse_button = QPushButton("Gözat")
        self.folder_browse_button.clicked.connect(self.browse_download_folder)
        folder_layout.addWidget(self.folder_input)
        folder_layout.addWidget(self.folder_browse_button)
        layout.addWidget(folder_group)
        
        # FFmpeg ayarları
        ffmpeg_group = QGroupBox("FFmpeg Ayarları")
        ffmpeg_layout = QVBoxLayout(ffmpeg_group)
        
        # FFmpeg durum göstergesi
        self.ffmpeg_status = QLabel()
        ffmpeg_layout.addWidget(self.ffmpeg_status)
        
        # FFmpeg yolu seçimi
        ffmpeg_path_layout = QHBoxLayout()
        self.ffmpeg_path_input = QLineEdit()
        self.ffmpeg_path_input.setPlaceholderText("FFmpeg yolu seçin")
        self.ffmpeg_browse_button = QPushButton("Gözat")
        self.ffmpeg_browse_button.clicked.connect(self.browse_ffmpeg_path)
        ffmpeg_path_layout.addWidget(self.ffmpeg_path_input)
        ffmpeg_path_layout.addWidget(self.ffmpeg_browse_button)
        ffmpeg_layout.addLayout(ffmpeg_path_layout)
        
        # FFmpeg indirme butonu
        self.ffmpeg_download_button = QPushButton("FFmpeg İndir")
        self.ffmpeg_download_button.clicked.connect(self.download_ffmpeg)
        ffmpeg_layout.addWidget(self.ffmpeg_download_button)
        
        layout.addWidget(ffmpeg_group)
        
        # Kalite ayarları
        quality_group = QGroupBox("Varsayılan Kalite Ayarları")
        quality_layout = QVBoxLayout(quality_group)
        
        # Video kalitesi
        video_quality_layout = QHBoxLayout()
        video_quality_label = QLabel("Video Kalitesi:")
        self.video_quality_combo = QComboBox()
        self.video_quality_combo.addItems(["En Yüksek", "1080p", "720p", "480p", "360p"])
        video_quality_layout.addWidget(video_quality_label)
        video_quality_layout.addWidget(self.video_quality_combo)
        quality_layout.addLayout(video_quality_layout)
        
        # Ses kalitesi
        audio_quality_layout = QHBoxLayout()
        audio_quality_label = QLabel("Ses Kalitesi:")
        self.audio_quality_combo = QComboBox()
        self.audio_quality_combo.addItems(["En Yüksek", "320k", "256k", "192k", "128k", "96k"])
        audio_quality_layout.addWidget(audio_quality_label)
        audio_quality_layout.addWidget(self.audio_quality_combo)
        quality_layout.addLayout(audio_quality_layout)
        
        layout.addWidget(quality_group)
        
        # Kaydet butonu
        self.save_settings_button = QPushButton("Ayarları Kaydet")
        self.save_settings_button.clicked.connect(self.save_settings)
        layout.addWidget(self.save_settings_button)
        
        layout.addStretch()
        
        # Ayarları yükle
        self.load_settings()
        
        # FFmpeg durumunu kontrol et
        self.update_ffmpeg_status()

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
    error_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, input_file, output_file, video_codec, audio_codec):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.video_codec = video_codec
        self.audio_codec = audio_codec
        self.is_cancelled = False
        self.start_time = None

    def get_video_duration(self):
        """Video süresini al"""
        try:
            cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
                   '-of', 'default=noprint_wrappers=1:nokey=1', self.input_file]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return float(result.stdout.strip())
        except Exception as e:
            print(f"Video süresi alınamadı: {str(e)}")
            return None

    def format_time(self, seconds):
        """Saniyeyi HH:MM:SS formatına çevir"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def run(self):
        try:
            # Video süresini al
            duration = self.get_video_duration()
            if duration is None:
                duration = 0
            
            # Başlangıç zamanını kaydet
            self.start_time = time.time()
            
            # FFmpeg komutu
            cmd = [
                'ffmpeg', '-i', self.input_file,
                '-c:v', self.video_codec,
                '-c:a', self.audio_codec,
                '-y',
                self.output_file
            ]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

            pattern = re.compile(r"frame=\s*(\d+)")
            fps_pattern = re.compile(r"fps=\s*(\d+)")
            time_pattern = re.compile(r"time=\s*(\d+:\d+:\d+\.\d+)")

            while True:
                line = process.stderr.readline()
                if not line and process.poll() is not None:
                    break

                frame_match = pattern.search(line)
                fps_match = fps_pattern.search(line)
                time_match = time_pattern.search(line)

                if frame_match and time_match and fps_match:
                    current_time = time_match.group(1)
                    h, m, s = map(float, re.split('[:]', current_time))
                    current_seconds = h * 3600 + m * 60 + s
                    
                    if duration > 0:
                        progress = (current_seconds / duration) * 100
                        
                        # Kalan süreyi hesapla
                        elapsed_time = time.time() - self.start_time
                        if progress > 0:
                            total_estimated_time = elapsed_time * (100 / progress)
                            remaining_time = total_estimated_time - elapsed_time
                            eta = self.format_time(remaining_time)
                        else:
                            eta = "--:--:--"
                    else:
                        progress = 0
                        eta = "--:--:--"
                        
                    fps = fps_match.group(1)

                    self.progress_signal.emit({
                        'percent': min(100, progress),
                        'speed': fps,
                        'time': current_time,
                        'eta': eta
                    })

            if process.returncode != 0:
                error = process.stderr.read()
                raise Exception(f"FFmpeg hatası: {error}")

            self.finished_signal.emit()

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
