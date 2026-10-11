# ADÜ Randevu Takip ve Rezervasyon Botu

Aydın Adnan Menderes Üniversitesi (ADÜ) online randevu sisteminde boş kontenjan bulunduğunda kullanıcıları Telegram üzerinden bilgilendiren ve otomatik randevu alabilen Telegram botu.

## Özellikler

- Merkezi Tarama Havuzu: Birden fazla kullanıcının ortak bölümleri için tek istek atarak sunucu yükünü ve ban riskini azaltır.
- Otomatik Rezervasyon (Sniper): Boş slot açıldığında onay beklemeden doğrudan randevu oluşturur.
- Filtreleme: Belirli gün aralıkları (7, 15, 30 gün) ve saat dilimleri (Sabah, Öğle) bazında arama.
- Takvim Entegrasyonu: Randevu onayında .ics takvim dosyası ve Google Takvim bağlantısı iletimi.
- Çoklu Profil: Farklı hastalar için ayrı kimlik ve telefon bilgisi tanımlama.
- Bölüm Takibi: Hastaneye ait 52 uzmanlık alanı arasından seçim yapabilme.
- Gece Modu (DND): Belirlenen saatlerde sessiz bildirim iletimi.
- Güvenlik: T.C. Kimlik, doğum tarihi ve telefon bilgileri veritabanında PBKDF2 + CTR + HMAC-SHA256 ile şifrelenir. SQLite WAL modu kullanılır.

## Gereksinimler

- Python 3.9+
- uv veya pip

## Kurulum ve Çalıştırma

1. Ortam değişkenlerini yapılandırın:

```bash
cp .env.example .env
```

`.env` dosyasındaki alanlar:
- `TELEGRAM_TOKEN`: Telegram bot belirteci.
- `ADMIN_CHAT_ID`: Yönetici Telegram chat ID.
- `LOG_LEVEL`: Log seviyesi (varsayılan: INFO).
- `ENCRYPTION_KEY`: (Opsiyonel) Veri şifreleme anahtarı. Tanımlanmazsa otomatik üretilir.
- `PROXY_URL`: (Opsiyonel) HTTP veya SOCKS5 proxy adresi.

2. Bağımlılıkları yükleyin ve botu başlatın:

```bash
uv sync
uv run bot.py
```

veya standart pip ile:

```bash
pip install -r requirements.txt
python bot.py
```

3. Testleri çalıştırın:

```bash
python -m unittest test_handlers.py
```

## Proje Yapısı

- `bot.py`: Uygulama giriş noktası ve tarayıcı başlatıcı.
- `handlers/`: Komutlar, mesaj sihirbazları, bildirimler, callback yönlendiricisi ve arka plan tarama motoru.
- `scraper.py`: Hastane randevu sistemi sorgulama ve rezervasyon istemcisi.
- `crypto.py`: Kişisel veriler için at-rest şifreleme modülü.
- `calendar_util.py`: iCalendar (.ics) ve Google Takvim bağlantı üreticisi.
- `db.py`: SQLite veritabanı işlemleri ve sistem metrikleri.
- `keyboards.py`: Telegram inline klavye ve sayfalama bileşenleri.
- `config.py`: Konfigürasyon, hastane bölüm listesi ve loglama ayarları.
- `test_handlers.py`: Birim test paketi.
