# CLAUDE.md

Bu dosya, bu depoda çalışan Claude oturumları için kalıcı bağlamdır.

## Proje

**Kararsızım**: kararsız kalınan konularda anket açılan, herkesin oy verebildiği bir web uygulaması.
Anket açmak için üyelik gerekir; ziyaretçiler görüntüleyip oy verebilir. Takip sistemi yok, tek ortak akış var.

**Tek doğruluk kaynağı: [`docs/KARARSIZIM_PLAN.md`](docs/KARARSIZIM_PLAN.md).**
Veri modeli, URL'ler, API sözleşmesi, tasarım rehberi ve fazlar oradadır. Buraya kopyalanmaz.
Her faza başlamadan o fazın bölümünü ve bölüm 10'daki geliştirme kurallarını oku.
Bu dosyadaki "Netleşen kararlar" plan ile çelişirse **bu dosya geçerlidir** (plan sonradan netleşti).

## Durum

| Faz | Konu | Durum |
|---|---|---|
| 0 | İskelet + tasarım sistemi | ✅ Tamamlandı |
| 1 | Üyelik (kayıt/giriş/çıkış) | ✅ Tamamlandı |
| 2 | Anket oluşturma + akış | ✅ Tamamlandı |
| 3 | Oy verme + sonuçlar | ✅ Tamamlandı |
| 4 | Supabase + Vercel deploy | ✅ Tamamlandı |
| 5 | Cilalama | ✅ Tamamlandı |
| B | Backlog (plan §12, 11 madde) | ✅ Yayında (26.09, f8b6a86) — kullanıcı testi bekliyor |

Çalışma şekli: **faz faz.** Bir faz bitince kontroller + özet verilir, kullanıcı onaylamadan sonraki faza geçilmez.
Bir faz bittiğinde bu tabloyu güncelle.

## Netleşen kararlar (planda olmayan / planı değiştiren)

- **Oy kuralı:** Ziyaretçiyken oy verip sonra giriş yapan kişi aynı ankete tekrar oy veremez.
  Üye oy verirken hem `user` hem `voter_token` (çerez) kontrol edilir; oy kaydında ikisi de saklanır.
  Uygulandı (Faz 3): `polls/services.py::_voter_filter` = `user` VEYA `voter_token`.
  Sonuç: aynı tarayıcıda başka bir üye de o ankete oy veremez; sonuçları görür ama "Senin oyun" rozeti çıkmaz.
- **Benzersizlik DB seviyesinde:** `username` ve `email` için `UniqueConstraint(Lower(...))` (büyük/küçük harf duyarsız). Formlar yine `iexact` ile kontrol edip Türkçe hata gösterir.
- **Kullanıcı adı sadece ASCII:** `^[A-Za-z0-9_.]+$`, 3–30 karakter. Türkçe İ/ı büyük/küçük harf dönüşüm sorunlarını önlemek için ş/ğ/ı yok.
- **Sayfalama:** sayfa numaralı basit sayfalama; "Daha fazla" butonu yok.
- **Deploy:** Kod GitHub'da tutulacak, Vercel git entegrasyonu ile deploy. Supabase projesi, migration, RLS ve Vercel kurulumunu Claude connector'larla yapar (Faz 4). `vercel.json` Vercel'in güncel Django dokümanına göre yazılır (plandaki `builds` biçimi eski).

## Backlog kararları (26.09)

- **Oy değiştirme:** açık ankette `change=1`; sadece kendi oyun (paylaşılan tarayıcıda başkasının oyu değişmez).
- **Süreli anket:** `Poll.closes_at` (süresiz/1s/1g/3g/1h). Kapanınca oy/değişiklik 403 `poll_closed`, sonuçlar herkese açık.
- **Kategoriler:** `polls/models.py::CATEGORIES` (10 sabit). **Arama:** `?q=` soru + seçenek, Türkçe İ varyantı (`search_variants`).
- **Hız sınırı:** `RateLimitHit` modeli + `polls/ratelimit.py`, sınırlar `settings.RATE_LIMITS`. IP: `X-Real-IP` / `X-Forwarded-For`.
- **Şikayet/moderasyon:** `Report`; 5 açık şikayette `Poll.is_hidden`. Moderasyon Django admin'de (aksiyonlar). Gizli anket: 404 (sahibi + staff hariç).
- **Yorumlar:** `Comment`, sadece üye, ≤500; yazan veya anket sahibi siler; admin gizler.
- **Parola sıfırlama:** Django auth view'ları + Türkçe şablonlar. E-posta: `RESEND_API_KEY` → `accounts/email.py` (urllib), yoksa `EMAIL_HOST` SMTP, yoksa konsol. Gönderim hatası loglanır, raise edilmez.
  Resend alan adı doğrulanmadan sadece hesap sahibinin adresine gönderir.
- **Seçenek görseli:** `polls/storage.py` (Pillow → 800px WebP → Supabase Storage `option-images` public bucket, urllib). `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` yoksa alan gizli. Anket silinince görseller silinir.
- **Karanlık mod:** CSS değişkenleri, `:root[data-theme]` + `prefers-color-scheme`; toggle `main.js`, `localStorage["theme"]`. Yeni renk eklerken token kullan (sabit hex yazma).
- **Paylaşım görseli:** `polls/share_image.py` (Pillow, `polls/assets/fonts/PlusJakartaSans.ttf`, OFL). `/anket/<id>/paylasim.png`, og:image.
- Sayımlar (`total_votes`, `comment_count`) korelasyonlu alt sorgu — JOIN+Count kullanma (arama/yorum join'leri sayıları bozar).
- **Güvenlik incelemesi (27.09, code-review-security):**
  - Otomatik gizleme sadece farklı **üye** şikayetlerini sayar (ziyaretçi her istekte yeni çerez alabilir).
  - Ziyaretçi oyu: anket başına, IP başına 24 saatte 3 (`visitor_vote_per_poll`); aşınca 429 `login_required`. Üyeler ve oy değiştirme etkilenmez.
  - Giriş sınırı hem IP (`login`) hem hesap başına (`login_account`, anahtar e-postanın hash'i); `/admin/login/` de aynı sınırla sarıldı (`polls/admin.py`).
  - Hız sınırlayıcı önce kaydeder sonra sayar (eş zamanlı istekler birlikte geçemez); engellenen deneme silinir.
  - IP: proxy başlıklarına sadece `TRUST_PROXY_HEADERS` (Vercel'de otomatik) açıkken güvenilir; önce `X-Forwarded-For`.
  - Herkese açık önbelleklenen yanıtlara (`Cache-Control: public`/`s-maxage`) ziyaretçi çerezi eklenmez.
  - `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` joker yok; `VERCEL_PROJECT_PRODUCTION_URL`/`VERCEL_BRANCH_URL`/`VERCEL_URL` kodda eklenir.
  - POST formları gönderilince buton kilitlenir (çift tıklama); kayıtta yarış → form hatası, 500 değil.
- Oy API sözleşmesi uzantıları: `can_change`, `closed`, 403 `poll_closed`, 429 `rate_limited` / `login_required`, sonuçlarda isteğe bağlı `image_url`.

## Geçici şeyler (unutma)

- Şu an yok.

## Canlı ortam

- **Site:** https://kararsizim-liard.vercel.app (her `main` push'u otomatik production deploy).
- **Supabase:** proje `kararsizim`, ref `mzggagkmnkajelekvnxr`, bölge eu-central-1 (Frankfurt), org `team1` (free).
  `public` şemasındaki her yeni tabloda RLS'i otomatik açan event trigger (`ensure_rls` → `public.rls_auto_enable()`) kurulu; policy yok.
- **Vercel:** Django zero-config (manage.py'den algılanır, collectstatic build'de otomatik). `vercel.json` sadece `regions: ["fra1"]` (DB ile aynı bölge).
- Migration'lar build'de değil, geliştirici makinesinden `DATABASE_URL=... python manage.py migrate` ile.
- Gizli değerler (`DJANGO_SECRET_KEY`, `DATABASE_URL`) Vercel'e kullanıcı tarafından girilir; Claude parola/anahtar girmez. Şu an sadece Production hedefinde (Preview deploy'ları bu yüzden hata verir).
- Claude'un Vercel bağlantısı deploy listesini görür ama build/runtime loglarını ve deploy detayını göremez (403). Canlı site kontrolü masaüstü uygulamasının tarayıcı paneliyle yapılır.

## Yapı

```
config/        settings.py (env tabanlı), urls.py, wsgi.py (Vercel için `app = application`)
accounts/      özel User modeli (AUTH_USER_MODEL = "accounts.User"), admin
polls/         anket uygulaması; testler polls/tests/ altında
templates/     base.html, partials/ (navbar, messages), accounts/, polls/
static/        css/main.css (tüm tasarım token'ları :root'ta), js/main.js, img/favicon.svg
docs/          KARARSIZIM_PLAN.md
```

- Ayarlar ortam değişkenlerinden okunur (`.env`, python-dotenv). `DATABASE_URL` yoksa SQLite; varsa Supabase (transaction pooler, `conn_max_age=0`, `DISABLE_SERVER_SIDE_CURSORS`).
- `DEBUG=False` iken `DJANGO_SECRET_KEY` zorunlu, yoksa uygulama başlamaz.
- Statik dosyalar WhiteNoise ile, `WHITENOISE_USE_FINDERS = True` (collectstatic gerekmez).
- Giriş: `accounts.backends.EmailBackend` (`authenticate(request, email=..., password=...)`), ardından `ModelBackend` (admin kullanıcı adıyla girer). `login()` çağrılarında `backend="accounts.backends.EmailBackend"` verilir.
- Anket formu: seçenekler tekrar eden `options` input'ları olarak gelir (`request.POST.getlist("options")`), `PollCreateForm` boşları atar, 2–5 / ≤100 karakter / tekrar yok kuralını uygular. Tekrar kontrolü Türkçe İ/ı'ya duyarlı (`polls/forms.py::comparison_key`). Kayıt `transaction.atomic` içinde.
- Seçenek rengi: `Option.color_class` (`opt-1`…`opt-5`). Göreli zaman: `{% load poll_extras %}` + `|relative_time` ("az önce", "5 dakika önce").
- Akış: `?sayfa=N`, sayfa başına 10, `select_related("author").prefetch_related("options")` — sorgu sayısı anket sayısıyla artmamalı (testi var).
- Oylama: `polls/middleware.py` her tarayıcıya `kararsizim_vid` (UUID4) çerezi verir → `request.voter_token`. `POST /anket/<id>/oy/` `Accept: application/json` ise plan §5.2 JSON'u döner, değilse detay sayfasına redirect + mesaj. Sayım/yüzde/"oy verdi mi" mantığı `polls/services.py` içinde (`polls_with_counts`, `build_results`, `votes_by_poll`).
- **Dikkat:** `annotate(Count(...))` olan sorgularda `Meta.ordering` uygulanmaz → `order_by` açıkça yazılmalı (`polls_with_counts`).
- Kart/detay ortak gövdesi: `partials/poll_body.html` (oy formu ya da `partials/poll_results.html`). `vote.js` aynı sonuç HTML'ini JS ile üretir; birini değiştirirsen diğerini de değiştir.
- Faz 5: `/kullanici/<username>/` profil (iexact, aktif kullanıcı), `/anket/<id>/sil/` (sadece yazar, GET onay / POST siler, başkasına 404), akış sekmeleri `?sirala=yeni|populer`, sayfalama parçası `partials/pagination.html` (`extra_query`), `404.html`/`500.html`, Open Graph blokları (`og_title`, `og_description`), skip link.
- Buton gradyanı #7C3AED → #DB2777 (beyaz yazı AA ≥4.5:1). `--accent` #EC4899 sadece dekoratif.
- Formlar `templates/partials/field.html` (etiket, input, yardım, hata) ve `partials/form_errors.html` ile çizilir; yeni formlarda da bunları kullan.
- `?next=` sadece `url_has_allowed_host_and_scheme` ile doğrulanarak kullanılır (`accounts/views.py::_safe_next`).
- Çıkış sadece POST (navbar'da küçük form).
- `main.js` içinde global `getCookie(name)` var; AJAX'ta CSRF token'ı `X-CSRFToken` header'ına koymak için kullan.
- Seçenek renkleri: seçenek elemanına `opt-1`…`opt-5` sınıfı verilir (order 0→`opt-1`); bileşenler `--c` / `--c-soft` değişkenlerini kullanır.

## Komutlar

```bash
# kurulum
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver

# her fazın sonunda — hepsi temiz geçmeli
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

## Kurallar (kısa)

- **Güvenlik/doğruluk incelemesi:** projede `.claude/skills/code-review-security/` skill'i var. Kod incelemesi, "canlıya hazır mı?" sorularında ve Python/SQL/Supabase kodu yazdıktan sonra (self-check modu) bu skill'i kullan.

- Kod, değişken adları ve yorumlar **İngilizce**; arayüz metinleri ve URL'ler **Türkçe**.
- E-posta hiçbir template'te, JSON yanıtında veya admin dışı yerde görünmez. Yeni bir sayfa eklerken bunu test et.
- Yeni paket eklemeden önce kullanıcıya sor (izinli liste: `requirements.txt`).
- Function-based view tercih edilir; gereksiz soyutlama yok.
- JS'siz de çalışmalı (progressive enhancement).
- **Commit mesajlarına `Co-Authored-By` / `Claude-Session` gibi Claude atıf satırları eklenmez** (kullanıcı isteği). Commit yazarı: busracankit <cankitbusra@gmail.com>.

## Çalışma ortamı notları

- Kullanıcı macOS'ta; Claude'un yerel ortamı Linux ve Python 3.10. Vercel 3.12 kullanacak, kod 3.10+ uyumlu yazılır.
- Git işlemleri Kararsizim klasöründe silme izni ister (`.git/index.lock`); izin her oturumda yeniden istenir.
- `.env`, `db.sqlite3`, `.idea/`, `.DS_Store`, `Claude outputs/` git'e girmez.
- Yeni migration varsa canlıya push'tan ÖNCE kullanıcı Mac'te `pip install -r requirements.txt` + `read -s DATABASE_URL` + `python manage.py migrate` çalıştırmalı (yoksa canlı site yeni kolonları bulamaz).
- DEBUG=False yerel sunucuda şablonlar ve WhiteNoise dosyaları önbelleğe alınır; değişiklikten sonra sunucuyu yeniden başlat.
