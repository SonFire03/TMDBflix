# TMDB Explorer - Platform Edition

Vitrine cinema complete avec:
- backend `FastAPI` versionne (`/api/v1`)
- auth utilisateur (register/login)
- watchlist synchronisee en SQLite
- proxy TMDB securise (allowlist + cache + rate limit)
- page detail routable avec recommandations
- CI GitHub Actions + smoke tests

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
. .venv/bin/activate
uvicorn server:app --host 127.0.0.1 --port 8000
```

Ouvrir `http://127.0.0.1:8000`.

## Tests

```bash
. .venv/bin/activate
python tests/smoke_test.py
```

## Endpoints principaux

- `GET /api/v1/health`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `GET /api/v1/watchlist`
- `POST /api/v1/watchlist`
- `DELETE /api/v1/watchlist?media_id=...&media_type=...`
- `GET /api/v1/tmdb?endpoint=...`

## Pages

- `/` : vitrine principale
- `/title/{movie|tv}/{id}` : page detail + recommandations
