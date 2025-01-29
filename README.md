<<<<<<< HEAD
# 🎮 YouTube Video Downloader by ConsolAktif

A **modern and stylish** application that allows you to download videos and audio from YouTube and other platforms! 🚀

![Screenshot](screenshot.png) <!-- If available, you can add a screenshot here -->

## 📌 Features
👉 Quickly downloads YouTube videos and audio files.  
👉 Offers various format and quality options.  
👉 Has a user-friendly, sleek, and modern interface.  
👉 Can convert video formats (H.264, H.265, VP9, AV1).  
👉 **Completely free and open-source!** 🎉

## 🛠️ Requirements
To run this application, you need the following dependencies:

- Python 3.9 or later
- `pip install -r requirements.txt`
- FFmpeg (Can be downloaded from within the program if necessary)

## 🚀 Installation and Usage

1. **Install dependencies:**
   ```sh
   pip install -r requirements.txt
   ```
2. **Run the application:**
   ```sh
   python main.py
   ```

## 🛠️ Creating an .exe File with PyInstaller

If you want to create a standalone `.exe` file for the application:

1. Install PyInstaller:
   ```sh
   pip install pyinstaller
   ```
2. Run the following command to create the `.exe` file:
   ```sh
   pyinstaller --noconsole --onefile --icon=icon.ico --name="YouTube Video Downloader by ConsolAktif" main.py
   ```
   **Explanation:**
   - `--noconsole`: Prevents the command window from opening.
   - `--onefile`: Creates a single `.exe` file.
   - `--icon=icon.ico`: Adds a custom icon.
   - `--name="YouTube Video Downloader by ConsolAktif"`: Sets the name of the `.exe` file.

3. The generated `.exe` file will be located in the `dist` folder.

---

## 🐝 Contribute
Would you like to contribute to the project? You can create a pull request or open an issue. ✨

## 📚 License
This project is licensed under the **MIT License**.

---

**If you encounter any errors, please let us know.** 📩  
🎥🎶 Enjoy using it!

=======
# YouTube Downloader by ConsolAktif

## Açıklama

YouTube Downloader, kullanıcı dostu bir arayüz sunarak YouTube videolarını hızlı ve kolay bir şekilde indirmenize olanak tanır. Videoları hem MP4 hem de MP3 formatında indirmenizi sağlar. Ayrıca altyazı desteği, toplu indirme, hız limiti belirleme gibi gelişmiş özellikler sunar.

## Özellikler

- **Video ve Ses İndirme**: Videoları MP4 formatında, ses dosyalarını ise MP3 formatında indirebilirsiniz.
- **Kalite Seçenekleri**: Video ve ses dosyaları için farklı kalite seçenekleri mevcuttur.
- **Altyazı Desteği**: Videolarla birlikte altyazıları da indirebilirsiniz.
- **Hız Limiti**: İndirme hızını sınırlayarak bant genişliğinizi kontrol edebilirsiniz.
- **Kullanıcı Dostu Arayüz**: Şık ve minimalist bir arayüzle kolay kullanım.

## Gereksinimler

- Python 3.8+
- PyQt5
- yt-dlp
- imageio-ffmpeg

## Kurulum

1. Gerekli bağımlılıkları yükleyin:
   ```bash
   pip install -r requirements.txt
Uygulamayı çalıştırın:
python main.py
Kullanım
İndirmek istediğiniz YouTube URL'sini girin veya toplu indirme için birden fazla URL'yi yapıştırın.
Format (MP4/MP3) ve kalite seçeneklerini belirleyin.
İndir düğmesine tıklayın.
İndirilen dosyayı belirtilen klasörde bulabilirsiniz.

Geliştirici
Bu proje MuratGuler tarafından geliştirilmiştir.

Lisans
Bu proje MIT Lisansı ile lisanslanmıştır. Daha fazla bilgi için LICENSE dosyasına bakabilirsiniz.
>>>>>>> fc87a0402d123dd79bef33afab468843288daeb8
