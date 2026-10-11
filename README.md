# ADÜ Hastane Randevu Takip ve Otomatik Rezervasyon Botu

Bu proje, Aydın Adnan Menderes Üniversitesi (ADÜ) online randevu sisteminde boş slot bulunduğunda kullanıcıları Telegram üzerinden anında bilgilendiren, tek tıkla onaylama veya Sniper modu ile tam otomatik rezervasyon yapılmasını sağlayan gelişmiş bir Telegram botudur.

## Özellikler

* **Merkezi Tarama Havuzu (Fan-Out Pub-Sub):** Birden fazla kullanıcı aynı bölümü takip etse bile hastane sunucusuna tek bir optimize istek atılır, elde edilen slotlar ilgili kullanıcılara dağıtılır. Bu sayede sunucu istekleri %80-%90 azalır ve IP ban riski önlenir.
* **Tam Otomatik Rezervasyon (Sniper Modu):** Profil bazlı aktif edilebilen Sniper moduyla, boş slot açıldığı anda Telegram onayı beklemeden milisaniyeler içinde randevu otomatik alınır ve kullanıcıya başarı onayı iletilir.
* **Akıllı Filtreleme (Tarih ve Saat Dilimi):**
  * Tarih Aralığı: Önümüzdeki 7, 15, 30 gün veya tüm tarihler.
  * Saat Dilimi: Tüm gün, Sabah (08:00 - 12:00) veya Öğle (13:00 - 17:00).
* **Takvim Entegrasyonu (.ics ve Google Calendar):** Randevu alındığında doğrudan Telegram mesajında Google Takvim butonu ve Apple/Android yerel takvimleriyle uyumlu `.ics` dosyası iletilir.
* **Çoklu Profil Yönetimi & Düzenleme:** Kendiniz veya yakınlarınız için ayrı profiller oluşturabilir; isim, telefon ve tercihleri dinamik menülerden düzenleyebilirsiniz.
* **Dinamik Bölüm Takibi:** ADÜ bünyesindeki 52 uzmanlık alanından istediklerinizi profil bazında sayfalı menüden işaretleyerek takibe alabilirsiniz.
* **Sessiz Saatler / Gece Modu (DND):** Gece saatlerinde (23:00 - 08:00) gelen randevu bildirimlerini sessiz iletme seçeneği.
* **Master Admin & Teşhis Paneli:**
  * Tek kullanımlık kriptografik davet kodları üretimi ve yetki iptali (revoke).
  * `/stats` ve `/ping` komutları ile canlı hastane yanıt süresi (ms), yakalanan slot sayısı ve veri tabanı metrikleri.

## Güvenlik ve Mimari

* **Kişisel Veri Şifreleme (At-Rest Encryption):** T.C. Kimlik No, Doğum Tarihi ve Telefon numaraları veritabanında düz metin olarak değil, PBKDF2 + CTR modu + HMAC-SHA256 authenticated keystream şifrelemesiyle saklanır.
* **Yüksek Eşzamanlılık (SQLite WAL):** `PRAGMA journal_mode = WAL;` ve `PRAGMA busy_timeout = 5000;` ile veritabanı kilitlenme hataları (database is locked) tamamen engellenmiştir.
* **Tam Asenkron Ağ Motoru (httpx):** Senkron istek bloklamaları yerine native async `httpx.AsyncClient` altyapısı, otomatik retry ve opsiyonel HTTP/SOCKS5 proxy desteği.
* **TOCTOU & SQL Injection Koruması:** Davet kodlarında atomik claim ve sorgularda %100 parametreli SQLite sorguları kullanılır.

## Gereksinimler

* Python >= 3.9
* uv veya pip

## Kurulum ve Çalıştırma

### 1. Çevre Değişkenlerini Yapılandırın

`.env.example` dosyasını `.env` olarak kopyalayın ve gerekli alanları doldurun:

```bash
cp .env.example .env
```

`.env` dosyasındaki değişkenler:
* `TELEGRAM_TOKEN`: Telegram BotFather'dan aldığınız bot belirteci.
* `ADMIN_CHAT_ID`: Master Admin Telegram chat ID'si.
* `LOG_LEVEL`: Uygulama log seviyesi (INFO, DEBUG vb.).
* `ENCRYPTION_KEY`: (Opsiyonel) Kişisel verileri şifreleme anahtarı. Boş bırakılırsa `.secret.key` dosyasına güvenli şekilde otomatik üretilir.
* `PROXY_URL`: (Opsiyonel) HTTP veya SOCKS5 proxy adresi (`http://user:pass@host:port`).

### 2. Bağımlılıkları Yükleyin ve Çalıştırın

```bash
uv sync
uv run bot.py
```

veya standart pip ile:

```bash
pip install -r requirements.txt
python bot.py
```

### 3. Testleri Çalıştırın

```bash
python -m unittest test_handlers.py
```

## Proje Yapısı

* `bot.py`: Uygulama giriş noktası, Telegram bot konfigürasyonu ve merkezi arka plan tarayıcısı kurulumu.
* `handlers/`: Modüler bot işleyicileri paketi (komutlar, mesaj sihirbazları, bildirimler, alan bazlı callback yönlendiricisi ve merkezi tarama döngüsü).
* `scraper.py`: `httpx` tabanlı tam asenkron hastane randevu portali sorgulama ve rezervasyon modülü.
* `crypto.py`: Kişisel veriler için authenticated keystream at-rest şifreleme modülü.
* `calendar_util.py`: iCalendar (`.ics`) dosyası ve Google Calendar URL oluşturucu.
* `db.py`: WAL modunda SQLite veritabanı, CRUD işlemleri, şifreleme katmanı ve sistem metrikleri.
* `keyboards.py`: Dinamik Telegram butonları, filtreleme ve sayfalama bileşenleri.
* `config.py`: Loglama altyapısı, hastane departman listesi ve sabitler.
* `test_handlers.py`: 40 birim testten oluşan kapsamlı otomatik test paketi.
