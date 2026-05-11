#!/usr/bin/env python3

import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

TMDB_BASE = "https://api.themoviedb.org/3"
CACHE_TTL_SECONDS = 120
CACHE_MAX_ITEMS = 300
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 120
DB_PATH = Path("tmdb_app.db")

ALLOWED_ENDPOINTS = [
    re.compile(r"^/search/multi$"),
    re.compile(r"^/trending/movie/week$"),
    re.compile(r"^/discover/movie$"),
    re.compile(r"^/movie/\d+$"),
    re.compile(r"^/movie/\d+/recommendations$"),
    re.compile(r"^/tv/\d+$"),
    re.compile(r"^/tv/\d+/recommendations$"),
]

CACHE = {}
RATE_BUCKET = {}


def load_env(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def endpoint_allowed(endpoint: str) -> bool:
    return any(pattern.match(endpoint) for pattern in ALLOWED_ENDPOINTS)


def cache_get(key: str):
    entry = CACHE.get(key)
    if not entry:
        return None
    if time.time() - entry["ts"] > CACHE_TTL_SECONDS:
        CACHE.pop(key, None)
        return None
    return entry["data"]


def cache_set(key: str, data: dict) -> None:
    if len(CACHE) >= CACHE_MAX_ITEMS:
        oldest = min(CACHE.items(), key=lambda kv: kv[1]["ts"])[0]
        CACHE.pop(oldest, None)
    CACHE[key] = {"ts": time.time(), "data": data}


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = db()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT UNIQUE NOT NULL,
              password_hash TEXT NOT NULL,
              created_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
              token TEXT PRIMARY KEY,
              user_id INTEGER NOT NULL,
              created_at INTEGER NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist (
              user_id INTEGER NOT NULL,
              media_id INTEGER NOT NULL,
              media_type TEXT NOT NULL,
              payload TEXT NOT NULL,
              created_at INTEGER NOT NULL,
              PRIMARY KEY(user_id, media_id, media_type),
              FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def get_user_from_token(auth_header: Optional[str]) -> dict:
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth_header.split(" ", 1)[1].strip()
    conn = db()
    try:
        row = conn.execute(
            """
            SELECT u.id, u.username
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"id": row["id"], "username": row["username"], "token": token}
    finally:
        conn.close()


def rate_limit(key: str) -> None:
    now = time.time()
    bucket = RATE_BUCKET.get(key)
    if not bucket or now - bucket["start"] > RATE_LIMIT_WINDOW:
        RATE_BUCKET[key] = {"start": now, "count": 1}
        return
    bucket["count"] += 1
    if bucket["count"] > RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")


class AuthPayload(BaseModel):
    username: str
    password: str


class WatchlistPayload(BaseModel):
    media_id: int
    media_type: str
    payload: dict


load_env()
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "").strip()
init_db()

app = FastAPI(title="TMDB Explorer API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health")
def health():
    return {"ok": True, "api_ready": bool(TMDB_API_KEY)}


@app.post("/api/v1/auth/register")
def register(payload: AuthPayload):
    username = payload.username.strip().lower()
    if len(username) < 3 or len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="username>=3 and password>=6 required")

    conn = db()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, hash_password(payload.password), int(time.time())),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="username already exists")
    finally:
        conn.close()
    return {"ok": True}


@app.post("/api/v1/auth/login")
def login(payload: AuthPayload):
    conn = db()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (payload.username.strip().lower(),),
        ).fetchone()
        if not row or row["password_hash"] != hash_password(payload.password):
            raise HTTPException(status_code=401, detail="invalid credentials")
        token = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
            (token, row["id"], int(time.time())),
        )
        conn.commit()
        return {"token": token, "username": row["username"]}
    finally:
        conn.close()


@app.get("/api/v1/auth/me")
def me(authorization: Optional[str] = Header(default=None)):
    user = get_user_from_token(authorization)
    return {"id": user["id"], "username": user["username"]}


@app.get("/api/v1/watchlist")
def list_watchlist(authorization: Optional[str] = Header(default=None)):
    user = get_user_from_token(authorization)
    conn = db()
    try:
        rows = conn.execute(
            "SELECT media_id, media_type, payload, created_at FROM watchlist WHERE user_id = ? ORDER BY created_at DESC",
            (user["id"],),
        ).fetchall()
        data = []
        for row in rows:
            item = json.loads(row["payload"])
            item["media_id"] = row["media_id"]
            item["media_type"] = row["media_type"]
            data.append(item)
        return {"items": data}
    finally:
        conn.close()


@app.post("/api/v1/watchlist")
def upsert_watchlist(payload: WatchlistPayload, authorization: Optional[str] = Header(default=None)):
    user = get_user_from_token(authorization)
    if payload.media_type not in ("movie", "tv"):
        raise HTTPException(status_code=400, detail="media_type must be movie or tv")
    conn = db()
    try:
        conn.execute(
            """
            INSERT INTO watchlist (user_id, media_id, media_type, payload, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, media_id, media_type)
            DO UPDATE SET payload = excluded.payload
            """,
            (user["id"], payload.media_id, payload.media_type, json.dumps(payload.payload), int(time.time())),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.delete("/api/v1/watchlist")
def delete_watchlist(media_id: int, media_type: str, authorization: Optional[str] = Header(default=None)):
    user = get_user_from_token(authorization)
    conn = db()
    try:
        conn.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND media_id = ? AND media_type = ?",
            (user["id"], media_id, media_type),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.get("/api/v1/tmdb")
def tmdb_proxy(
    request: Request,
    endpoint: str = Query(...),
    language: Optional[str] = "fr-FR",
):
    if not TMDB_API_KEY:
        raise HTTPException(status_code=500, detail="TMDB_API_KEY not configured")

    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    if not endpoint_allowed(endpoint):
        raise HTTPException(status_code=403, detail="Endpoint not allowed")

    rate_limit("global")

    params = {"api_key": TMDB_API_KEY, "language": language or "fr-FR"}
    for key, value in request.query_params.multi_items():
        if key in ("endpoint",):
            continue
        params[key] = value

    cache_key = endpoint + "?" + urllib.parse.urlencode(sorted(params.items()))
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    url = f"{TMDB_BASE}{endpoint}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            body = response.read().decode("utf-8")
        data = json.loads(body)
        cache_set(cache_key, data)
        return data
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"TMDB request failed: {exc}")


app.mount("/static", StaticFiles(directory="."), name="static")


@app.get("/")
def index_page():
    return FileResponse("index.html")


@app.get("/tendances")
def tendances_page():
    return FileResponse("tendances.html")


@app.get("/resultats")
def resultats_page():
    return FileResponse("resultats.html")


@app.get("/watchlist")
def watchlist_page():
    return FileResponse("watchlist.html")


@app.get("/title/{media_type}/{media_id}")
def detail_page(media_type: str, media_id: int):
    if media_type not in ("movie", "tv"):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse("detail.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
