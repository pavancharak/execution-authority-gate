"""
Optional Flask server for the dashboard.

Not required for local use — `python -m http.server` from web/ works
fine (see the README). This exists for deployment: a static-file server
with a health check at /api/status, matching ../Dockerfile and
../fly.toml.

Serves whatever is in web/data/dashboard.json at request time — for a
deployed image that's the version committed to the repo, since the
pipeline isn't run inside the container.
"""

import os
from pathlib import Path

from flask import Flask, send_from_directory
from flask_cors import CORS

WEB_DIR = Path(__file__).resolve().parent

app = Flask(__name__, static_folder=None)
CORS(app)


@app.get("/api/status")
def status():
    dashboard_path = WEB_DIR / "data" / "dashboard.json"
    return {"ok": True, "dashboard_present": dashboard_path.exists()}


@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/<path:filename>")
def static_files(filename):
    return send_from_directory(WEB_DIR, filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
