# ADU Hastane Randevu Takip ve Otomatik Rezervasyon Botu

Bu proje, Aydin Adnan Menderes Universitesi (ADU) online randevu sisteminde bos slot bulundugunda kullanicilari Telegram uzerinden aninda bilgilendiren ve tek tikla rezervasyon yapilmasini saglayan ozel bir Telegram botudur.

## Ozellikler

* Coklu Profil Yonetimi: Kendiniz veya yakinlariniz icin ayri T.C. Kimlik No, dogum tarihi ve telefon bilgileri barindiran profiller tanimlayabilirsiniz.
* Dinamik Bolum Takibi: Tanimladiginiz her profil icin ayri uzmanlik alanlarini (Kardiyoloji, Goz Hastaliklari vb.) takip listesine alabilirsiniz.
* Arka Plan Sorgulama: Belirlenen zaman araliklarinda (varsayilan 15 dakika) hastane sistemini otomatik olarak sorgular.
* Tek Tusla Rezervasyon: Bos randevu slotu bulundugunda gelen Telegram mesajindaki butona tiklayarak aninda randevu kaydi gerceklestirebilirsiniz.
* Master Admin Modeli: Bot sadece Master Admin tarafindan uretilen tek kullanimlik davet kodlarina sahip yetkili kullanicilar tarafindan kullanilabilir.
* Guvenli Yetki Yonetimi: Master Admin panelinden aktif kullanicilarin yetkileri aninda iptal edilebilir (revoke). Yetkisi iptal edilen kullanicinin verileri veritabanindan kalici olarak temizlenir.

## Guvenlik ve Mimari

* SQL Injection Korumasi: Veritabanindaki tum islemlerde SQLite parametreli sorgulari kullanilarak SQL Injection riskleri tamamen engellenmistir.
* TOCTOU Engelleme: Davet kodlarinin ayni anda birden fazla kisi tarafindan kullanilmasini (race condition) onlemek amaciyla SQLite uzerinde atomik guncelleme mantigi uygulanmistir.
* Kriptografik Rastgelelik: Davet kodlari Python `secrets` modulu ile kriptografik olarak guvenli sekilde uretilir.
* Yetki Denetimi: Tum callback ve komut tetikleyicilerinde Master Admin ve normal kullanici yetkileri her adimda bagimsiz olarak dogrulanir.

## Gereksinimler

Projenin yerelinizde veya sunucuda calismasi icin asagidaki bilesenlerin yuklu olmasi gerekir:

* Python >= 3.9
* uv (Modern ve hizli paket yoneticisi) veya pip
* Docker ve Docker Compose (Opsiyonel - Sunucu kurulumu icin)

## Yerel Kurulum ve Calistirma

Projede paket yonetimi icin Astral tarafindan gelistirilen `uv` kullanilmaktadir.

### 1. Depoyu Klonlayin ve Proje Dizinine Gidin

```bash
git clone <depo-adresi>
cd adu
```

### 2. Cevre Degiskenlerini Yapilandirin

`.env.example` dosyasini `.env` olarak kopyalayin ve gerekli alanlari doldurun:

```bash
cp .env.example .env
```

`.env` dosyasindaki degiskenler:

* `TELEGRAM_BOT_TOKEN`: Telegram BotFather'dan aldiginiz bot belirteci.
* `ADMIN_CHAT_ID`: Master Admin olarak tanimlanacak kullanicinin Telegram chat ID'si.
* `LOG_LEVEL`: Uygulamanin log seviyesi (DEBUG, INFO, WARNING, ERROR).

### 3. Sanal Ortam Olusturun ve Bagimliliklari Yukleyin

`uv` kullanarak sanal ortami saniyeler icinde olusturup bagimliliklari senkronize edebilirsiniz:

```bash
uv venv
uv sync
```

### 4. Botu Calistirin

```bash
uv run bot.py
```

## Docker ile Kurulum (Sunucu Yonetimi)

Proje, sunucularda kolayca calistirilabilmesi icin Dockerfile ve Docker Compose destegiyle birlikte gelir. Docker imaj derleme asamasinda `uv` kullanilarak derleme sureleri optimize edilmistir.

### 1. Docker Compose ile Baslatin

```bash
docker compose up -d --build
```

Bu komut botu arka planda baslatir, veritabanini (`adu_bot.db`) ve log dosyalarini (`adu_bot.log`) ana makinede kalici (persistent) hale getirir.

### 2. Loglari Takip Edin

```bash
docker compose logs -f
```

## Proje Yapisi

* `bot.py`: Bot uygulamasinin giris noktasi, Telegram Application kurulumu ve sinyal yoneticileri.
* `handlers.py`: Komutlar, mesaj yoneticileri, sihirbazlar, callback islemleri ve arka plan tarama gorevleri.
* `db.py`: Veritabani semasi, SQLite baglanti yonetimi, CRUD islemleri ve atomik davet kodu Claim mantigi.
* `scraper.py`: Hastane randevu portalindan veri cekme (scraping) ve rezervasyon yapma modulu.
* `keyboards.py`: Dinamik Telegram butonlari ve arayuz bilesenleri.
* `config.py`: Loglama altyapisi, cevre degiskenleri ve sistem sabitleri.
* `pyproject.toml` ve `uv.lock`: Proje bagimliliklari ve kilitli paket surumleri (`uv` uyumlu).
