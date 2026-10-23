# Release Manager – notes for Claude

Django 6.1 + React 19 (Vite) app for release notes of products (iCRM, IUC, Sales Audit) and their clients, on MySQL 5.5.
The [README](README.md) describes the whole app; read it before changing code.

## Deploying to staging or production

Follow [`docs/STAGING_DEPLOYMENT.md`](docs/STAGING_DEPLOYMENT.md) step by step, in order. Run each step's commands,
check the result it names, and stop at the first step that doesn't match: explain what went wrong before going on.

Ask the person for the server's own values; never invent them: host name, MySQL user / password / database name, SMTP
account, `UPLOAD_DIR` folder, certificate, service account, Jira and Bitbucket tokens. Generate the two secrets with the
command in step 3.

Rules that must not be broken on a server:

- **Back up first.** Before `manage.py setup` or `migrate` on a database that has data, dump it (`mysqldump`, step 5) and
  copy the `UPLOAD_DIR` folder. Migrations change the `release_version` table.
- **Never change `APP_SECRET_KEY`** once it is set: sign-ins end and the Jira / Bitbucket tokens saved in the app can no
  longer be read.
- **Never commit `.env`**, and never print its passwords or tokens in output, logs or messages.
- **Staging and production run under waitress** (`config.settings.prod`), never `manage.py runserver`, and as one
  process (sign-in lockout and rate limits live in memory).
- **Set `UPLOAD_DIR` outside the code folder** and back it up with the database: uploads are files, not database rows.
- **Don't drop, rename or edit tables by hand**, and don't edit applied migrations. On MySQL 5.5 some of Django's
  automatic schema changes fail (`information_schema.check_constraints` is missing); write those as plain SQL that checks
  what already exists, as `releases/migrations/0003_product_clients.py` and `0004_product_public_key.py` do.
- **Don't delete products, clients, versions or users** to "clean up" unless the person asks for exactly that.

## Working on the code

- Run locally: `.venv\Scripts\python manage.py runserver 8000` (it runs `setup` first). Frontend:
  `cd frontend; npm run build` (or `npm run dev` on port 5173).
- Before committing: `.venv\Scripts\python manage.py test`, `manage.py check`, `manage.py makemigrations --check
  --dry-run`, and in `frontend\`: `npx oxlint src` and `npm run build`. The unit tests mock the database and network.
- Every API call is about the product or client in the `X-Product` header (`releases/products.py`); public endpoints take
  only the product's public key (`?key=`), never its id. Keep both rules in new endpoints.
- Keep `README.md` and `docs/STAGING_DEPLOYMENT.md` up to date when a setting, a step or a table changes.
