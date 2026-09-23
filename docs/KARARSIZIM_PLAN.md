# Kararsızım — Proje Planı ve Claude Code Rehberi

> Bu dosya, **Kararsızım** web uygulamasının tüm detaylarını ve Claude Code ile aşama aşama geliştirme talimatlarını içerir.
> Kullanım: Dosyayı proje kök dizinine `CLAUDE.md` adıyla koy (Claude Code otomatik okur) **veya** `docs/PLAN.md` olarak koyup her fazın başında Claude Code'a "`docs/PLAN.md` dosyasını oku ve Faz X'i uygula" de.

---

## 1. Proje Özeti

**Kararsızım**, kullanıcıların kararsız kaldıkları konularda diğer kullanıcılara danışmak için anket açtığı bir platformdur.

- Örnek: *"Bugün sinemaya mı gitsem, restorana mı?"*
- Her ankette **en az 2, en fazla 5** seçenek bulunur.
- **Takip sistemi yok.** Herkes platformdaki tüm anketleri tek bir akışta görür.
- **Üye olmayanlar** anketleri görüntüleyebilir ve oy verebilir.
- **Anket oluşturmak** için üyelik zorunludur.
- Anketlerde oluşturanın **kullanıcı adı** görünür, **e-posta asla görünmez**.

**Hedef:** Önce çalışan, sade bir **prototip**. Karmaşık teknolojilerden kaçınılacak; özellikler sonradan adım adım eklenecek.

---

## 2. Teknoloji Yığını

| Katman | Teknoloji | Not |
|---|---|---|
| Backend | Python 3.12 + Django 5.2 (LTS) | Django'nun yerleşik auth, form, ORM ve template sistemi kullanılacak |
| Veritabanı | Supabase (PostgreSQL) | Supabase **sadece Postgres veritabanı** olarak kullanılır. Supabase Auth / JS SDK **kullanılmaz**; kimlik doğrulama Django'dadır |
| Frontend | Saf HTML + CSS + JavaScript | Framework yok. Django template'leri ile aynı repoda. JS sadece küçük etkileşimler için (seçenek ekleme/silme, AJAX oy verme) |
| Statik dosyalar | WhiteNoise | Vercel'de statik dosyaları Django üzerinden sunmak için |
| Deployment | Vercel (Python runtime) | Serverless; kalıcı dosya sistemi yok |

### Python bağımlılıkları (`requirements.txt`)

```
Django>=5.2,<5.3
dj-database-url
psycopg[binary]
whitenoise
python-dotenv
```

> Başka paket ekleme (Django REST Framework, Celery, Redis, React vb. **yok**). Yeni bir paket gerçekten gerekirse önce sor.

---

## 3. Kullanıcı Rolleri ve Yetkiler

| İşlem | Ziyaretçi (üye değil) | Üye |
|---|---|---|
| Anket akışını görüntüleme | ✅ | ✅ |
| Anket detayını görüntüleme | ✅ | ✅ |
| Oy verme | ✅ (tarayıcı başına 1 oy) | ✅ (hesap başına 1 oy) |
| Anket oluşturma | ❌ → giriş sayfasına yönlendirilir | ✅ |
| Kendi anketini silme | ❌ | ✅ (Faz 5) |

---

## 4. Veri Modeli

Uygulama adları: `accounts` (kullanıcılar), `polls` (anketler).

### 4.1 `accounts.User` (özel kullanıcı modeli)

`AbstractUser`'dan türetilir. **Proje başında** tanımlanmalı (`AUTH_USER_MODEL = "accounts.User"`), sonradan değiştirmek zordur.

| Alan | Tip | Kural |
|---|---|---|
| `username` | CharField(30) | Benzersiz, zorunlu. 3–30 karakter; sadece harf, rakam, `_` ve `.` . Büyük/küçük harf duyarsız benzersizlik (kayıtta `iexact` kontrolü) |
| `email` | EmailField | **Benzersiz**, zorunlu. Küçük harfe çevrilerek kaydedilir. Hiçbir sayfada gösterilmez |
| `password` | (Django yerleşik) | Django'nun hash'leme ve parola doğrulayıcıları kullanılır (min. 8 karakter) |
| `date_joined` | (Django yerleşik) | |

- Giriş **e-posta + parola** ile yapılır → basit bir özel `EmailBackend` yazılır (`AUTHENTICATION_BACKENDS`).
- `first_name` / `last_name` kullanılmaz.

### 4.2 `polls.Poll`

| Alan | Tip | Kural |
|---|---|---|
| `author` | FK → User (`on_delete=CASCADE`, `related_name="polls"`) | |
| `question` | CharField(200) | Zorunlu, en az 5 karakter, baş/son boşluk temizlenir |
| `created_at` | DateTimeField(auto_now_add) | İndeksli; akış bu alana göre yeniden eskiye sıralanır |

### 4.3 `polls.Option`

| Alan | Tip | Kural |
|---|---|---|
| `poll` | FK → Poll (`CASCADE`, `related_name="options"`) | |
| `text` | CharField(100) | Zorunlu, boş olamaz |
| `order` | PositiveSmallIntegerField | 0–4; seçenek sırası ve renk ataması için |

- Bir ankette **2–5 seçenek** olmalı (form seviyesinde doğrulanır).
- Aynı anket içinde tekrar eden seçenek metni olamaz (büyük/küçük harf duyarsız).

### 4.4 `polls.Vote`

| Alan | Tip | Kural |
|---|---|---|
| `poll` | FK → Poll (`CASCADE`, `related_name="votes"`) | Sorgu kolaylığı için tutulur |
| `option` | FK → Option (`CASCADE`, `related_name="votes"`) | `option.poll == poll` olmalı (view'da doğrulanır) |
| `user` | FK → User, `null=True` | Üye oyu |
| `voter_token` | CharField(36), `null=True` | Ziyaretçi oyu (çerezdeki UUID) |
| `created_at` | DateTimeField(auto_now_add) | |

**Kısıtlar (`Meta.constraints`):**
- `UniqueConstraint(fields=["poll", "user"], condition=Q(user__isnull=False), name="unique_vote_per_user")`
- `UniqueConstraint(fields=["poll", "voter_token"], condition=Q(voter_token__isnull=False), name="unique_vote_per_token")`
- `CheckConstraint`: `user` veya `voter_token`'dan en az biri dolu olmalı.

### 4.5 Oy verme kuralları

- Her anket için **tek oy**. Prototipte **oy değiştirme yok**.
- **Üye:** oy `user` ile kaydedilir.
- **Ziyaretçi:** bir middleware, çerezi olmayan her ziyaretçiye `kararsizim_vid` adlı bir çerez atar (UUID4, 1 yıl, `HttpOnly`, `SameSite=Lax`, prod'da `Secure`). Oy bu `voter_token` ile kaydedilir.
- Anket sahibi kendi anketine oy verebilir.
- **Sonuçlar oy verdikten sonra** gösterilir (oy vermeden önce sadece seçenekler görünür; toplam oy sayısı görünebilir).
- Not: Çerez tabanlı kontrol, çerezi silen biri tarafından aşılabilir. Prototip için kabul edilebilir; ileride IP/rate limit eklenebilir (bkz. Backlog).

---

## 5. Sayfalar ve URL'ler

Tüm URL'ler ve arayüz metinleri **Türkçe**.

| URL | View | Erişim | Açıklama |
|---|---|---|---|
| `/` | `poll_list` | Herkes | Anket akışı. Yeniden eskiye, sayfa başına 10 anket, basit sayfalama ("Daha fazla" / sayfa numaraları) |
| `/anket/yeni/` | `poll_create` | Sadece üye (`login_required`) | Anket oluşturma formu |
| `/anket/<int:pk>/` | `poll_detail` | Herkes | Anket detayı, oy verme / sonuçlar |
| `/anket/<int:pk>/oy/` | `poll_vote` | Herkes, sadece `POST` | Oy kaydı. JSON döner (AJAX), JS yoksa detay sayfasına redirect |
| `/kayit/` | `register` | Sadece giriş yapmamış | Kayıt formu |
| `/giris/` | `login` | Sadece giriş yapmamış | Giriş formu (`?next=` desteği) |
| `/cikis/` | `logout` | Üye, sadece `POST` | Çıkış |
| `/admin/` | Django admin | Superuser | Moderasyon için |

### 5.1 Sayfa detayları

**Ana sayfa (akış)**
- Üstte hero alanı: "Kararsız mı kaldın? Sor, herkes oylasın." + "Anket Oluştur" butonu (ziyaretçide giriş sayfasına götürür).
- Anket kartları: soru, `@kullaniciadi`, göreli zaman ("5 dk önce" — Django `timesince` filtresi), toplam oy sayısı, seçenekler.
- Kartın içinden **doğrudan oy verilebilir** (sayfa yenilenmeden). Oy verildiyse kart sonuç görünümünde gelir.
- N+1 sorgudan kaçın: `select_related("author")`, `prefetch_related("options")`, `annotate(total_votes=Count("votes"))`. Kullanıcının oy verdiği anket ID'leri tek sorguyla alınır.

**Anket oluşturma**
- Soru alanı + başlangıçta 2 seçenek alanı.
- "+ Seçenek ekle" butonu (5'e ulaşınca gizlenir/disable olur), her seçeneğin yanında sil butonu (2'nin altına düşmez) — saf JS.
- Sunucu tarafında da 2–5 kuralı, boş seçenek ve tekrar kontrolü yapılır (JS'e güvenilmez).
- Anket ve seçenekler `transaction.atomic()` içinde kaydedilir.
- Başarılı olursa anket detayına yönlendirilir + başarı mesajı (Django messages).

**Anket detayı**
- Soru, yazar, tarih, seçenekler / sonuçlar.
- Sonuç görünümü: her seçenek için renkli ilerleme çubuğu, yüzde ve oy sayısı; kullanıcının seçtiği seçenek işaretli ("Senin oyun ✓"); en çok oy alan vurgulu.
- "Linki kopyala" butonu (Clipboard API).

**Kayıt / Giriş**
- Kayıt: kullanıcı adı, e-posta, parola, parola tekrar. Hata mesajları Türkçe ve alan bazlı.
- Giriş: e-posta + parola.
- Kayıt sonrası otomatik giriş ve ana sayfaya yönlendirme.

### 5.2 Oy API sözleşmesi

`POST /anket/<pk>/oy/` — form-encoded, CSRF token `X-CSRFToken` header'ında.

İstek: `option_id=<id>`

Yanıtlar:
```json
// 200 — başarılı
{ "ok": true, "total_votes": 12, "voted_option_id": 34,
  "results": [ { "id": 34, "text": "Sinema", "votes": 7, "percent": 58 },
               { "id": 35, "text": "Restoran", "votes": 5, "percent": 42 } ] }

// 409 — zaten oy verilmiş (mevcut sonuçlar yine döner)
{ "ok": false, "error": "already_voted", "results": [...], "voted_option_id": 34, "total_votes": 12 }

// 400 — geçersiz seçenek
{ "ok": false, "error": "invalid_option" }
```
- Yarış durumunda (aynı anda iki istek) `IntegrityError` yakalanıp 409 döner.
- Yüzdeler tam sayıya yuvarlanır; toplam oy 0 ise hepsi 0.

---

## 6. Arayüz ve Tasarım Rehberi

**Hedef kitle:** Genç kullanıcılar. **His:** Eğlenceli, enerjik ama temiz ve ferah.

### 6.1 Prensipler
- **Açık arka plan**, üzerinde **canlı renk vurguları** ve yumuşak renk tonları (pastel tint'ler).
- Bol boşluk, büyük yuvarlatılmış köşeler, yumuşak gölgeler.
- **Mobil öncelikli** (mobile-first), tek sütun akış; masaüstünde ortalanmış maks. ~680px içerik.
- Emojiye yer var ama ölçülü (ör. logo yanında 🤔, boş durumda ✨).

### 6.2 Renk paleti (CSS değişkenleri — `static/css/main.css` içinde `:root`)

```css
:root {
  /* Zemin */
  --bg: #FAF8FF;            /* çok açık lila-beyaz */
  --surface: #FFFFFF;
  --border: #ECE7F7;
  --text: #1E1B2E;
  --text-muted: #6B6880;

  /* Marka */
  --primary: #7C3AED;       /* canlı mor */
  --primary-soft: #F1EAFE;
  --accent: #EC4899;        /* pembe */
  --gradient: linear-gradient(135deg, #7C3AED 0%, #EC4899 100%);

  /* Seçenek renkleri (order 0–4) */
  --opt-1: #7C3AED;  --opt-1-soft: #F1EAFE;   /* mor */
  --opt-2: #EC4899;  --opt-2-soft: #FDE8F3;   /* pembe */
  --opt-3: #F97316;  --opt-3-soft: #FFEEDF;   /* turuncu */
  --opt-4: #14B8A6;  --opt-4-soft: #DDF7F3;   /* turkuaz */
  --opt-5: #EAB308;  --opt-5-soft: #FEF6D6;   /* sarı */

  /* Durum */
  --success: #16A34A;
  --danger: #DC2626;

  /* Şekil */
  --radius: 18px;
  --radius-sm: 12px;
  --shadow: 0 6px 24px rgba(124, 58, 237, 0.08);
}
```

- Her seçenek `order` değerine göre kendi rengini alır: oy öncesi buton kenarlığı/hover'ı `--opt-n`, arka planı `--opt-n-soft`; sonuç çubuğu dolgusu `--opt-n`.
- Birincil butonlar `--gradient` arka planlı, beyaz yazılı, hover'da hafif yükselme (`translateY(-1px)`).
- Metin/arka plan kontrastı WCAG AA'yı sağlamalı (sarı üzerine beyaz yazı kullanma).

### 6.3 Tipografi
- Google Fonts: **Plus Jakarta Sans** (400, 600, 700, 800). Yedek: `system-ui, sans-serif`.
- Soru başlıkları 600–700 ağırlık, logo 800.

### 6.4 Bileşenler
- **Navbar:** Solda logo "kararsızım 🤔" (gradient yazı), sağda ziyaretçiye "Giriş" / "Kayıt ol", üyeye `@kullaniciadi` + "Anket oluştur" + "Çıkış".
- **Anket kartı:** beyaz yüzey, `--radius`, `--shadow`, üstte yazar + zaman (muted), büyük soru metni, seçenek butonları alt alta tam genişlik.
- **Sonuç çubuğu:** yuvarlak uçlu bar, genişlik animasyonu (`transition: width .6s ease`), sağda `%58 · 7 oy`.
- **Boş durum:** "Henüz anket yok. İlk kararsızlığı sen paylaş ✨" + buton.
- **Flash mesajları:** üstte renkli yumuşak kutular, birkaç saniye sonra kaybolur.
- **Formlar:** büyük input'lar, odakta mor halka (`outline: 3px solid var(--primary-soft)`), hata metni kırmızı ve alanın altında.
- Erişilebilirlik: tüm butonlar klavye ile kullanılabilir, `:focus-visible` stilleri, form etiketleri (`<label>`).

---

## 7. Proje Klasör Yapısı

```
kararsizim/
├── CLAUDE.md                  # bu dosya (veya docs/PLAN.md)
├── manage.py
├── requirements.txt
├── vercel.json
├── .env.example
├── .gitignore
├── README.md
├── config/                    # Django proje ayarları
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py                # Vercel giriş noktası (app = application)
├── accounts/
│   ├── models.py  forms.py  views.py  urls.py  backends.py  admin.py
│   └── migrations/
├── polls/
│   ├── models.py  forms.py  views.py  urls.py  admin.py  middleware.py
│   ├── templatetags/          # (gerekirse) yardımcı filtreler
│   ├── tests/
│   └── migrations/
├── templates/
│   ├── base.html
│   ├── partials/ (navbar.html, messages.html, poll_card.html)
│   ├── accounts/ (register.html, login.html)
│   └── polls/ (poll_list.html, poll_detail.html, poll_create.html)
└── static/
    ├── css/main.css
    ├── js/ (vote.js, poll_form.js, main.js)
    └── img/ (favicon.svg)
```

---

## 8. Ortam Değişkenleri (`.env.example`)

```
DJANGO_SECRET_KEY=degistir-beni
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,.vercel.app
DJANGO_CSRF_TRUSTED_ORIGINS=https://*.vercel.app
DATABASE_URL=postgresql://postgres.<proje-ref>:<parola>@aws-0-<bolge>.pooler.supabase.com:6543/postgres
```

- `DATABASE_URL` yoksa (yerel geliştirmede) **SQLite**'a düşülebilir; prod'da mutlaka Supabase.
- `.env` **asla** commit edilmez (`.gitignore`'a ekle).

---

## 9. Supabase ve Vercel ile İlgili Kritik Notlar

### Supabase
- Supabase panelinde **Connect → Transaction pooler** bağlantı dizesini kullan (port **6543**). Serverless ortamda doğrudan bağlantı (5432) bağlantı sayısını tüketir.
- Transaction pooler ile Django ayarları:
  ```python
  DATABASES = {"default": dj_database_url.config(conn_max_age=0, ssl_require=True)}
  DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
  ```
- Migration'lar **build sırasında değil**, geliştirici makinesinden çalıştırılır: `.env`'de prod `DATABASE_URL` ile `python manage.py migrate`. (Gerekirse migration için Session pooler / doğrudan bağlantı dizesi kullanılabilir.)
- **Güvenlik:** Supabase, `public` şemadaki tabloları otomatik olarak REST API (Data API) üzerinden açar. Django `postgres` rolüyle bağlandığı için RLS'den etkilenmez; bu yüzden migration'lardan sonra tüm tablolarda **RLS'i aç ve hiç policy ekleme** (böylece anon key ile dışarıdan erişilemez). Alternatif: Supabase panelinden Data API'yi kapat.
  ```sql
  -- Her Django tablosu için (ör.):
  alter table public.polls_poll enable row level security;
  ```
  Bunu kolaylaştırmak için tüm `public` tablolarında RLS açan bir SQL snippet'i README'ye eklenmeli.

### Vercel
- Vercel'in Python runtime'ı `config/wsgi.py` içinde **`app`** adlı WSGI nesnesini arar → dosyanın sonuna `app = application` ekle.
- Kalıcı dosya sistemi yok → SQLite, dosya yükleme, yerel log dosyası kullanılamaz.
- Statik dosyalar: WhiteNoise middleware + prototip için `WHITENOISE_USE_FINDERS = True` (collectstatic adımına gerek kalmadan `static/` klasöründen sunar). Prod'da `DEBUG=False` iken de çalıştığını doğrula.
- Başlangıç `vercel.json` (Vercel'in **güncel** Python/Django dokümantasyonuyla karşılaştırıp gerekirse güncelle):
  ```json
  {
    "builds": [{ "src": "config/wsgi.py", "use": "@vercel/python" }],
    "routes": [{ "src": "/(.*)", "dest": "config/wsgi.py" }]
  }
  ```
- Ortam değişkenleri Vercel proje ayarlarından (Settings → Environment Variables) girilir; prod'da `DJANGO_DEBUG=False`.
- Prod güvenlik ayarları: `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` (DEBUG=False iken True).

---

## 10. Geliştirme Kuralları (Claude Code için)

1. **Fazları sırayla uygula.** Bir fazda sadece o fazın kapsamını yap; sonraki fazlara geçme.
2. Her fazın sonunda: `python manage.py check`, `python manage.py makemigrations --check` (değişiklik kalmamalı) ve `python manage.py test` çalıştır; hepsi temiz geçmeli.
3. Her fazın sonunda kısa bir özet ver: ne yapıldı, nasıl test edilir, bilinen eksikler.
4. Kod ve yorumlar **İngilizce** (değişken/fonksiyon adları), **arayüz metinleri Türkçe**. `LANGUAGE_CODE = "tr"`, `TIME_ZONE = "Europe/Istanbul"`, `USE_TZ = True`.
5. Basitlik öncelikli: class-based view yerine okunaklıysa function-based view tercih edilebilir; gereksiz soyutlama yapma.
6. Sırlar (SECRET_KEY, DB parolası) asla koda yazılmaz; `os.environ` / `python-dotenv` ile okunur.
7. Tüm formlarda CSRF korumasını koru. AJAX isteklerinde CSRF token'ı çerezden okuyup `X-CSRFToken` header'ına ekle.
8. JS olmadan da temel akış çalışmalı (progressive enhancement): oy formu normal `POST` ile de çalışır, JS varsa fetch ile sayfa yenilenmeden çalışır.
9. E-posta adresi hiçbir template'te, JSON yanıtında veya admin dışı yerde görünmemeli.
10. Yeni bağımlılık eklemeden önce sor.

---

## 11. Fazlar

### Faz 0 — Proje İskeleti ve Tasarım Sistemi

**Kapsam**
- Git deposu, `.gitignore` (Python, `.env`, `db.sqlite3`, `__pycache__`, `.vercel`), `requirements.txt`, `.env.example`.
- Django projesi `config`, uygulamalar `accounts` ve `polls`.
- `settings.py`: env tabanlı ayarlar, `DATABASE_URL` yoksa SQLite, WhiteNoise, Türkçe dil ve İstanbul saat dilimi, `templates/` ve `static/` dizinleri.
- **`accounts.User` özel kullanıcı modeli** (e-posta benzersiz) ve `AUTH_USER_MODEL` — ilk migration'dan **önce**.
- `base.html` (navbar, mesaj alanı, footer, Google Fonts), `main.css` içinde bölüm 6'daki tasarım değişkenleri ve temel bileşen stilleri.
- Geçici bir ana sayfa (hero + boş durum kartı) ile tasarımın görünmesi.

**Kabul kriterleri**
- `python manage.py runserver` ile ana sayfa açılıyor, tasarım dili (renkler, font, kart) görünüyor.
- `migrate` sorunsuz çalışıyor, `createsuperuser` ile admin'e girilebiliyor.

**Claude Code'a verilecek prompt**
> `CLAUDE.md` dosyasını baştan sona oku. Ardından sadece **Faz 0**'ı uygula: proje iskeletini, ayarları, özel kullanıcı modelini, base template'i ve tasarım sistemini (bölüm 6) oluştur. Bitince kontrol komutlarını çalıştır ve özet ver.

---

### Faz 1 — Üyelik (Kayıt / Giriş / Çıkış)

**Kapsam**
- `RegisterForm`: kullanıcı adı (format + büyük/küçük harf duyarsız benzersizlik), e-posta (küçük harfe çevir, benzersiz), parola + tekrar (Django parola doğrulayıcıları).
- `EmailBackend` ile e-posta + parola girişi; `LoginForm`.
- `/kayit/`, `/giris/`, `/cikis/` (POST) view'ları; giriş yapmış kullanıcı kayıt/giriş sayfasına girerse ana sayfaya yönlendirilir.
- `LOGIN_URL = "/giris/"`, `LOGIN_REDIRECT_URL = "/"`, `LOGOUT_REDIRECT_URL = "/"`; `?next=` desteği.
- Navbar'ın oturum durumuna göre değişmesi. Türkçe hata ve başarı mesajları.
- Admin'de User kaydı (e-posta admin'de görünebilir).
- Testler: kayıt başarılı, tekrar eden kullanıcı adı/e-posta reddi, e-posta ile giriş, yanlış parola.

**Kabul kriterleri**
- Yeni kullanıcı kayıt olup otomatik giriş yapıyor; çıkış yapıp e-postasıyla tekrar girebiliyor.
- Navbar'da `@kullaniciadi` görünüyor, e-posta hiçbir sayfada görünmüyor.

**Prompt**
> `CLAUDE.md`'yi oku ve **Faz 1**'i uygula (üyelik sistemi). Faz 0'daki yapıyı bozma. Testleri yaz, çalıştır ve özet ver.

---

### Faz 2 — Anket Oluşturma ve Akış

**Kapsam**
- `Poll` ve `Option` modelleri + migration'lar + admin (Option inline).
- `/anket/yeni/` (login_required): soru + 2–5 seçenek; `poll_form.js` ile dinamik seçenek ekleme/silme; sunucu tarafı doğrulama (2–5, boş yok, tekrar yok); `transaction.atomic()`.
- `/` akış: yeniden eskiye, sayfa başına 10, sayfalama; kartlarda soru, `@yazar`, göreli zaman, seçenekler (bu fazda oy butonları görünür ama henüz işlevsiz olabilir).
- `/anket/<pk>/` detay sayfası.
- Ziyaretçi "Anket oluştur"a basarsa giriş sayfasına (`?next=/anket/yeni/`) yönlendirilir.
- Boş durum tasarımı.
- Testler: ziyaretçi oluşturamaz, 1 veya 6 seçenekli anket reddedilir, geçerli anket oluşur, akış sıralaması.

**Kabul kriterleri**
- Üye anket oluşturabiliyor; anket akışta en üstte ve detay sayfasında görünüyor.
- Seçenek sayısı kuralları hem arayüzde hem sunucuda uygulanıyor.

**Prompt**
> `CLAUDE.md`'yi oku ve **Faz 2**'yi uygula (anket modelleri, oluşturma formu, akış ve detay sayfası). Oy verme işlevini bu fazda yapma. Testleri yaz, çalıştır ve özet ver.

---

### Faz 3 — Oy Verme ve Sonuçlar

**Kapsam**
- `Vote` modeli ve kısıtları (bölüm 4.4), migration.
- `polls/middleware.py`: ziyaretçi çerezi (`kararsizim_vid`) atayan middleware.
- `POST /anket/<pk>/oy/`: bölüm 5.2'deki sözleşmeye uygun; üye → `user`, ziyaretçi → `voter_token`; seçeneğin ankete ait olduğunu doğrula; `IntegrityError` → 409.
- `vote.js`: kart/detay sayfasında seçeneğe tıklayınca fetch ile oy ver, sonuç görünümüne animasyonlu geçiş; hata durumunda kullanıcıya mesaj.
- JS'siz fallback: normal form POST → detay sayfasına redirect.
- Akış ve detay sayfası: kullanıcı daha önce oy verdiyse sonuç görünümü gelir; seçtiği seçenek işaretli; toplam oy sayısı.
- Admin'de oyların listelenmesi (salt okunur yeterli).
- Testler: ziyaretçi oy verir, aynı çerezle ikinci oy 409, üye oy verir ve ikinci oy 409, başka anketin seçeneğiyle oy 400, yüzde hesaplama.

**Kabul kriterleri**
- Ziyaretçi ve üye, sayfa yenilenmeden oy verip sonuçları görebiliyor.
- Aynı tarayıcı/hesap ikinci kez oy veremiyor; sayfa yenilendiğinde sonuç görünümü korunuyor.

**Prompt**
> `CLAUDE.md`'yi oku ve **Faz 3**'ü uygula (oy verme, ziyaretçi çerezi, sonuç görünümü). API sözleşmesine (bölüm 5.2) birebir uy. Testleri yaz, çalıştır ve özet ver.

---

### Faz 4 — Supabase Bağlantısı ve Vercel'e Deploy

**Kapsam**
- `settings.py`'nin prod için hazırlanması: `DEBUG` env'den, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, güvenli çerezler, `SECURE_PROXY_SSL_HEADER`, bölüm 9'daki veritabanı ayarları.
- `config/wsgi.py`'ye `app = application`.
- `vercel.json` (bölüm 9) — Vercel'in güncel dokümantasyonuyla doğrula.
- WhiteNoise ile statik dosyaların `DEBUG=False`'ta da sunulduğunun yerelde doğrulanması.
- README: yerel kurulum, Supabase projesi oluşturma, bağlantı dizesi alma, `migrate` çalıştırma, **RLS'i açan SQL snippet'i**, Vercel'e deploy adımları ve env değişkenleri listesi.
- Deploy sonrası duman testi listesi: ana sayfa, kayıt, giriş, anket oluşturma, ziyaretçi oyu, üye oyu, admin.

**Kabul kriterleri**
- Uygulama Vercel URL'sinde çalışıyor ve verileri Supabase'e yazıyor.
- CSS/JS dosyaları yükleniyor, CSRF hatası yok.
- Supabase Data API üzerinden tablolara anon key ile erişilemiyor (RLS açık).

**Prompt**
> `CLAUDE.md`'yi oku ve **Faz 4**'ü uygula: uygulamayı Supabase Postgres ve Vercel deploy için hazırla, README'ye adım adım kurulum/deploy talimatlarını yaz. Benim yapmam gereken manuel adımları (Supabase ve Vercel panelinde) açıkça listele.

---

### Faz 5 — Cilalama (Prototip Sonu)

**Kapsam**
- Üyenin kendi anketini silebilmesi (onay adımıyla, sadece POST).
- Basit kullanıcı profil sayfası: `/kullanici/<username>/` — o kullanıcının anketleri (e-posta yok).
- Özel 404 ve 500 sayfaları (tasarım diline uygun).
- Favicon, sayfa `<title>`'ları, temel meta etiketleri (Open Graph: anket paylaşılınca soru görünsün).
- Mobil görünüm, klavye erişilebilirliği ve kontrast kontrolü; küçük animasyon iyileştirmeleri.
- Akışta sıralama sekmeleri: "En yeni" / "En çok oylanan".

**Prompt**
> `CLAUDE.md`'yi oku ve **Faz 5**'i uygula. Mevcut davranışları bozma; testleri güncelle ve tümünün geçtiğini doğrula.

---

## 12. Backlog (Prototip Sonrası Fikirler)

Öncelik sırası yok; ihtiyaca göre seçilecek:
- Oy değiştirme / geri alma
- Anket süresi (ör. 24 saat sonra kapanma) ve "kapanmış anket" görünümü
- Kategoriler / etiketler ve filtreleme
- Arama
- Rate limiting ve kötüye kullanım koruması (IP bazlı sınır, CAPTCHA)
- Anket raporlama (şikayet) ve moderasyon paneli
- Yorumlar
- Parola sıfırlama (e-posta gönderimi gerektirir)
- Anket seçeneklerine görsel ekleme (Supabase Storage)
- Karanlık mod
- Paylaşım kartı görseli üretme

---

## 13. Kapsam Dışı (Bilinçli olarak yapılmayacak)

- Kullanıcı takip etme / takipçi sistemi
- Kişiselleştirilmiş akış
- Frontend framework (React, Vue vb.) ve SPA mimarisi
- Supabase Auth, Supabase JS istemcisi, realtime abonelikler
- Mobil uygulama
