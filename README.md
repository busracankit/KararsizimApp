# Kararsızım 🤔

Kararsız kaldığın konularda anket aç, herkes oylasın. Django 5.2 + saf HTML/CSS/JS.
Proje planı ve fazlar: [`docs/KARARSIZIM_PLAN.md`](docs/KARARSIZIM_PLAN.md)

## Yerel kurulum

Python 3.12 önerilir.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # DJANGO_SECRET_KEY'i değiştir, DATABASE_URL'i boş bırak (SQLite)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- Site: http://127.0.0.1:8000/
- Admin: http://127.0.0.1:8000/admin/

## Kontroller

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

Supabase ve Vercel kurulumu Faz 4'te bu dosyaya eklenecek.
