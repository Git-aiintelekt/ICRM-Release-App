# Release Manager – Staging deployment steps

Ten steps take a Windows staging server from an empty folder to a running Release Manager behind https. Steps 1 to 8
are for the infrastructure team; steps 9 and 10 are done with the release manager.

The same guide is shared as a document; this file is the one kept with the code, so it always matches this version.
Rules for Claude Code are in [`CLAUDE.md`](../CLAUDE.md); the whole app is described in the [README](../README.md).

## Before you start

The server needs the software below, a MySQL account, and a host name with an https certificate.

| Item | Needed | Notes |
| --- | --- | --- |
| Windows server | Windows Server or Windows 10/11 | Commands below are PowerShell |
| Git | Any recent version | Read access to `https://github.com/Git-aiintelekt/ICRM-Release-App` |
| Python | **3.14** (with the `py` launcher) | Packages come from `requirements.txt` |
| Node.js | **24** (with npm) | Only to build the web pages; not used at run time |
| MySQL | **5.5** (the app's compatibility backend targets it) | A user that may create a database, or an empty database made for the app |
| Web server | IIS (with URL Rewrite and ARR) or nginx | Terminates https and forwards to the app on `127.0.0.1:8000` |
| Host name + certificate | e.g. `release-notes.staging.example.com` | Used in `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `APP_BASE_URL` |
| Service wrapper | e.g. NSSM, or a Task Scheduler task at startup | Keeps the app running and restarts it |
| SMTP account | Company relay or mailbox | Password reset and release emails |
| Jira and Bitbucket API tokens | Optional at install | Can be entered later in the app (step 9) |

The app keeps no state on the server besides the database and the upload folder (`UPLOAD_DIR`). Back both up.

## Step 1: Get the code

Clone into the folder the app will run from (the examples use `D:\apps`). Use `main` once the products pull request is
merged; until then use the branch `products-and-clients`.

```powershell
cd D:\apps
git clone https://github.com/Git-aiintelekt/ICRM-Release-App.git
cd ICRM-Release-App
git checkout main          # or: git checkout products-and-clients
```

## Step 2: Python environment and packages

```powershell
py -3.14 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

This installs Django 6.1.1, waitress, whitenoise and the MySQL driver into `.venv` only.

## Step 3: Settings for staging (`.env`)

`.env` is never in git. Create it from the template, then set the values below.

```powershell
copy .env.example .env
notepad .env
```

| Setting | Staging value | Why |
| --- | --- | --- |
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` | DEBUG off, secure cookies, secrets required |
| `DJANGO_SECRET_KEY` | a long random text | Django's own secret |
| `APP_SECRET_KEY` | a different long random text; **never change it later** | Signs sign-in tokens and encrypts the Jira / Bitbucket tokens saved in the app |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | the staging MySQL | A database name that doesn't exist yet is created in step 5 |
| `ALLOWED_HOSTS` | `release-notes.staging.example.com` | Host names the app answers to (comma-separated) |
| `CSRF_TRUSTED_ORIGINS` | `https://release-notes.staging.example.com` | Same, with `https://` |
| `APP_BASE_URL` | `https://release-notes.staging.example.com` | Links in password-reset emails |
| `NUM_PROXIES` | `1` | The app sits behind one proxy (IIS / nginx), so rate limits use the real client address |
| `UPLOAD_DIR` | e.g. `D:/data/release-manager` | Screenshots and videos; keep it outside the code folder and back it up |
| `EMAIL_MODE` | `smtp` | Plus `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM` |
| `PUBLIC_RELEASE_NOTES` | `true` only if customers should open public links | Off by default |
| `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` | `true`, `31536000` | Only once the site works over https |
| `JIRA_*`, `BITBUCKET_*` | leave empty, or fill in | Can be entered in the app instead (step 9) |

Make each secret with:

```powershell
.venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Keep `.env` readable only by the service account and administrators: it holds the database and SMTP passwords.

### Where screenshots and videos are stored

Every upload is saved as a file under `<UPLOAD_DIR>\release-images\`, with a random name (e.g.
`0b1a38477adb4d0a8c54088b165f354a.png`). The database's `release_image` table keeps only the file name, type, caption
and which version or change it belongs to. Without `UPLOAD_DIR`, files go into `media\` inside the code folder, so
always set it on staging.

```
UPLOAD_DIR=D:/data/release-manager
```

- The app creates the folder, and its `release-images` subfolder, on the first upload; it doesn't need to exist.
- Use forward slashes. A network share works too (e.g. `UPLOAD_DIR=//fileserver/release-manager`) when the service
  account can read and write it.
- Restart the app after changing `.env`; settings are read at start.
- Deleting a screenshot, change or version also deletes its files.

**Space:** screenshots are checked to be at most 5 MB, videos at most 25 MB. These are rough estimates; real sizes
depend on what people upload.

| Kind | Typical size | 1,000 of them |
| --- | --- | --- |
| Screenshot (PNG / JPEG) | 0.2 to 1 MB | about 0.2 to 1 GB |
| Short video (MP4) | 1 to 5 MB | about 1 to 5 GB |

**Checklist:**

- [ ] Create the folder on a data drive or share, outside the code folder (e.g. `D:\data\release-manager`).
- [ ] Give the app's service account write permission on it.
- [ ] Set `UPLOAD_DIR` in `.env`, then restart the app.
- [ ] Add the folder to the backup, next to the database: a database backup alone keeps the captions but loses the
      pictures.

**Moving existing files** to a new folder: stop the app, copy them, set the new `UPLOAD_DIR`, start the app. The
database stores only file names, so nothing in it changes.

```powershell
robocopy <old UPLOAD_DIR>\release-images D:\data\release-manager\release-images /E
```

## Step 4: Build the web pages

Django serves the React app from `frontend\dist`, which isn't in git.

```powershell
cd frontend
npm ci
npm run build
cd ..
```

The build ends with `✓ built in …` and creates `frontend\dist\index.html`.

## Step 5: Database setup

**If the database already has data, back it up first.** Then run `setup`, which does everything the database needs:

```powershell
# Only for an existing database:
& "C:\Program Files\MySQL\MySQL Server 5.5\bin\mysqldump.exe" -u<user> -p --single-transaction <DB_NAME> > D:\backups\release_manager_before_deploy.sql

.venv\Scripts\python manage.py setup
```

`setup` is safe to run again; it only adds what is missing. It:

1. creates the database named in `DB_NAME` if it doesn't exist,
2. runs every migration, including the products migrations `releases/0002` to `0004` (iCRM, IUC and Sales Audit are
   created; existing versions and repositories become iCRM's),
3. marks the Latest version of each product,
4. creates the default admin **`releasemanager` / `releasemanager`** when there are no users.

Expected output on a new database:

```
Created the database <DB_NAME>.
Tables are up to date.
Created the default admin: releasemanager / releasemanager. Sign in and choose a new password; nothing else works for this account until you do.
```

The default admin can do nothing but change its password until it does (step 9).

### How the database is created

There is no SQL file to import: `setup` builds everything (`accounts/management/commands/setup.py`).

1. **Connect** to MySQL with `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` and `DB_NAME`. Any error other than
   "unknown database" (wrong password, MySQL stopped) ends here with *Can't connect to MySQL with the DB_\* settings in
   .env*.
2. **Create the database** when MySQL reports it doesn't exist: `CREATE DATABASE IF NOT EXISTS <DB_NAME> CHARACTER SET
   utf8`. The name may contain only letters, digits and underscores. The character set is `utf8`, because MySQL 5.5's
   index size limit can't fit `utf8mb4`.
3. **Create the tables** by running each migration once (recorded in `django_migrations`):

| Migration | Creates |
| --- | --- |
| Django's own | `django_migrations`, `django_session`, `django_content_type`, `auth_*`, `django_admin_log` |
| `accounts`, `audit`, `jira`, `releases` 0001 | The original tables (`app_user`, `app_user_security_group`, `audit_log`, `release_version`, `release_item`, `release_image`, `release_upload`, `jira_*`) with `CREATE TABLE IF NOT EXISTS`, so existing tables and data are kept |
| `accounts` later migrations | `revoked_token`, `user_token_cutoff` (signed-out tokens) |
| `integrations` | `integration_scope`, `integration_credential` |
| `releases` 0002 | `release_product`, `release_product_repository`; iCRM, IUC, Sales Audit; `release_version.product_id`; the `.env` repositories linked to iCRM |
| `releases` 0003, 0004 | `release_product.parent_id` (clients) and `release_product.public_key` (one random key per product) |

4. **Mark Latest** for each product (nothing to do on an empty database), then **create the default admin** when there
   are no users.

| Situation | What `setup` does |
| --- | --- |
| `DB_NAME` doesn't exist | Creates the database, every table, the three products and the default admin |
| An existing database from an older version | Adds only the missing tables and migrations; data stays, and existing versions become iCRM's |
| Already up to date | Nothing; safe to run on every deployment |

**MySQL permission:** `DB_USER` needs the right to create a database and tables. If staging's database user may not
create databases, the DBA creates an empty one once and grants the user rights on it; `setup` then only creates the
tables.

```sql
CREATE DATABASE release_manager CHARACTER SET utf8;
GRANT ALL PRIVILEGES ON release_manager.* TO 'release_user'@'localhost';
```

Use that name as `DB_NAME` in `.env`.

## Step 6: Static files

```powershell
.venv\Scripts\python manage.py collectstatic --noinput
```

This copies Django's own files into `staticfiles\`. The React app in `frontend\dist` needs no copy: whitenoise serves
both from the app itself, so the web server only forwards requests.

## Step 7: Run the app as a Windows service

The app runs under **waitress**, listening only on the local address. Never use `manage.py runserver` on staging.

**Test it by hand first:**

```powershell
.venv\Scripts\waitress-serve --listen=127.0.0.1:8000 config.wsgi:application
```

In a second window, `curl http://127.0.0.1:8000/api/health` must answer `{"status":"ok","database":"ok"}`. Stop it with
`Ctrl+C`.

**Then install it as a service.** Example with NSSM (any service wrapper works the same way):

```powershell
nssm install ReleaseManager D:\apps\ICRM-Release-App\.venv\Scripts\waitress-serve.exe "--listen=127.0.0.1:8000 --threads=8 config.wsgi:application"
nssm set ReleaseManager AppDirectory D:\apps\ICRM-Release-App
nssm set ReleaseManager AppStdout D:\logs\release-manager\app.log
nssm set ReleaseManager AppStderr D:\logs\release-manager\app.log
nssm set ReleaseManager AppRotateFiles 1
nssm set ReleaseManager Start SERVICE_AUTO_START
nssm start ReleaseManager
```

- **Working directory** must be the code folder: the app reads `.env` from there.
- **Logs** go to the console, so the wrapper must capture standard output and errors (`AppStdout` / `AppStderr`).
- **Service account:** needs read access to the code folder and `.env`, and write access to `UPLOAD_DIR` and the log
  folder.
- **One process only:** sign-in lockout and rate limits live in the process's memory. Use threads, not several
  processes.

## Step 8: https in front (IIS or nginx)

The web server takes https on 443 and forwards everything to `http://127.0.0.1:8000`, keeping the host name and
telling the app the request was https.

| Requirement | Why |
| --- | --- |
| Forward the original `Host` header | Must match `ALLOWED_HOSTS`, or the app answers 400 |
| Send `X-Forwarded-Proto: https` | The app trusts it to know the request was secure (secure cookies, CSRF) |
| Send `X-Forwarded-For` | Rate limits and the audit log use the client's address (`NUM_PROXIES=1`) |
| Allow request bodies up to **26 MB** | Videos are up to 25 MB |
| Redirect http to https | Or set `SECURE_SSL_REDIRECT=true` |

**nginx:**

```nginx
server {
    listen 443 ssl;
    server_name release-notes.staging.example.com;
    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    client_max_body_size 26m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 120s;
    }
}
```

**IIS:** install **URL Rewrite** and **Application Request Routing (ARR)**, enable the proxy in ARR (Server Proxy
Settings, with **Preserve host header**), then add a site for the host name with its certificate and a reverse-proxy
rule to `http://127.0.0.1:8000/{R:1}`. Allow the server variable `HTTP_X_FORWARDED_PROTO` and set it to `https` on the
rule. IIS's default request limit (30 MB) already covers 25 MB videos.

**Long requests:** drafting release notes from Bitbucket reads many pages of commits and Jira issues, so a large
release takes noticeably longer than other pages. Keep the proxy timeout at 120 seconds or more.

**Public page only from outside (optional):** if customers should reach public links but nothing else, let the
internet reach only `/public/`, `/assets/`, `/favicon.ico` and `/api/public/`, and keep the rest internal.

## Step 9: First sign-in and configuration

Do this once, together with the release manager, at `https://<host name>`.

1. **Change the default password.** Sign in as `releasemanager` / `releasemanager`. The app asks for a new password (at
   least 8 characters) before anything else works.
2. **Connect Jira and Bitbucket** (if not set in `.env`): **Settings / Integrations → Integrations → Jira and Bitbucket
   connection**. Enter the Jira site URL, email and API token, and the Bitbucket workspace, email and API token, then
   **Save** and **Refresh and test connections**. Tokens are stored encrypted and never shown again.
3. **Set up products and clients:** **Settings → Products**. iCRM, IUC and Sales Audit exist already; add each IUC client
   and link its Bitbucket repository.
4. **Grant access:** **Settings → Users & access**. Give `FULLADMIN` (admin) or `JIRA_VIEWER` (Jira and Bitbucket
   pages) to the people who need it. Self sign-up is limited to `@aiintelekt.com` addresses unless `.env` says
   otherwise.
5. **Check email:** on a server shell, `.venv\Scripts\python manage.py send_test_email you@aiintelekt.com` prints the
   mode and host and whether sending worked.

## Step 10: Verify

| Check | How | Expected |
| --- | --- | --- |
| App is up | `curl http://127.0.0.1:8000/api/health` on the server | `{"status":"ok","database":"ok"}` (503 = database unreachable) |
| Through the proxy | Open `https://<host name>/api/health` | the same, over https |
| Configuration | `.venv\Scripts\python manage.py check --deploy` | no errors (warnings about HSTS are expected until step 3's https settings are on) |
| Migrations | `.venv\Scripts\python manage.py showmigrations releases` | `[X]` on 0001 to 0004 |
| Sign-in | Sign in with the new admin password | Dashboard opens |
| Integrations | Dashboard → Integration health | Jira and Bitbucket **Connected** |
| Products | Header → Product dropdown | iCRM, IUC, Sales Audit (and the clients added) |
| Public link (if switched on) | Settings → Products → Copy, open in a private window | Release notes without Jira numbers, no sign-in |
| Uploads | Publish a test version with a screenshot, then delete it | Screenshot shows; file appears in `UPLOAD_DIR\release-images` |

## Every later deployment

After the first install, each update is the same seven steps, run from the code folder:

```powershell
# 1. Back up the database and the upload folder
& "C:\Program Files\MySQL\MySQL Server 5.5\bin\mysqldump.exe" -u<user> -p --single-transaction <DB_NAME> > D:\backups\release_manager_<date>.sql
# 2. Note the running version, for a rollback
git rev-parse HEAD
# 3. Get the new code
git pull
# 4. Python packages (only changes something when requirements.txt changed)
.venv\Scripts\pip install -r requirements.txt
# 5. Web pages
cd frontend; npm ci; npm run build; cd ..
# 6. Database and static files
.venv\Scripts\python manage.py setup
.venv\Scripts\python manage.py collectstatic --noinput
# 7. Restart
nssm restart ReleaseManager
```

Then repeat the first two checks of step 10. Users may need a hard refresh (Ctrl+Shift+R) to load the new pages.

**Rollback:**

1. `nssm stop ReleaseManager`
2. `git checkout <the version noted in step 2>`, then rebuild the web pages (step 5 above).
3. If the update ran new migrations, restore the backup: `mysql -u<user> -p <DB_NAME> < D:\backups\release_manager_<date>.sql`.
4. `nssm start ReleaseManager`

## Troubleshooting

| Problem | Cause | Fix |
| --- | --- | --- |
| Service stops at once; log says `Set DJANGO_SECRET_KEY and APP_SECRET_KEY` | Secrets missing in `.env` | Set both (step 3) |
| `Bad Request (400)` for every page | Host name not in `ALLOWED_HOSTS`, or the proxy doesn't forward `Host` | Add the name; turn on "preserve host" (IIS) or `proxy_set_header Host $host` (nginx) |
| Sign-in or saving fails with a CSRF error | `CSRF_TRUSTED_ORIGINS` missing, or `X-Forwarded-Proto` not sent | Set `https://<host name>`; send the header (step 8) |
| Endless redirect after `SECURE_SSL_REDIRECT=true` | Proxy doesn't send `X-Forwarded-Proto: https` | Send the header, or turn the redirect off and redirect in the proxy |
| Page says "The React app isn't built yet" | `frontend\dist` missing | Step 4 |
| `/api/health` answers 503 | MySQL not reachable | Check the MySQL service and `DB_*` |
| `setup` says it can't connect to MySQL | Wrong `DB_*`, or the user can't create databases | Fix `.env`, or create the empty database and grant the user rights on it |
| A migration fails with "Unknown table 'check_constraints'" | A Django schema change MySQL 5.5 can't run | Report it to the developers; restore the backup if the run stopped halfway |
| Video upload fails | Proxy body limit below 26 MB | `client_max_body_size 26m` (nginx); IIS default is enough |
| Jira / Bitbucket "not configured" | No tokens yet | Step 9, item 2 |
| Saved Jira / Bitbucket tokens stopped working | `APP_SECRET_KEY` changed | Enter the tokens again in Settings → Integrations |
| Emails don't arrive | `EMAIL_MODE` not `smtp`, or SMTP refused | `manage.py send_test_email you@aiintelekt.com` shows the reason |
| Public link says the notes aren't available | `PUBLIC_RELEASE_NOTES` off, or the link was replaced | Set it to `true` and restart; copy the current link from Settings → Products |

The log file from step 7 (`D:\logs\release-manager\app.log`) shows each error with its reason.
