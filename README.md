# Release Manager

Release Manager is the app for writing, publishing and sharing release notes for **iCRM, IUC, Sales Audit** and their
clients. Release notes come from a Word document, a CSV file, or straight from Bitbucket release branches and their
Jira issues. The app also shows live Jira ticket counts, Bitbucket repositories, branches, commits and pull requests
for the product you pick, and gives each product and client its own public release notes link.

| | |
|---|---|
| Backend | Django 6.1, Django REST Framework (Python 3.14) |
| Frontend | React 19, built with Vite, served by Django |
| Database | MySQL 5.5 through a small compatibility backend (`config/db_backends/mysql55`) |
| Integrations | Jira Cloud (REST v3) and Bitbucket Cloud (API 2.0), read through the server |

## Contents

1. [Key ideas](#key-ideas)
2. [Local development](#local-development)
3. [Using the app, page by page](#using-the-app-page-by-page)
4. [Products and clients](#products-and-clients)
5. [Public release notes](#public-release-notes)
6. [Release notes from Word, CSV or Bitbucket](#release-notes-from-word-csv-or-bitbucket)
7. [Screenshots and videos](#screenshots-and-videos)
8. [Jira and Bitbucket (live data)](#jira-and-bitbucket-live-data)
9. [Users, roles and sign-in security](#users-roles-and-sign-in-security)
10. [Email](#email)
11. [Database](#database)
12. [API](#api)
13. [Project structure](#project-structure)
14. [Settings (.env)](#settings-env)
15. [Environments and deployment](#environments-and-deployment)
16. [Testing](#testing)
17. [Troubleshooting](#troubleshooting)
18. [History](#history)

---

## Key ideas

| Term | Meaning |
|---|---|
| **Product** | iCRM, IUC, Sales Audit, or any product an admin adds. Picked in the header; every page then shows that product only. |
| **Client** | A client of a product (e.g. IUC → Client A). It has its **own repositories, branches and version numbers**. A product's own entry, shown as **Shared (all clients)**, is for things all its clients share; iCRM uses only that. |
| **Version** | One release of a product or client, e.g. 10.9.0: released or **Coming soon**, with a date, summary, highlights, known issues, upgrade notes and a screenshot gallery. A version number is unique per product or client, so Client A and Client B can each have 3.2.0. |
| **Change** | One item in a version: a category (New feature, Improvement, Bug fix, Security), a title, a description, an optional Jira ID and screenshots or videos. |
| **Latest** | The released version with the highest number, per product or client (10.10.0 > 10.9.0), set automatically after every publish, edit and delete (`releases/services/latest.py`). |
| **Release branch** | A Bitbucket branch named `release/icrm_release_<version>_<date>`, e.g. `release/icrm_release_10_9_0_18122025` is 10.9.0, started 18 Dec 2025. Used to draft release notes and count a release's Jira tickets. |
| **Roles** | `FULLADMIN` (admin, the release manager): everything. `JIRA_VIEWER`: release notes plus the Jira and Bitbucket pages. Everyone else who signs in: release notes only. |

---

## Local development

Needs Python 3.14, Node.js 24 and a running MySQL server (here `C:\Program Files\MySQL\MySQL Server 5.5`, running as a
Windows service). The database itself doesn't need to exist.

### First-time setup (after cloning)

In PowerShell. Steps 1 to 3 are needed once per checkout: git has no Python packages, no built web pages and no
`.env`.

```powershell
git clone https://github.com/Git-aiintelekt/ICRM-Release-App.git
cd ICRM-Release-App
```

1. **Python environment and packages**
   ```powershell
   py -3.14 -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```
2. **Settings (`.env`)**: not in git. Create it from the template (or copy one from a teammate) and fill it in.
   ```powershell
   copy .env.example .env
   notepad .env
   ```
   - `DB_PASSWORD`: the MySQL password of `DB_USER` (default `root`).
   - `DB_NAME`: the database to use. A name that doesn't exist yet (e.g. `release_notes`) gives a new, empty one,
     created on first start; `react_database` uses the existing data.
   - `DJANGO_SECRET_KEY` and `APP_SECRET_KEY`: two long random texts
     (`.venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(50))"`). Keep `APP_SECRET_KEY` once it's
     set: the Jira and Bitbucket tokens saved in the app are encrypted with it.
   - `JIRA_*` / `BITBUCKET_*`: optional; they can be entered in the app instead (step 5).

   Screenshots are saved under `UPLOAD_DIR` (default `media\` in this folder, created when needed). Every setting is
   listed in [Settings (.env)](#settings-env).
3. **Build the React frontend (required).** Django serves the UI from `frontend\dist`, which isn't in git. Without it,
   http://localhost:8000 shows "The React app isn't built yet".
   ```powershell
   cd frontend
   npm ci
   npm run build
   cd ..
   ```
4. **Start it.** MySQL must be running; nothing else needs preparing.
   ```powershell
   .venv\Scripts\python manage.py runserver 8000
   ```
   On start, Django runs `manage.py setup`, which:
   - creates the database named in `DB_NAME` if it doesn't exist,
   - creates or updates every table (`migrate`; on an existing database it adds only what is missing),
   - creates the products **iCRM, IUC and Sales Audit** (migration `releases/0002`),
   - creates the default admin **`releasemanager` / `releasemanager`** when there are no users yet,
   - marks the Latest version of every product.

   On a server started with waitress instead of `runserver`, run `.venv\Scripts\python manage.py setup` once after
   each deployment.
5. **Sign in and connect Jira and Bitbucket.** Open http://localhost:8000 and sign in as `releasemanager` /
   `releasemanager`. The app asks for a new password (at least 8 characters) before anything else works. Unless `.env`
   already has them, open **Settings / Integrations → Integrations → Jira and Bitbucket connection**, enter the Jira
   site URL, email and API token and the Bitbucket workspace, email and API token, save, and click **Refresh and test
   connections**.
6. **Set up products and clients** (optional): **Settings → Products**, or the **+** buttons in the header. See
   [Products and clients](#products-and-clients).
7. **First release notes.** A new database has none. Pick the product (and client) in the header, open
   **Import / Export**, then upload a Word document or CSV file, or use **Draft from Bitbucket**, review and
   **Publish**. Versions can be published in any order; Latest is always the highest released number.

### Every time

```powershell
.venv\Scripts\python manage.py runserver 8000
```

Open http://localhost:8000. Stop with `Ctrl+C`. If port 8000 is in use, run `runserver 8001`.

### After `git pull`

| What changed | Run |
|---|---|
| Files in `frontend\` | `cd frontend; npm run build; cd ..` (`npm ci` first if `package.json` changed), then hard-refresh the browser (Ctrl+Shift+R) |
| `requirements.txt` | `.venv\Scripts\pip install -r requirements.txt` |
| New files in `*/migrations/` | Nothing with `runserver` (it runs `setup`); on a waitress server `manage.py setup`. Take a backup first (see [Database](#database)) |
| Only other Python files | Nothing; `runserver` reloads by itself, waitress needs a restart |

### Working on the React UI

Keep Django running, then in a second terminal run `cd frontend; npm run dev` and open http://localhost:5173. Vite
reloads on every save and passes `/api`, `/admin` and `/static` through to Django on port 8000. Lint with
`npx oxlint src` (in `frontend\`).

### Django Admin (off by default)

`/admin/` returns 404 and the React app hides its links. The React app's own `/api/admin/...` endpoints are not
affected. To switch it on, do both:

1. Server: set `ENABLE_DJANGO_ADMIN=true` in `.env` and restart Django.
2. React app: set `SHOW_ADMIN_LINKS = true` in `frontend/src/lib/navigation.js`, then `cd frontend; npm run build`.

Every `FULLADMIN` member then signs in to Django Admin with the same email and password; signing in to the React app
also signs you in to Admin. Admin has release versions (with their product), changes, screenshots, uploads, products
(with their repositories), users and the audit log.

```powershell
.venv\Scripts\python manage.py createsuperuser        # new admin: enter their email as the username
.venv\Scripts\python manage.py changepassword <username>
```

---

## Using the app, page by page

### Header and sidebar

- **Product and Client pickers** (signed in): choose the product, then, when it has clients, the client (or
  **Shared (all clients)**). Every page reloads for that choice, and the browser remembers it. Admins get a **+**
  beside each picker to add a product, or a client of the selected product (**+ Client** while it has none).
- **Theme menu**: System, White, Black or a custom background colour, remembered per browser.
- **Account**: your name (with an **Admin** badge), **Sign out** (this device) and **Sign out everywhere** (every
  device).
- **Left sidebar**: the pages you may open. On wide screens, **Collapse** shrinks it to icons (hover an icon for its
  name; remembered per browser). Below 900px it is a drawer opened from the menu button in the header.

| Page | Who sees it |
|---|---|
| Dashboard | admins, Jira viewers (admins land here after signing in) |
| Release Notes | everyone signed in |
| Jira Tickets, Bitbucket Repositories, Commits & Pull Requests | admins, Jira viewers |
| Audit Logs, Import / Export, Settings / Integrations | admins |

### Dashboard

- **Summary tiles** beside the title: how many releases are published, the latest one with its open tickets and
  open bugs, and how many integrations (Jira, Bitbucket) are connected.
- **Jira tickets**: pick a published release; cards show total, open and resolved / closed tickets, and the same
  for bugs. These are the Jira issues found in that release branch's commits, with their live status. All 0 until
  a release branch is published.
- **Published release branches**: with more than one published, a table compares them.
- **Integration health**: whether Jira and Bitbucket answer, last successful sync, last error.

### Release Notes

- **Summary tiles**: number of versions and the Latest version (click it to jump there).
- **Admins**: **Upload release notes** (opens Import / Export) and, while the public page is on, **Copy public link**
  (the selected product's or client's own link).
- **Versions list** on the left, **search** (changes, or Jira ID for signed-in users), **category chips** with counts
  (All, New features, Improvements, Bug fixes, Security).
- **At a glance** panel on wide screens (1280px and up): the version being read, its changes by kind (click one to
  filter) and **Back to top**.
- **Each version**: Latest / Coming soon badge, date, summary, highlights, changes grouped by category (Jira numbers
  link to Jira for admins), known issues, upgrade notes and the screenshot gallery.
- **Admins, per version**:
  - **Edit release**: change the date, status (released / coming soon, with an expected date), summary,
    highlights, known issues and upgrade notes; **Add change**; **Add changes from CSV**; **Edit** / **Delete** next
    to any change; add, caption or remove screenshots and videos (per change, or **Add to gallery**); **Delete
    version**.
  - **Email / download**: download the version's notes as an HTML file, or email it as an attachment (To, Cc, a
    message), sent as described in [Email](#email).

### Jira Tickets

Live tickets from the configured Jira projects, always for one **published release**: only the Jira issues found in
its release branch's commits. Filter by type, status, created dates and search. Tiles show the projects and whether
Jira is connected. Admins have a link to add or remove Jira projects.

### Bitbucket Repositories

- **Tiles**: the selected product's or client's repositories (and how many are private), the branches added in
  Settings (or All), and the workspace.
- **Linked repositories** (admins): **Add / remove repositories** for the selected product or client. Removing only
  unlinks it from this product; a repository the app doesn't know yet is checked in Bitbucket first.
- **Repository cards**: click one to see its branches (search, last commit, Jira keys, date, a link to its commits).
- **Add / remove branches** (admins): limit the screens to chosen branches of that repository.

### Commits & Pull Requests

Recent commits or pull requests of one repository of the selected product or client, optionally one branch (or PR
state). Every Jira key in a message is shown with its **live** Jira status; a commit never marks an issue done.

### Audit Logs

Who signed in, what they opened and what changed: sign-ins, failed sign-ins, Jira views, release uploads, edits,
deletes, emails, access changes, integration and product changes. Filter, load more, or download as CSV (up to
10,000 entries). The same log is on **Settings → Audit log**.

### Import / Export

- **Upload release notes**: a Word document (`.docx`) or a CSV file. The app reads it and shows a review screen
  (version, date, status, summary, highlights, known issues, upgrade notes, screenshots and every change, all
  editable). It says which product or client it **publishes to** (the one in the header). Nothing is saved until
  **Publish**. A version that already exists for that product is refused: edit it on the Release Notes page, or
  delete it and upload again.
- **Draft from Bitbucket**: pick a version that has a release branch in the selected product's repositories, click
  **Draft release notes**, review and publish. See [below](#release-notes-from-word-csv-or-bitbucket).
- **Export**: the selected product's release notes as JSON or CSV, and the sample Word document.

### Settings / Integrations

| Tab | What it does |
|---|---|
| **Users & access** | Every user: grant or remove admin (`FULLADMIN`) and Jira access (`JIRA_VIEWER`), enable or disable the account. Accounts are disabled, never deleted (uploads and the audit log refer to them). You can't remove your own admin role. |
| **Audit log** | As the Audit Logs page. |
| **Products** | Add products; per product: its **Shared (all clients)** repositories, its clients (add, remove) and each client's repositories; each one's **public link** with **Copy** and **New link**. See [Products and clients](#products-and-clients). |
| **Integrations** | **Refresh and test connections** (clears the cache), integration health, the **Jira and Bitbucket connection** (URL, emails, workspace, tokens; saved encrypted, never shown again), **What the screens show** (the selected product's repositories, branches per repository, Jira projects, Jira fix versions) and the settings that stay in `.env`. |

---

## Products and clients

### How it fits together

```
iCRM ──────────── Shared (all clients)   repos: icrm-b2b-master, icrm-base-framework-master
IUC ───┬───────── Shared (all clients)   (usually empty)
       ├── Client A                      repos: Client A's own, branches, versions 3.2.0 …
       ├── Client B                      repos: Client B's own, branches, versions 5.0.1 …
       └── Client C                      …
Sales Audit ───── Shared (all clients)
```

- A **client** is stored as a product whose parent is the product (`release_product.parent_id`). Clients can't have
  clients of their own. **Shared (all clients)** is the product itself.
- Each product and each client has its **own release versions** (numbers unique within it), its own **Latest**, its
  own **repositories** and its own **public link**.
- The React app sends the selected product or client as the **`X-Product` header** on every API call;
  `releases/products.py` reads it (or `?product=<id>`), and without one the first product is used.
- **Jira projects are shared** by all products.

### Setting up IUC clients (example)

1. In the header pick **IUC**, click **+ Client**, type **Client A**, **Add**. Repeat for Client B and Client C (or
   use **Settings → Products → New client of IUC**).
2. Pick **IUC → Client A**. On **Bitbucket Repositories → Add / remove repositories**, add Client A's repository
   (its slug, the last part of its Bitbucket URL). Or add it on its card in Settings → Products.
3. On the Bitbucket page, click the repository and **Add / remove branches** for the branches to show.
4. Publish Client A's release notes with **Import / Export** while Client A is selected.
5. Share Client A's public link from **Settings → Products** (Client A's card → **Copy**).

### Rules

| Action | Rule |
|---|---|
| Add a product or client | Admins. Names are trimmed; unique (ignoring case) among products, or among one product's clients. |
| Remove a product or client | Refused while it has release versions (delete them first), or while a product still has clients. The last product always stays. Its repository links go with it; the repositories stay in the app. |
| Link a repository | Admins. One repository can belong to several products or clients (e.g. a shared framework). |
| Unlink a repository | Only from that product or client; others keep it. |

### What is per product, and what is shared

| Per product or client | Shared |
|---|---|
| Release versions, Latest, uploads, drafts, exports | Jira projects |
| Linked repositories (Bitbucket, Commits, Dashboard, Draft from Bitbucket) | Branches added to a repository (stored per repository: two products using the **same** repository see the same branches) |
| Public link | Jira fix versions added in Settings; version start dates (stored by version number) |
| Email subject and file name ("IUC – Client A Release 3.2.0") | Release branch naming: only `icrm_release_…` branches are recognised (below) |

When clients use **different repositories**, their branches are fully separate too.

**Release branch naming:** Draft from Bitbucket and the Dashboard's per-release counts recognise only branches named
`release/icrm_release_<version>_<date>`. IUC clients without such branches can still upload release notes (Word / CSV)
and browse their repositories, branches, commits and pull requests; only those two features need the naming. When
IUC release branches exist, a per-product branch pattern is the next step
(`integrations/release_generator.py`, `BRANCH_RE`).

---

## Public release notes

A read-only release notes page anyone can open without signing in, for customers. It is **switched off by default**.

- **Switch on:** set `PUBLIC_RELEASE_NOTES=true` in `.env` and restart Django. Off, the page and `/api/public/...`
  answer 404 and nothing else changes.
- **One link per product and client:** `<APP_BASE_URL>/public/release-notes/<key>`, where the key is 16 random
  characters (`release_product.public_key`), e.g. `/public/release-notes/Xk3p9QwZ_aB7mT2c`. One version: add its
  anchor, e.g. `…/<key>#icrm-v1090`.
- **Safe to share:** the public API takes only the key (`?key=`), never a product id, so one client's link doesn't
  lead to another's. A product id in the URL or header is ignored there. Screenshots are served only with their own
  product's key. Product ids aren't in the public data, and the product list (`/api/products`) needs sign-in.
- **Where to get a link:** **Settings → Products**, each card → **Copy**. **New link** replaces the key; the old
  link then stops working for everyone. While the page is on, the Release Notes page's **Copy public link** copies the
  selected product's or client's link.
- **What it shows:** every version with its changes, highlights, known issues, upgrade notes and screenshots,
  **without Jira numbers** (left out on the server, not only hidden), without edit buttons, navigation or product
  picker. Upcoming versions are marked "Coming soon".
- **The original link** `/public/release-notes` (no key) still works and shows the first product (iCRM).
- **Limits:** `/api/public/...` is rate-limited per client IP (`THROTTLE_PUBLIC`, default `60/min`; behind IIS / nginx
  set `NUM_PROXIES=1`). Screenshots are served with `Cache-Control: public`.
- **Reaching it from outside** (infrastructure): the server needs a public https address in `ALLOWED_HOSTS`,
  `CSRF_TRUSTED_ORIGINS` and `APP_BASE_URL`. To publish only this page, let the proxy pass `/public/`, `/assets/`,
  `/favicon.ico` and `/api/public/` from the internet and keep the rest internal.

---

## Release notes from Word, CSV or Bitbucket

All three open the same review screen; nothing is saved until **Publish**, and the version goes to the product or
client selected in the header.

### Word document (.docx)

Required: a **version number** (e.g. a title line `iCRM Release 11.1`) and **at least one change** (a bullet under a
heading such as *What's New* or *Bug Fixes*, or a row in a Jira table). Optional: `Status: Coming soon` and
`Planned release: October 2026`, a release date (`Released on September 28, 2026`; default today), a summary
paragraph, *Highlights* / *Known issues* / *Upgrade notes* sections, screenshots (a picture under a change belongs to
it; pictures under *Screenshots* go to the gallery; a caption line starts with `Screenshot:`), and a *Jira list* table
(Jira, Category, Title, Description). Start from the sample: `frontend/public/samples/iCRM-Release-11.1-sample.docx`
(also under Import / Export → Export).

### CSV file

One change per row with a header row; only **Title** is required (Version, Release date, Status, Planned release,
Category, Jira ID, Description and more are optional). Sample: `frontend/public/samples/iCRM-Release-sample.csv`. On
the Release Notes page, **Add changes from CSV** adds a file's changes to an existing version.

### Draft from Bitbucket

- Every branch named `release/icrm_release_<version>_<date>` in the selected product's repositories is a version
  (`release/icrm_release_10_9_0_18122025` = 10.9.0, 18 Dec 2025; older names use DDMMYY; copies such as `_bkp` or
  `citi_…` are ignored).
- Its changes are the commits on that branch that aren't on the previous version's branch in the same repository.
- The Jira keys in those commit messages are looked up in Jira: summary → title, description → description, issue
  type → category (Bug → Bug fix; Story / New Feature / Epic → New feature; Security / Vulnerability type or a
  `security` label → Security; anything else by its wording).
- Warnings list issues Jira doesn't show and issues not done yet (remove them if they aren't in the release).
- **After publishing**, its release branches are added to the screens' branch scope, so Bitbucket, Commits and the
  Dashboard follow the published release. Deleting the version removes them again. Both are audited.

Code: `integrations/release_generator.py`.

---

## Screenshots and videos

On the Release Notes page, **Edit release → Add screenshot or video** (one change) or **Add to gallery** (the whole
version) uploads a file, checked from its bytes, not its name:

| Kind | Formats | Largest | Shown as |
|---|---|---|---|
| Screenshot | PNG, JPEG, GIF (animated too), WebP | 5 MB | the picture, linked to its full size |
| Video | MP4, WebM | 25 MB | a muted, looping player that plays while on screen, with controls |

A 30-second screen recording is usually 1 to 5 MB as MP4 (often over 10 MB as a GIF), so record videos as MP4 (e.g.
Windows Snipping Tool → Record). Videos can't come from a Word document; Django Admin takes screenshots only. Videos
are served with byte ranges (`Range` → 206) so browsers can seek. Files live in `<UPLOAD_DIR>/release-images/`.
Behind IIS the default request limit (30 MB) is enough; behind nginx raise `client_max_body_size` to `26m`.

---

## Jira and Bitbucket (live data)

The Dashboard, Jira Tickets, Bitbucket Repositories and Commits & Pull Requests pages read Jira Cloud and Bitbucket
Cloud **through Django** (`integrations/`). Tokens stay on the server; no response contains them. Without credentials
each page says which settings are missing, and the rest of the app works.

- **Configure:** **Settings → Integrations → Jira and Bitbucket connection** (Jira site URL, email, API token;
  Bitbucket workspace, email and API token, or an access token), then **Refresh and test connections**. Saved in
  `integration_credential`, encrypted with a key derived from `APP_SECRET_KEY` (changing that key makes them
  unreadable: enter them again). Anything not saved there is read from `JIRA_*` / `BITBUCKET_*` in `.env`.
- **Repositories:** the app's list is `BITBUCKET_REPOSITORIES` plus repositories admins add, minus `.env` ones they
  removed. Each product or client shows only the ones **linked to it** (see [Products](#products-and-clients)).
- **Counts:** open = status category not Done; resolved / closed = Done **and** a status in `JIRA_RESOLVED_STATUSES` /
  `JIRA_CLOSED_STATUSES` (anything else Done is "other done"); bugs = `JIRA_BUG_ISSUE_TYPES`. Configured names Jira
  doesn't have are ignored and reported, never sent in JQL.
- **Scope (Settings → Integrations → What the screens show):** branches per repository and Jira fix versions. With
  branches added, Bitbucket lists only those, and Commits & Pull Requests show only commits on them and PRs into or
  out of them. With fix versions added, Jira counts and lists cover only those (this overrides
  `JIRA_FIX_VERSION_MAP`). Each name is checked in Bitbucket / Jira before it's saved; changes are audited as
  `INTEGRATION_SCOPE`. Jira projects can be added on top of `JIRA_PROJECT_KEYS` there too.
- **Commits → Jira:** keys of the configured projects in commit messages and PR titles are looked up live. A commit
  never marks an issue resolved.
- **Release-wise summaries** (`GET /api/integrations/jira/releases`): listed under Jira's own fix version names, tied
  to the app's versions only through `JIRA_FIX_VERSION_MAP`.
- **Caching:** answers are kept in memory for `INTEGRATION_CACHE_SECONDS` (default 300); **Refresh** clears them.
  Nothing from Jira or Bitbucket is copied into the database.

---

## Users, roles and sign-in security

| Role | Can do |
|---|---|
| `FULLADMIN` | Everything: every page, uploads and edits, products, users, integrations, audit log |
| `JIRA_VIEWER` | Release Notes, Dashboard, Jira Tickets, Bitbucket, Commits & Pull Requests (read only) |
| Signed in, no role | Release Notes (read only) |

Roles are granted on **Settings → Users & access** (or in Django Admin); they live in `app_user_security_group` with
from / thru dates.

| What | How | Settings (`.env`) |
|---|---|---|
| Sign-in first | Every page opens on the sign-in form until the user signs in; release notes and screenshots need a signed-in user on the server too. The one exception is the [public page](#public-release-notes), when switched on. | |
| Default admin | `manage.py setup` creates `releasemanager` / `releasemanager` only when there are no users. Until its password is changed the API answers 403 to everything except `/api/auth/me`, `/change-password` and the sign-outs, and Django Admin refuses it. | |
| Rate limits | Sign-in, sign-up and password reset are counted per client IP; over the limit the API answers 429. | `THROTTLE_LOGIN` (10/min), `THROTTLE_REGISTER` (5/hour), `THROTTLE_PASSWORD_RESET` (5/hour), `NUM_PROXIES` |
| Account lockout | After 5 failed sign-ins to one account its sign-in is refused for 15 minutes (audited). A password reset unlocks it. | `LOGIN_LOCKOUT_ATTEMPTS`, `LOGIN_LOCKOUT_SECONDS` |
| Sign out | **Sign out** ends this device's token (`revoked_token`); **Sign out everywhere** ends every device's (`user_token_cutoff`, audited). A password change or disabling an account also ends every earlier sign-in. | |
| Password reset | **Forgot password** emails a link valid for `PASSWORD_RESET_TTL_SECONDS` (default 30 minutes), usable once. | `APP_BASE_URL` |
| Self sign-up | Limited to `@aiintelekt.com` addresses by default; can be switched off. | `ALLOW_REGISTRATION`, `REGISTRATION_EMAIL_DOMAINS` |
| Content Security Policy | Report-only by default (logged in the browser console). | `CSP_ENFORCE=true` |
| Health check | `GET /api/health`: 200 `{"status": "ok"}`, or 503 when the database doesn't answer. | |

**Passwords** use the PBKDF2 format of the retired python-backend (`accounts/hashers.py`); sign-in tokens are signed
with `APP_SECRET_KEY` (`TOKEN_TTL_SECONDS`, default 8 hours). The lockout and rate limits live in the in-process cache:
restarting Django clears them, and they assume one server process (use Redis before running several).

---

## Email

Password resets and **Email / download** on a release send email. `EMAIL_MODE` in `.env` picks how:

| `EMAIL_MODE` | What happens | Used for |
|---|---|---|
| `file` | Each email is saved as an `.eml` file in `MAIL_FILE_DIR` (default `sent_emails/`). Nothing is sent. | Local development (default) |
| `smtp` | Sent through `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY` (`starttls` / `ssl` / `none`), `SMTP_USER`, `SMTP_PASSWORD`. | Mailtrap testing; production |
| `console` | Printed in the server console. | Quick checks |

`MAIL_FROM` is the sender (`Name <address>`); `SMTP_TIMEOUT` (seconds, default 20) is optional. A wrong value stops
Django at startup with a message naming the setting; passwords are never printed. The release email's subject and
attachment carry the product or client name, e.g. "IUC – Client A Release 3.2.0 - release notes".

**Test the settings:** `.venv\Scripts\python manage.py send_test_email you@example.com` (prints the mode, host, user,
whether a password is set, and the server's error if sending fails).

**Mailtrap** (mailtrap.io → Email Testing → My Inbox → SMTP): every email lands in the Mailtrap inbox, never a real
mailbox.

```
EMAIL_MODE=smtp
SMTP_HOST=sandbox.smtp.mailtrap.io
SMTP_PORT=2525
SMTP_SECURITY=starttls
SMTP_USER=<from the SMTP tab>
SMTP_PASSWORD=<from the SMTP tab>
```

**Production (infrastructure team):** set `EMAIL_MODE=smtp`, the company relay's `SMTP_*` values and a `MAIL_FROM` that
account may send as. Microsoft 365: `smtp.office365.com:587` needs Authenticated SMTP enabled for the mailbox, the
mailbox excluded from MFA / security defaults and Basic auth for SMTP still allowed ("Send As" permission for another
address). Direct Send (`aiintelekt-com.mail.protection.outlook.com:25`) only delivers to @aiintelekt.com and is
refused from IPs on Spamhaus lists; from a fixed server IP, add it to the domain's SPF record.

---

## Database

`react_database` on `localhost:3306` by default (`DB_*` in `.env`). The original tables are used as they are: their
Django models are `managed = False`, and on an empty database `migrate` creates them (`CREATE TABLE IF NOT EXISTS` in
each app's `0001_initial`).

### Tables

| Table | Model | What it holds |
|---|---|---|
| `release_product` | `releases.Product` | Products and clients (`parent_id` = the product), display order, public link key |
| `release_product_repository` | `releases.ProductRepository` | Which Bitbucket repositories each product or client shows |
| `release_version` | `releases.ReleaseVersion` | Versions: product, number, date, status, summary, highlights, known issues, upgrade notes, Latest |
| `release_item` | `releases.ReleaseItem` | Changes: category, title, description, Jira ID, order |
| `release_image` | `releases.ReleaseImage` | Screenshots and videos (file in `<UPLOAD_DIR>/release-images/`) |
| `release_upload` | `releases.ReleaseUpload` | Every upload (file name, changes, who, when) |
| `app_user`, `app_user_security_group` | `accounts.AppUser`, `AppUserSecurityGroup` | Users and their roles |
| `revoked_token`, `user_token_cutoff` | `accounts` | Signed-out tokens |
| `audit_log` | `audit.AuditLog` | The audit log |
| `integration_scope` | `integrations.IntegrationScope` | Branches, fix versions, added Jira projects and repositories, version start dates |
| `integration_credential` | `integrations.IntegrationCredential` | Jira / Bitbucket connection settings, encrypted |
| `jira_issue`, `jira_seed_entry`, `jira_table_entry` | `jira` | The imported Jira list (its tab is hidden on the Jira page) |
| `django_*`, `auth_*` | Django | Migrations, sessions, admin log, permissions |
| `messages` | not mapped | Old demo table, unused |

### Release migrations

| Migration | Change |
|---|---|
| `releases/0001_initial` | The original release tables (created only if missing) |
| `releases/0002_products` | `release_product` and `release_product_repository`; iCRM, IUC, Sales Audit; every existing version and repository becomes iCRM's; `release_version.product_id` added and the unique key on `version` replaced by one on `(product_id, version)` |
| `releases/0003_product_clients` | `release_product.parent_id` (clients); names unique per product |
| `releases/0004_product_public_key` | `release_product.public_key`, a random key for every product and client |

**MySQL 5.5 and migrations:** Django 6 officially supports MySQL 8.0.11+. `config/db_backends/mysql55` lowers the
version check and creates `DATETIME` columns without fractional seconds. Some of Django's automatic schema changes
(e.g. dropping a unique key) read `information_schema.check_constraints`, which 5.5 doesn't have, so schema changes
there are written as plain SQL that checks what already exists (see `0003` and `0004`); a run that stopped halfway
then finishes on the next `migrate`. After upgrading the server to MySQL 8, set `ENGINE` to
`django.db.backends.mysql` in `config/settings/base.py`.

```powershell
.venv\Scripts\python manage.py migrate                 # apply migrations
.venv\Scripts\python manage.py showmigrations          # what is applied
.venv\Scripts\python manage.py makemigrations          # only after changing a model
```

### Backups

`backups/` (git-ignored) holds full dumps:
- `react_database_before_django_20260930_1435.sql`: before Django first touched the database.
- `react_database_before_products_20261023.sql`: before the products migrations.

Take one before applying new migrations:
```powershell
& "C:\Program Files\MySQL\MySQL Server 5.5\bin\mysqldump.exe" -uroot -p --single-transaction react_database > backups\react_database_<date>.sql
```
Restore with `mysql -uroot -p react_database < <file>`.

---

## API

All under `/api/` (`config/urls.py`). Signed-in calls send `Authorization: Bearer <token>`; product-specific calls also
send **`X-Product: <id>`** (the header's product or client; none = the first product). Errors come back as
`{"detail": "..."}` or `{"errors": {...}}`.

| Endpoint | View | Access |
|---|---|---|
| `GET /api/releases`, `/api/releases/{id}`, `/api/releases/version/{v}` | `releases.api` | signed in; the selected product's |
| `GET /api/release-images/{id}` | `releases.api.release_image` | signed in (session cookie or token) |
| `GET /api/public/releases`, `/api/public/releases/version/{v}`, `/api/public/product`, `/api/public/release-images/{id}` (all `?key=<public key>`) | `releases.api.public_*` | anyone while `PUBLIC_RELEASE_NOTES=true` (404 otherwise); no Jira numbers |
| `GET /api/products` | `releases.api.list_products` | signed in (`publicKey` for admins only) |
| `POST /api/admin/products` (`{name, parentId?}`), `DELETE /api/admin/products/{id}`, `POST /api/admin/products/{id}/public-key` | `releases.api.add_product`, `remove_product`, `new_public_key` | FULLADMIN, audited as `PRODUCT_CHANGE` |
| `POST /api/integrations/products/{id}/repositories` (`{repository}`), `DELETE .../repositories/{slug}` | `integrations.api.product_repository_*` | FULLADMIN, audited as `PRODUCT_CHANGE` |
| `POST /api/admin/releases/parse` (file), `POST /api/admin/releases` (publish) | `releases.api.parse_upload`, `publish` | FULLADMIN |
| `PATCH/DELETE /api/admin/releases/{id}`; `POST .../{id}/items`, `.../{id}/items/import`, `.../{id}/images`; `GET .../{id}/notes-file`; `POST .../{id}/email` | `releases.api` | FULLADMIN |
| `PATCH/DELETE /api/admin/release-items/{id}`, `/api/admin/release-images/{id}` | `releases.api` | FULLADMIN |
| `POST /api/auth/register`, `/login`, `/forgot-password`, `/reset-password`, `/change-password`, `/logout`, `/logout-all`; `GET /api/auth/me`, `/api/auth/options` | `accounts.api` | public / signed in |
| `GET /api/admin/users`, `PATCH /api/admin/users/{id}` | `accounts.api` | FULLADMIN |
| `GET /api/admin/audit-log`, `/api/admin/audit-log.csv` | `audit.api` | FULLADMIN |
| `GET /api/jira-issues`, `/api/jira-issues/{id}` | `jira.api` | FULLADMIN or JIRA_VIEWER, audited |
| `GET /api/integrations/status`, `/dashboard`, `/jira/{filters,summary,issues,releases}`, `/bitbucket/repositories[/{slug}/{branches,commits,pullrequests}]` | `integrations.api` | FULLADMIN or JIRA_VIEWER (denials audited) |
| `POST /api/integrations/refresh` | `integrations.api.refresh` | FULLADMIN, audited |
| `POST /api/integrations/scope`, `DELETE /api/integrations/scope/{id}` | `integrations.api.scope_*` | FULLADMIN, audited as `INTEGRATION_SCOPE` |
| `GET/PUT /api/integrations/credentials` (tokens never returned) | `integrations.api.credentials_settings` | FULLADMIN, audited (names only) |
| `GET /api/integrations/release-notes/versions`, `POST /api/integrations/release-notes/draft` | `integrations.api.release_*` | FULLADMIN; nothing is saved |
| `GET /api/health` | `config.health` | public |

---

## Project structure

| Folder | What's in it |
|---|---|
| `config/` | Settings (`settings/base.py`, `dev.py`, `prod.py`), URLs, shared API helpers, email config, health check, the MySQL 5.5 backend |
| `accounts/` | Users, roles, sign-in, tokens, password hashing, `setup` and `send_test_email` commands |
| `audit/` | The audit log model, recording and the audit API |
| `releases/` | Products, clients, versions, changes, screenshots; `products.py` (which product a request is about); `services/` (Word / CSV parsers, images, Latest, JSON, email) |
| `integrations/` | Jira and Bitbucket clients, cache, credentials, scope, release drafting (`release_generator.py`) and their API |
| `jira/` | The imported Jira list |
| `frontend/` | The React app: `src/pages/` (one per page), `src/components/`, `src/context/` (sign-in, product), `src/services/` (API calls), `src/lib/`; built into `frontend/dist/` |
| `frontend_app/` | Serves the built React app for every non-API URL |
| `scripts/` | `smoke_api.py`: every endpoint against the real database, rolled back |
| `media/`, `sent_emails/`, `backups/` | Uploaded files, saved emails, database dumps (all git-ignored) |

---

## Settings (.env)

`.env.example` lists every setting with comments. The main ones:

| Setting | Default | Purpose |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.dev` | `config.settings.prod` on a server |
| `DJANGO_SECRET_KEY`, `APP_SECRET_KEY` | (none) | Django's secret; the app's token and encryption secret (keep it) |
| `TOKEN_TTL_SECONDS`, `PASSWORD_RESET_TTL_SECONDS` | 28800, 1800 | Sign-in and reset link lifetimes |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | `react_database`, `root`, -, `localhost`, `3306` | MySQL |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` | - | Production |
| `APP_BASE_URL` | `http://localhost:8000` | Links in emails |
| `UPLOAD_DIR` | `media/` | Screenshots and videos |
| `ENABLE_DJANGO_ADMIN` | `false` | Django Admin at `/admin/` |
| `PUBLIC_RELEASE_NOTES`, `THROTTLE_PUBLIC` | `false`, `60/min` | Public release notes |
| `ALLOW_REGISTRATION`, `REGISTRATION_EMAIL_DOMAINS` | `true`, `aiintelekt.com` | Self sign-up |
| `THROTTLE_LOGIN`, `THROTTLE_REGISTER`, `THROTTLE_PASSWORD_RESET`, `LOGIN_LOCKOUT_ATTEMPTS`, `LOGIN_LOCKOUT_SECONDS`, `NUM_PROXIES` | see [security](#users-roles-and-sign-in-security) | Sign-in protection |
| `CSP_ENFORCE` | `false` | Enforce the Content Security Policy |
| `EMAIL_MODE`, `MAIL_FILE_DIR`, `MAIL_FROM`, `SMTP_*` | `file`, `sent_emails` | [Email](#email) |
| `JIRA_BASE_URL`, `JIRA_CLOUD_ID`, `JIRA_EMAIL`, `JIRA_API_TOKEN` | - | Jira connection (or enter in the app) |
| `JIRA_PROJECT_KEYS` | `CS,IBP,CT,CP` | Jira projects (more can be added in the app) |
| `JIRA_BUG_ISSUE_TYPES`, `JIRA_RESOLVED_STATUSES`, `JIRA_CLOSED_STATUSES`, `JIRA_FIX_VERSION_MAP` | `Bug`, `Resolved`, `Closed,Done` | Ticket counting |
| `BITBUCKET_WORKSPACE`, `BITBUCKET_EMAIL`, `BITBUCKET_API_TOKEN` / `BITBUCKET_ACCESS_TOKEN` | - | Bitbucket connection (or enter in the app) |
| `BITBUCKET_REPOSITORIES` | `icrm-base-framework-master,icrm-b2b-master` | Starting repositories (more can be added in the app) |
| `INTEGRATION_TIMEOUT_SECONDS`, `INTEGRATION_CACHE_SECONDS` | 15, 300 | Jira / Bitbucket request timeout and cache |

Secrets live only in `.env`, which is git-ignored.

---

## Environments and deployment

| | Development | Staging / production |
|---|---|---|
| Settings | `config.settings.dev` (default in `manage.py`) | `config.settings.prod` (default in `config/wsgi.py`) |
| Server | `manage.py runserver` | `.venv\Scripts\waitress-serve --listen=127.0.0.1:8000 config.wsgi:application`, behind IIS / nginx with https |
| DEBUG | on | off; `DJANGO_SECRET_KEY` and `APP_SECRET_KEY` required |
| Required `.env` | `DB_*` | `DB_*`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `APP_BASE_URL`, `EMAIL_MODE=smtp` and `SMTP_*` |
| Each deployment | `npm run build` | back up the database; `npm ci; npm run build` in `frontend/`; `manage.py setup` (migrations); `manage.py collectstatic`; restart waitress |

| Build | Command | Output |
|---|---|---|
| React app | `cd frontend; npm run build` | `frontend/dist/` |
| Django Admin static files (production) | `.venv\Scripts\python manage.py collectstatic` | `staticfiles/` |

---

## Testing

```powershell
.venv\Scripts\python manage.py test                         # 177 unit tests, mocked: no network, no database
.venv\Scripts\python manage.py check
.venv\Scripts\python manage.py makemigrations --check --dry-run
cd frontend; npx oxlint src; npm run build; cd ..
# Every API endpoint against the real database, in a transaction that is rolled back:
.venv\Scripts\python manage.py shell -c "exec(open('scripts/smoke_api.py', encoding='utf-8').read())"
```

The unit tests cover sign-in security, the audit export, health, email, releases, products and clients, public
links, and Jira / Bitbucket with mocked responses. The smoke script expects the imported Jira list (`jira_issue` rows);
on a database without them it stops at its "jira detail" check.

`bitbucket-pipelines.yml` runs the unit tests, `check`, the migration check, oxlint and the React build on every push
and pull request once the project is in a Bitbucket repository.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "The React app isn't built yet" | `cd frontend; npm ci; npm run build` |
| A change in the UI doesn't show | Rebuild the frontend, then hard-refresh (Ctrl+Shift+R) |
| No Product dropdown in the header | It shows when signed in and there are two or more products, or the product has clients, or you are an admin |
| A page is empty for a client | Link its repositories (Settings → Products or Bitbucket → Add / remove repositories); publish its release notes while it is selected |
| Draft from Bitbucket lists no versions | The selected product's repositories have no `release/icrm_release_…` branches |
| Jira / Bitbucket "not configured" | Settings → Integrations → Jira and Bitbucket connection, then Refresh and test connections |
| Public link says the notes aren't available | `PUBLIC_RELEASE_NOTES=true` and restart; or the link was replaced with **New link**: copy the current one |
| A migration fails with "Unknown table 'check_constraints'" | MySQL 5.5 can't run that automatic change: write it as plain SQL (see [Database](#database)) |
| Port 8000 in use | `runserver 8001` |

---

## History

This app replaced `python-backend` (FastAPI) and `my-react-app`; both folders have been deleted. It still works on
that app's database (`react_database`) as it is, and keeps its password and token formats. Verified during that
migration (2026-09-30) against the real data: every admin page loads, 41/41 API checks, 16/16 browser checks.
Products, clients and per-client public links were added on 2026-10-23.
