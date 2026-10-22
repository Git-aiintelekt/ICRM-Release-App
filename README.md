# iCRM Release Notes (Django)

The Release Notes management app: add, edit, publish and email iCRM release notes.
It replaced `python-backend` (FastAPI, now retired). It uses the **same database, tables, users and passwords**,
and serves the **same React UI**.

| | |
|---|---|
| Framework | Django 6.1, Django REST Framework, React 19 (Vite) |
| Database | MySQL `react_database` (5.5.62) through a small compatibility backend, `config/db_backends/mysql55` |

---

## Local development

Needs Python 3.14, Node.js 24 and the local MySQL server (`C:\Program Files\MySQL\MySQL Server 5.5`, already running as a Windows service).

### First-time setup (after cloning)

```powershell
git clone https://github.com/Git-aiintelekt/ICRM-Release-App.git
cd ICRM-Release-App
```

1. **Python environment and packages**
   ```powershell
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```
2. **Settings (`.env`)**: not in git, so create it from the template and fill in `DB_PASSWORD`,
   `DJANGO_SECRET_KEY` and `APP_SECRET_KEY` (or copy an existing `.env` from a teammate's or an older checkout).
   ```powershell
   copy .env.example .env
   mkdir media\release-images
   ```
   Screenshots are saved under `UPLOAD_DIR` (default `media\` in this folder).
3. **Build the React frontend (required).** Django serves the UI from `frontend\dist`, which isn't in git.
   Without it, http://localhost:8000 shows "The React app isn't built yet".
   ```powershell
   cd frontend
   npm ci
   npm run build
   cd ..
   ```
4. **Check the setup.** It should print `System check identified no issues`.
   ```powershell
   .venv\Scripts\python manage.py check
   ```
5. **Database tables**: only on a new, empty database. `react_database` already has them.
   ```powershell
   .venv\Scripts\python manage.py migrate   # creates Django's own tables; existing tables untouched
   ```

### Every time

```powershell
.venv\Scripts\python manage.py runserver 8000
```

Open http://localhost:8000. Stop with `Ctrl+C`. If port 8000 is in use, run `runserver 8001`.

### After `git pull`

| What changed | Run |
|---|---|
| Files in `frontend\` | `cd frontend; npm run build; cd ..` (`npm ci` first if `package.json` changed) |
| `requirements.txt` | `.venv\Scripts\pip install -r requirements.txt` |
| New files in `*/migrations/` | `.venv\Scripts\python manage.py migrate` |
| Only other Python files | Nothing, just restart the server |

- React app: http://localhost:8000 (left sidebar: dashboard, release notes, Jira, Bitbucket, commits & PRs, audit logs,
  import/export, settings / integrations)
- Django Admin: http://localhost:8000/admin/ (switched off by default, see below)

**Django Admin is switched off by default.** `/admin/` returns 404, and the React app hides its links to it (the
sidebar's **Administration** section). The React app's own `/api/admin/...` endpoints are not affected. To switch it on, do both:

1. Server: set `ENABLE_DJANGO_ADMIN=true` in `.env` and restart Django.
2. React app: set `SHOW_ADMIN_LINKS = true` in `frontend/src/lib/navigation.js`, then `cd frontend; npm run build`.

**Working on the React UI:** keep Django running, then in a second terminal run `cd frontend; npm run dev` and open
http://localhost:5173. Vite reloads on every save and passes `/api`, `/admin` and `/static` through to Django on port 8000.

**Admin users.** Every `FULLADMIN` member can sign in to both the React app and Django Admin with the same email and
password (when Django Admin is switched on). Signing in to the React app also signs you in to Admin.

```powershell
.venv\Scripts\python manage.py createsuperuser        # new admin: enter their email as the username
.venv\Scripts\python manage.py changepassword <username>
```

In Admin → Users you can also add users, enable or disable them, and grant or revoke `FULLADMIN` / `JIRA_VIEWER`.
The React Settings page does the same. Accounts are disabled rather than deleted, because uploads and the
audit log refer to them.

## Database

**Database:** `react_database` on `localhost:3306` (set by `DB_*` in `.env`). **Every existing table is used as it is:**
the Django models are `managed = False` and use `db_table`, so Django never creates, alters or drops them.

| Existing table | Django model | Admin |
|---|---|---|
| `release_version` | `releases.ReleaseVersion` | Release versions: items and gallery screenshots inline |
| `release_item` | `releases.ReleaseItem` | Release items: search, filter by version and category, screenshots inline |
| `release_image` | `releases.ReleaseImage` (file in `<UPLOAD_DIR>/release-images/`) | Screenshots: upload, caption, preview |
| `release_upload` | `releases.ReleaseUpload` | Word document uploads (read-only) |
| `jira_issue` | `jira.JiraIssue` | Jira issues: seed and table entries inline |
| `jira_seed_entry` | `jira.JiraSeedEntry` | (inline) |
| `jira_table_entry` | `jira.JiraTableEntry` | (inline) |
| `app_user` | `accounts.AppUser`, the Django user model (`password_hash`, `is_enabled`, `last_login_at` mapped by column) | Users |
| `app_user_security_group` | `accounts.AppUserSecurityGroup` (`FULLADMIN`, `JIRA_VIEWER`, with from/thru dates) | (inline on Users) |
| `audit_log` | `audit.AuditLog` | Audit log (read-only) |
| `messages` | not mapped (demo table, unused) | |

**New tables** created by `python manage.py migrate`: Django's own (`django_migrations`, `django_session`,
`django_admin_log`, `django_content_type`, `auth_permission`, `auth_group`, `auth_group_permissions`) and
**`revoked_token`** / **`user_token_cutoff`** (signed-out tokens, see [Sign-in security](#sign-in-security)).

```powershell
.venv\Scripts\python manage.py migrate                 # apply migrations
.venv\Scripts\python manage.py showmigrations          # what is applied
.venv\Scripts\python manage.py makemigrations          # only after changing a model
```

**Passwords** keep python-backend's PBKDF2 format (`accounts/hashers.py`), so a password set in either app works in both.
**Sign-in tokens** use the same format and `APP_SECRET_KEY`, so they work in both too.

**Backup:** a full dump taken before Django first touched the database is in
`backups/react_database_before_django_20260930_1435.sql`. Restore it with `mysql -uroot -p react_database < <file>`.

**MySQL 5.5:** Django 6 officially supports MySQL 8.0.11+. `config/db_backends/mysql55` lowers the version check and
creates `DATETIME` columns without fractional seconds, for Django's own tables only. After upgrading the server to
MySQL 8, set `ENGINE` to `django.db.backends.mysql` in `config/settings/base.py`.

## API

The same URLs and JSON as python-backend, so the React app didn't change (`config/urls.py`):

| FastAPI endpoint | Django view | Access |
|---|---|---|
| `GET /api/releases`, `/api/releases/{id}`, `/api/releases/version/{v}` | `releases.api` | public |
| `GET /api/release-images/{id}` | `releases.api.release_image` | public |
| `POST /api/auth/register`, `/login`, `/forgot-password`, `/reset-password`; `GET /api/auth/me` | `accounts.api` | public / signed in |
| (new) `POST /api/auth/logout` | `accounts.api.logout` | ends the Django Admin session too |
| `GET /api/jira-issues`, `/api/jira-issues/{id}` | `jira.api` | FULLADMIN or JIRA_VIEWER, audited |
| `POST /api/admin/releases/parse`, `POST /api/admin/releases` | `releases.api.parse_upload`, `publish` | FULLADMIN |
| `PATCH/DELETE /api/admin/releases/{id}`, `POST .../{id}/items`, `POST .../{id}/images` | `releases.api` | FULLADMIN |
| `PATCH/DELETE /api/admin/release-items/{id}`, `/api/admin/release-images/{id}` | `releases.api` | FULLADMIN |
| `GET /api/admin/users`, `PATCH /api/admin/users/{id}`, `GET /api/admin/audit-log` | `accounts.api`, `audit.api` | FULLADMIN |
| (new) `GET /api/admin/audit-log.csv` (same filters, up to 10,000 entries) | `audit.api.audit_log_csv` | FULLADMIN |
| (new) `GET /api/health`, `GET /api/auth/options`, `POST /api/auth/logout-all` | `config.health`, `accounts.api` | public / public / signed in |
| `GET/POST/DELETE /api/messages` | not ported (unused demo) | |
| `GET /api/integrations/status`, `/dashboard`, `/jira/{filters,summary,issues,releases}`, `/bitbucket/repositories[/{slug}/{branches,commits,pullrequests}]` | `integrations.api` | FULLADMIN or JIRA_VIEWER (denials audited) |
| `POST /api/integrations/refresh` | `integrations.api.refresh` | FULLADMIN, audited as `INTEGRATION_REFRESH` |

## Sign-in security

| What | How | Settings (`.env`) |
|---|---|---|
| Rate limits | Sign-in, sign-up and password-reset requests are counted per client IP; over the limit the API answers 429 | `THROTTLE_LOGIN` (10/min), `THROTTLE_REGISTER` (5/hour), `THROTTLE_PASSWORD_RESET` (5/hour), `NUM_PROXIES` (set 1 behind IIS / nginx) |
| Account lockout | After 5 failed sign-ins to one account (from any IP) its sign-in is refused for 15 minutes, audited as a failed sign-in with "locked". A password reset unlocks it | `LOGIN_LOCKOUT_ATTEMPTS`, `LOGIN_LOCKOUT_SECONDS` |
| Sign out | **Sign out** ends that device's token at once (`revoked_token`). **Sign out everywhere** (header) ends every device's (`user_token_cutoff`), audited as `LOGOUT_EVERYWHERE` | |
| Password change, disabled account | A password change (reset link, Django Admin, `changepassword`) and disabling an account end every earlier sign-in | |
| Self sign-up | Limited to `@aiintelekt.com` addresses by default; can be switched off (the sign-in page then says to ask an administrator) | `ALLOW_REGISTRATION`, `REGISTRATION_EMAIL_DOMAINS` (empty = any domain) |
| Content Security Policy | Report-only: browsers log what it would block in the developer console. Before enforcing it, move the inline theme script in `frontend/index.html` into a file | `CSP_ENFORCE=true` |
| Health check | `GET /api/health`: 200 `{"status": "ok"}` or 503 when the database doesn't answer, for the reverse proxy and uptime monitors | |

The lockout and the rate limits are kept in the in-process cache: restarting Django clears them, and they assume one
waitress process (move the cache to Redis before running several). Tokens issued by python-backend still work here
until the user's next password change or "Sign out everywhere"; signing out of python-backend doesn't end them.

## Jira and Bitbucket (live data)

The Dashboard, Jira Tickets (Live tab), Bitbucket Repositories and Commits & Pull Requests pages read Jira Cloud
(REST v3) and Bitbucket Cloud (API 2.0) **through Django** (`integrations/`). Tokens live only in `.env`; no response
contains them. Without credentials each page says which `.env` values are missing, and the rest of the app is unaffected.

- **Configure:** fill the `JIRA_*` and `BITBUCKET_*` block of `.env` (see `.env.example`), restart Django, then
  Settings → Integrations → *Refresh and test connections*.
- **Counts:** open = status category not Done; resolved / closed = Done **and** a status in `JIRA_RESOLVED_STATUSES` /
  `JIRA_CLOSED_STATUSES` (anything else Done is shown as "other done"); bugs = `JIRA_BUG_ISSUE_TYPES`. Configured names
  that don't exist in the projects are ignored and reported, never sent in JQL.
- **Release-wise summaries:** listed under the fix version names Jira actually has. They are tied to this app's versions
  only through `JIRA_FIX_VERSION_MAP`; name matches are shown as unconfirmed hints.
- **Commits → Jira:** keys of the configured projects in commit messages / PR titles are looked up live in Jira. A commit
  never marks an issue resolved.
- **Repositories:** only those in `BITBUCKET_REPOSITORIES` can be read (currently `icrm-base-framework-master` and
  `icrm-b2b-master`); add `sql_group` there to show it too.
- **Scope (Settings → Integrations → *What the screens show*):** admins add branches per repository and Jira fix
  versions. With branches added, the Bitbucket page lists only those branches, Commits & Pull Requests and the Dashboard
  show only commits on them and pull requests into or out of them, and the branch box becomes a list of those
  branches. With fix versions added, the Dashboard counts, the release-wise table and the Jira ticket list cover only
  those versions (this overrides `JIRA_FIX_VERSION_MAP`). It applies to every user; with nothing added, everything is
  shown. Each name is checked against Bitbucket / Jira before it's saved, and changes are audited as `INTEGRATION_SCOPE`.
- **Caching:** answers are kept in memory for `INTEGRATION_CACHE_SECONDS` (default 300); the dashboard is one request.
  Nothing from Jira or Bitbucket is copied into the database. The only table is `integration_scope` (the scope above,
  created by `manage.py migrate`).

## Email

Password reset and "Email / download" on a release (admins) send email. `EMAIL_MODE` in `.env` picks how:

| `EMAIL_MODE` | What happens | Used for |
|---|---|---|
| `file` | Each email is saved as an `.eml` file in `MAIL_FILE_DIR` (default `sent_emails/`). Nothing is sent. | Local development (default) |
| `smtp` | Sent through `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY` (`starttls` / `ssl` / `none`), `SMTP_USER`, `SMTP_PASSWORD`. | Testing with Mailtrap; production |
| `console` | Printed in the server console. | Quick checks |

`MAIL_FROM` is the sender (`Name <address>`); `SMTP_TIMEOUT` (seconds, default 20) is optional. Without `EMAIL_MODE`,
the older rule applies: `SMTP_HOST` set → smtp, else `MAIL_FILE_DIR` set → file, else console. A wrong value
(unknown mode, `smtp` without `SMTP_HOST`, bad port or security) stops Django at startup with a message naming the
setting; passwords are never printed.

**Test the settings** (after editing `.env`; restart Django for the web app to use them):

```
.venv\Scripts\python manage.py send_test_email you@example.com
```

It prints the mode, host and user, only whether a password is set, and the server's error if sending fails.

**Local testing with Mailtrap** (mailtrap.io → Email Testing → My Inbox → SMTP tab): every email lands in the
Mailtrap web inbox and never reaches a real mailbox, so any recipient is safe.

```
EMAIL_MODE=smtp
SMTP_HOST=sandbox.smtp.mailtrap.io
SMTP_PORT=2525
SMTP_SECURITY=starttls
SMTP_USER=<from the SMTP tab>
SMTP_PASSWORD=<from the SMTP tab>
```

Set `EMAIL_MODE=file` to go back; the SMTP values can stay.

**Production (infrastructure team).** The server's `.env` is separate from any developer's: set `EMAIL_MODE=smtp`,
the `SMTP_*` values of the company relay or mailbox, and a `MAIL_FROM` that account may send as. Notes for
Microsoft 365 (aiintelekt.com mail):
- `smtp.office365.com:587` with a mailbox and password needs Authenticated SMTP enabled for that mailbox, the
  mailbox excluded from MFA / security defaults, and Basic auth for SMTP still allowed in the tenant (Microsoft is
  retiring it). Sending as another address (e.g. `no-reply@`) needs "Send As" permission on it.
- Direct Send (`aiintelekt-com.mail.protection.outlook.com:25`, no sign-in) only delivers to @aiintelekt.com
  recipients and is refused from IPs on Spamhaus lists (most office/home connections). From a server with a fixed
  IP, add that IP to the domain's SPF record so mail isn't marked as spoofed.

## Build

| What | Command | Output | When |
|---|---|---|---|
| React app served by Django | `cd frontend; npm run build` | `frontend/dist/` | after UI changes |
| Django Admin static files (production only) | `.venv\Scripts\python manage.py collectstatic` | `staticfiles/` | after upgrading Django |

## Editing workflow

```
Run Django (runserver locally, or the staging Django service)
  ↓ edit in the React UI (inline editing, .docx upload) or, when switched on, Django Admin
  ↓ saved to react_database immediately
```

## Environments

| | Development | Staging / production |
|---|---|---|
| Settings | `DJANGO_SETTINGS_MODULE=config.settings.dev` (default in `manage.py`) | `config.settings.prod` (default in `config/wsgi.py`) |
| Server | `manage.py runserver` | `.venv\Scripts\waitress-serve --listen=127.0.0.1:8000 config.wsgi:application`, behind IIS/nginx with https |
| DEBUG | on | off; `DJANGO_SECRET_KEY` and `APP_SECRET_KEY` required |
| Required `.env` | `DB_*` | `DB_*`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `APP_BASE_URL`, `SMTP_*`; optional `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` |
| Build steps | `npm run build` | `npm ci; npm run build` in `frontend/`, then `migrate` and `collectstatic` |
| Email | printed in the console | SMTP (`SMTP_HOST` …) |

Secrets live only in `.env`, which is git-ignored. `.env.example` lists every setting.

## Testing

```powershell
# Every API endpoint against the real database, inside a transaction that is rolled back (nothing is kept):
.venv\Scripts\python manage.py shell -c "exec(open('scripts/smoke_api.py', encoding='utf-8').read())"
.venv\Scripts\python manage.py check
# Unit tests: sign-in security, audit export, health, email, releases, and Jira/Bitbucket with MOCKED responses
# (no network, no database):
.venv\Scripts\python manage.py test
```

`bitbucket-pipelines.yml` runs the unit tests, `check`, the migration check, oxlint and the React build on every push
and pull request once the project is in a Bitbucket repository.

Verified during the migration (2026-09-30), against the real data (6 versions, 481 changes, 4 screenshots, 229 Jira issues):
- **Admin:** every page loads.
- **API:** 41/41 checks passed. `/api/releases` matches python-backend's response.
- **React through Django:** 16/16 browser checks passed (history, search, sign-in, inline edit, settings, Jira, one sign-in for Admin).

## python-backend (retired)

This app has replaced `python-backend` (FastAPI) and `my-react-app`. Both folders have been deleted.
`frontend\` is the React source, and screenshots are stored in `media\release-images\` (`UPLOAD_DIR` in `.env`).
