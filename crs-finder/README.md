# crs-finder

Internal web application for identifying the coordinate reference system (CRS) that best places a geometry into a target dataset.

## Architecture

```
Browser → Nginx (port 8080)
            ├── /          → React frontend (static)
            └── /api/      → FastAPI backend
```

## Quick start

```bash
docker compose up --build
```

The application is available at http://localhost:8080.

The FastAPI interactive docs are proxied at http://localhost:8080/api/docs.

## Development

### Backend

```bash
cd crs-finder/backend
pip install -e ".[dev]"
uvicorn crs_finder.main:app --reload --port 8000
```

### Frontend

```bash
cd crs-finder/frontend
npm install
npm run dev   # http://localhost:5173  (proxies /api → localhost:8000)
```

## Project structure

```
crs-finder/
├── compose.yaml
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/crs_finder/
│       ├── main.py          # FastAPI application factory
│       ├── api/             # Route handlers (thin — delegate to services)
│       ├── models/          # Pydantic request/response models
│       └── services/        # Business logic / geospatial processing
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    └── src/
        ├── api/             # Generated/typed API client
        ├── components/      # Reusable UI components
        └── pages/           # Top-level page components
```
