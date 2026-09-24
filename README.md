# Kararsızım 🤔

Kararsız kaldığın konularda anket aç, herkes oylasın. Django 5.2 + saf HTML/CSS/JS.
Veritabanı: Supabase (Postgres) · Yayın: Vercel.
Proje planı ve fazlar: [`docs/KARARSIZIM_PLAN.md`](docs/KARARSIZIM_PLAN.md)

## Yerel kurulum

Python 3.12 önerilir (3.10+ çalışır).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # DJANGO_SECRET_KEY'i değiştir, DATABASE_URL'i boş bırak (SQLite)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- Site: http://127.0.0.1:8000/ · Admin: http://127.0.0.1:8000/admin/

### Kontroller

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

## Ortam değişkenleri

| Değişken | Yerel | Vercel (Production) | Gizli mi? |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | herhangi bir değer | uzun rastgele değer (aşağıdaki komut) | **Evet** |
| `DJANGO_DEBUG` | `True` | `False` | Hayır |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | `.vercel.app` | Hayır |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | — | `https://*.vercel.app` | Hayır |
| `DATABASE_URL` | boş (SQLite) | Supabase Transaction pooler dizesi | **Evet** |

Gizli anahtar üretmek için:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

## Supabase (veritabanı)

Proje: **kararsizim** (bölge: eu-central-1 / Frankfurt).

1. **Bağlantı dizesi:** Supabase Dashboard → proje → **Connect** → **Transaction pooler** (port **6543**).
   `[YOUR-PASSWORD]` yerine veritabanı parolasını yaz. Parolayı bilmiyorsan:
   **Project Settings → Database → Reset database password**.
   Parolada `@ : / ? # %` gibi karakterler varsa URL-kodla (ör. `@` → `%40`) ya da sadece harf/rakamdan oluşan bir parola seç.
2. **Migration (geliştirici makinesinden, build sırasında değil):**
   ```bash
   DATABASE_URL='postgresql://postgres.<ref>:<parola>@<host>:6543/postgres' python manage.py migrate
   DATABASE_URL='...' python manage.py createsuperuser
   ```
   (Transaction pooler migration'da sorun çıkarırsa Connect → **Session pooler** dizesini, port 5432, kullan.)
3. **RLS (güvenlik):** Django `postgres` rolüyle bağlanır, RLS'den etkilenmez. Supabase'in otomatik REST API'si (anon key)
   tablolara erişemesin diye tüm `public` tablolarında RLS açık ve **hiç policy yok**.
   Projede, `public` şemasında oluşturulan her yeni tabloda RLS'i otomatik açan bir event trigger (`ensure_rls`) kurulu.
   Elle kontrol / açmak için SQL Editor'de:
   ```sql
   -- RLS'i kapalı tablo kaldı mı?
   select tablename from pg_tables where schemaname = 'public' and not rowsecurity;

   -- public'teki tüm tablolarda RLS'i aç
   do $$
   declare t record;
   begin
     for t in select tablename from pg_tables where schemaname = 'public' loop
       execute format('alter table public.%I enable row level security', t.tablename);
     end loop;
   end $$;
   ```

## Vercel (yayın)

- Vercel Django'yu `manage.py` üzerinden otomatik tanır; `WSGI_APPLICATION` giriş noktasıdır.
- `collectstatic` build sırasında otomatik çalışır, `/static/` dosyaları Vercel CDN'inden sunulur.
- `vercel.json` sadece fonksiyon bölgesini **fra1 (Frankfurt)** yapar — veritabanıyla aynı bölge, sorgular hızlı olsun diye.
- Python sürümü `.python-version` (3.12). Bağımlılıklar `requirements.txt`.
- Deploy: GitHub'daki `main` dalına her `git push` otomatik production deploy'u başlatır.
- Ortam değişkenleri: Vercel → proje → **Settings → Environment Variables** (yukarıdaki tablo).

## Deploy sonrası duman testi

- [ ] Ana sayfa açılıyor, CSS/JS yükleniyor (renkler, font)
- [ ] Kayıt ol → otomatik giriş, navbar'da `@kullaniciadi`
- [ ] Çıkış → e-posta ile tekrar giriş
- [ ] Anket oluştur (2–5 seçenek)
- [ ] Gizli pencerede ziyaretçi olarak oy ver → sonuçlar; sayfa yenilenince sonuçlar kalıyor
- [ ] Üye olarak oy ver → ikinci oy engelleniyor
- [ ] `/admin/` → superuser ile giriş, anket ve oyları gör
- [ ] Supabase REST API'den anon key ile tablolar okunamıyor (RLS)
