# ADÜ Hastane Randevu Takip ve Otomatik Rezervasyon Botu

Bu proje, Aydın Adnan Menderes Üniversitesi (ADÜ) online randevu sisteminde boş slot bulunduğunda kullanıcıları Telegram üzerinden anında bilgilendiren ve tek tıkla rezervasyon yapılmasını sağlayan bir Telegram botudur.

## Özellikler

* Çoklu Profil Yönetimi: Kendiniz veya yakınlarınız için ayrı T.C. Kimlik No, doğum tarihi ve telefon bilgileri barındıran profiller tanımlayabilirsiniz.
* Dinamik Bölüm Takibi: Tanımladığınız her profil için ayrı uzmanlık alanlarını (Kardiyoloji, Göz Hastalıkları vb.) takip listesine alabilirsiniz.
* Arka Plan Sorgulama: Belirlenen zaman aralıklarında (varsayılan 15 dakika) hastane sistemini otomatik olarak sorgular.
* Tek Tuşla Rezervasyon: Boş randevu slotu bulunduğunda gelen Telegram mesajındaki butona tıklayarak anında randevu kaydı gerçekleştirebilirsiniz.
* Master Admin Modeli: Bot sadece Master Admin tarafından üretilen tek kullanımlık davet kodlarına sahip yetkili kullanıcılar tarafından kullanılabilir.
* Güvenli Yetki Yönetimi: Master Admin panelinden aktif kullanıcıların yetkileri anında iptal edilebilir (revoke). Yetkisi iptal edilen kullanıcının verileri veritabanından kalıcı olarak temizlenir.

## Güvenlik ve Mimari

* SQL Injection Koruması: Veritabanındaki tüm işlemlerde SQLite parametreli sorguları kullanılarak SQL Injection riskleri tamamen engellenmiştir.
* TOCTOU Engelleme: Davet kodlarının aynı anda birden fazla kişi tarafından kullanılmasını (race condition) önlemek amacıyla SQLite üzerinde atomik güncelleme mantığı uygulanmıştır.
* Kriptografik Rastgelelik: Davet kodları Python `secrets` modülü ile kriptografik olarak güvenli şekilde üretilir.
* Yetki Denetimi: Tüm callback ve komut tetikleyicilerinde Master Admin ve normal kullanıcı yetkileri her adımda bağımsız olarak doğrulanır.

## Gereksinimler

Projenin yerelinizde veya sunucuda çalışması için aşağıdaki bileşenlerin yüklü olması gerekir:

* Python >= 3.9
* uv veya pip
* Docker ve Docker Compose (opsiyonel)

## Yerel Kurulum ve Çalıştırma

### 1. Depoyu Klonlayın ve Proje Dizinine Gidin

```bash
git clone <depo-adresi>
cd adu
```

### 2. Çevre Değişkenlerini Yapılandırın

`.env.example` dosyasını `.env` olarak kopyalayın ve gerekli alanları doldurun:

```bash
cp .env.example .env
```

`.env` dosyasındaki değişkenler:

* `TELEGRAM_BOT_TOKEN`: Telegram BotFather'dan aldığınız bot belirteci.
* `ADMIN_CHAT_ID`: Master Admin olarak tanımlanacak kullanıcının Telegram chat ID'si.
* `LOG_LEVEL`: Uygulamanın log seviyesi (DEBUG, INFO, WARNING, ERROR).

### 3. Sanal Ortam Oluşturun ve Bağımlılıkları Yükleyin

`uv` kullanarak sanal ortamı saniyeler içinde oluşturup bağımlılıkları senkronize edebilirsiniz:

```bash
uv venv
uv sync
```

### 4. Botu Çalıştırın

```bash
uv run bot.py
```

## Docker ile Kurulum

### 1. Docker Compose ile Başlatın

```bash
docker compose up -d --build
```

### 2. Logları Takip Edin

```bash
docker compose logs -f
```

## Proje Yapısı

* `bot.py`: Bot uygulamasının giriş noktası, Telegram Application kurulumu ve sinyal yöneticileri.
* `handlers.py`: Komutlar, mesaj yöneticileri, sihirbazlar, callback işlemleri ve arka plan tarama görevleri.
* `db.py`: Veritabanı şeması, SQLite bağlantı yönetimi, CRUD işlemleri ve atomik davet kodu Claim mantığı.
* `scraper.py`: Hastane randevu portalından veri çekme (scraping) ve rezervasyon yapma modülü.
* `keyboards.py`: Dinamik Telegram butonları ve arayüz bileşenleri.
* `config.py`: Loglama altyapısı, çevre değişkenleri ve sistem sabitleri.
