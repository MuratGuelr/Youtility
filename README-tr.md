Hoş geldiniz! **YouTube Downloader**'ımın yeni nesline geçiş yaptık. Bu sürüm **daha hızlı, daha güçlü ve daha akıllı**!

### Yenilikler

- **Daha Hızlı MP3 Dönüştürme:**  
  İki aşamalı süreç: Önce orijinal ses akışı indirilir, ardından FFmpeg ile **libshine** (varsa) kullanılarak MP3'e dönüştürme gerçekleştirilir.  
  _Not: Daha hızlı dönüşüm için FFmpeg'inizin libshine desteğine sahip olması önerilir._
- **GPU Hızlandırmalı Video Dönüştürme:**  
  Mevcutsa NVIDIA veya AMD gibi GPU hızlandırmalı codec’ler kullanılarak video işleme süresi kısaltılır.
- **Gelişmiş Kullanıcı Arayüzü & Hata Yönetimi:**  
  Akıcı animasyonlar, modern ikonlar ve detaylı hata mesajlarıyla geliştirilmiş bir arayüz sunar.
- **Donanım Otomatik Algılama:**  
  Uygulama, sisteminizdeki GPU’yu otomatik olarak algılar ve en uygun ayarları belirler.

### Başlarken

#### Gereksinimler

- **Python 3.6+**
- **FFmpeg:**  
  FFmpeg’in sisteminizde yüklü olduğundan ve PATH’e eklendiğinden emin olun.  
  Libshine desteğini kontrol etmek için:
  ```bash
  ffmpeg -encoders | grep libshine
  ```
- Gerekli Python paketleri:
  - `yt_dlp`
  - `requests`
  - `PyQt5` veya `PyQt6`
  - `sqlite3` (Python ile birlikte gelir)

#### Kurulum

1. **Depoyu Klonlayın:**
   ```bash
   git clone https://github.com/MuratGuelr/youtube_download_by_consolaktif.git
   cd youtube_download_by_consolaktif
   ```
2. **Bağımlılıkları Yükleyin:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Uygulamayı Çalıştırın:**
   ```bash
   python FinalBreakdown.py
   ```

### Özellikler

- **Video İndirme:**  
  Çeşitli formatları destekler ve mevcut GPU hızlandırması sayesinde video dönüştürme süresini kısaltır.
- **MP3 İndirme:**  
  Ses akışı önce orijinal formatında indirilir, ardından libshine kullanılarak MP3’e dönüştürülür.
- **Hata Yönetimi:**  
  Geliştirilmiş hata mesajları ve loglama desteği sayesinde sorunlar kolayca tespit edilir.

### Sorun Giderme

`postprocessor_args` ile ilgili hatalar alırsanız, artık manuel dönüşüm yöntemi devreye girmektedir.  
Daha hızlı dönüşüm için FFmpeg'inizin libshine desteğine sahip olduğundan emin olun.

### Katkıda Bulunma

Katkılarınızı bekliyoruz! Lütfen projeyi fork’layın, değişikliklerinizi yapın ve pull request gönderin.  
Detaylar için [CONTRIBUTING.md](CONTRIBUTING.md) dosyasına bakınız.

### Lisans

Bu proje MIT Lisansı kapsamında lisanslanmıştır. Detaylar için [LICENSE](LICENSE) dosyasına göz atınız.

### İletişim

Sorularınız veya önerileriniz için lütfen GitHub üzerinden bir issue açın veya [Murat Güler](mailto:desmeron134714@gmail.com) ile iletişime geçin.

---

Enjoy the new release – **Faster and Stronger / Daha Hızlı ve Daha Güçlü!** 🎉
