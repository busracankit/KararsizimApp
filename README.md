**English** | [Türkçe](README.tr.md)

# Kararsızım 🤔

*"Kararsızım" means "I can't decide" in Turkish.*

Can't make up your mind? Open a poll and let everyone vote. Kararsızım is a small social polling app
built with Django 5.2 and plain HTML/CSS/JS, backed by Supabase (Postgres) and deployed on Vercel.

**Live demo:** https://kararsizim-liard.vercel.app

Project plan and phases: [`docs/KARARSIZIM_PLAN.md`](docs/KARARSIZIM_PLAN.md) (Turkish)

## Screenshots

| Home feed (dark mode) | Poll detail |
|---|---|
| ![Home feed](docs/screenshots/home.png) | ![Poll detail](docs/screenshots/poll-detail.png) |

| Create a poll | Log in |
|---|---|
| ![Create a poll](docs/screenshots/create-poll.png) | ![Log in](docs/screenshots/login.png) |

## Features

- **Polls with 2–5 options**, with an optional image per option (converted to WebP and stored in Supabase Storage)
- **Vote without signing up.** Guests get a cookie-based voter token, while members get one vote per account and can change it
- **Voting without a page reload** (progressive enhancement, so it still works without JavaScript)
- **Timed polls** that close automatically, with a countdown and final results
- **Categories, search and sorting** (newest / most voted). Search handles the Turkish İ/ı correctly
- **Comments** (members only) and **user profiles**
- **Reporting & moderation.** A poll is auto-hidden after 5 distinct member reports, and admins can hide or unhide it
- **Accounts:** sign up, log in with email, change password, and reset a forgotten password by email (Resend)
- **Dark mode** that follows the system setting, with a manual toggle
- **Share previews:** each poll has a generated Open Graph image (`/anket/<id>/paylasim.png`)
- **Rate limiting** on voting, poll creation, comments, reports, login and sign-up

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Django 5.2 (function-based views), Python 3.12 |
| Frontend | Django templates, vanilla CSS & JS (no build step) |
| Database | Supabase Postgres (Transaction pooler); SQLite locally |
| Storage | Supabase Storage (`option-images` bucket) |
| Email | Resend (falls back to SMTP, then to the console) |
| Images | Pillow |
| Static files | WhiteNoise / Vercel CDN |
| Hosting | Vercel (region `fra1`) |

## Project structure

```
config/        settings, urls, wsgi
accounts/      custom User model, email login backend, auth views, Resend email backend
polls/         models (Poll, Option, Vote, Report, Comment, RateLimitHit), views, forms,
               services.py, ratelimit.py, storage.py, share_image.py, templatetags/
templates/     HTML templates
static/        css/main.css, js/main.js, js/poll_form.js, js/vote.js
docs/          project plan and screenshots
```

## Local setup

Python 3.12 is recommended (3.10+ works).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # change DJANGO_SECRET_KEY, leave DATABASE_URL empty (SQLite)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- Site: http://127.0.0.1:8000/
- Admin: http://127.0.0.1:8000/admin/

Generate a secret key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

### Checks and tests

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

## Environment variables

| Variable | Local | Vercel (Production) | Secret? |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | any value | long random value | **Yes** |
| `DJANGO_DEBUG` | `True` | `False` | No |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | your domain (no wildcards; per-deploy hosts are added from `VERCEL_URL` automatically) | No |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | — | `https://<your-domain>` | No |
| `DATABASE_URL` | empty (SQLite) | Supabase Transaction pooler URL | **Yes** |
| `SUPABASE_URL` | optional | `https://<project-ref>.supabase.co` | No |
| `SUPABASE_SERVICE_ROLE_KEY` | optional | Supabase → Project Settings → API Keys → secret / service_role | **Yes** |
| `RESEND_API_KEY` | optional (emails are printed to the console) | Resend → API Keys | **Yes** |
| `DEFAULT_FROM_EMAIL` | — | e.g. `Kararsızım <onboarding@resend.dev>` | No |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | — | only if you use SMTP instead of Resend | Password **yes** |

## Supabase

1. **Connection string:** Dashboard → project → **Connect** → **Transaction pooler** (port **6543**).
   If the password contains `@ : / ? # %`, URL-encode it (e.g. `@` → `%40`).
2. **Run migrations from your machine** (not during the build):
   ```bash
   read -s DATABASE_URL && export DATABASE_URL   # paste the pooler URL
   python manage.py migrate
   python manage.py createsuperuser
   unset DATABASE_URL
   ```
   If the Transaction pooler causes problems with migrations, use the **Session pooler** URL (port 5432).
3. **Row Level Security:** Django connects as the table owner, so RLS does not affect it. To keep the
   auto-generated Supabase REST API (anon key) away from the data, RLS is enabled on every `public` table with
   **no policies**. An event trigger (`ensure_rls`) turns RLS on for every new table automatically.
   To check manually in the SQL Editor:
   ```sql
   -- any table without RLS?
   select tablename from pg_tables where schemaname = 'public' and not rowsecurity;

   -- enable RLS on all public tables
   do $$
   declare t record;
   begin
     for t in select tablename from pg_tables where schemaname = 'public' loop
       execute format('alter table public.%I enable row level security', t.tablename);
     end loop;
   end $$;
   ```
4. **Option images:** create a public bucket named `option-images` (allowed type `image/webp`, max 2 MB).
   Only the server uploads and deletes files using the service/secret key. The bucket has no policies, so the anon key
   cannot upload or list files.

## Deploying to Vercel

- Vercel detects Django through `manage.py`; `WSGI_APPLICATION` is the entry point.
- `collectstatic` runs during the build, and `/static/` is served from the Vercel CDN.
- `vercel.json` only sets the function region to **fra1 (Frankfurt)**, close to the database.
- The Python version comes from `.python-version` (3.12), and dependencies from `requirements.txt`.
- Every push to `main` triggers a production deploy. Run new migrations against Supabase **before** pushing.
- Set the environment variables under Vercel → project → **Settings → Environment Variables**.

## Security notes

- Secrets live only in environment variables, and `.env` is gitignored.
- CSRF protection on every form. In production: HTTPS redirect, secure session/CSRF cookies, and no wildcard hosts.
- The voter cookie is HttpOnly and SameSite=Lax. Duplicate votes are prevented by database constraints.
- Database-backed rate limiting. Behind Vercel, the client IP is taken from `X-Forwarded-For`.
- Uploaded images are re-encoded with Pillow (size and format checked) before storage.
