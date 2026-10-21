"""Serve the React app (frontend/dist, built with `npm run build`) for every page route.

WhiteNoise serves its files (/assets/..., /favicon.ico); this view answers the page routes the React router
handles (/, /jira, /upload, /settings, /login, /reset-password, ...) with index.html.
"""
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.cache import never_cache

NOT_BUILT = """<!doctype html><meta charset="utf-8"><title>iCRM Release Notes</title>
<body style="font-family:system-ui;max-width:640px;margin:64px auto;line-height:1.5">
<h1>The React app isn't built yet</h1>
<p>Build it once, then reload:</p><pre>cd frontend
npm install
npm run build</pre>
<p>Or, while developing, run <code>npm run dev</code> in <code>frontend/</code> and open
<a href="http://localhost:5173">http://localhost:5173</a>.</p>
<p>Django Admin works without it: <a href="/admin/">/admin/</a></p>"""


@never_cache
def spa(request, path=""):
    index = settings.FRONTEND_DIR / "dist" / "index.html"
    if not index.is_file():
        return HttpResponse(NOT_BUILT, status=503)
    return HttpResponse(index.read_bytes(), content_type="text/html; charset=utf-8")
