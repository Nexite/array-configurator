# Array Configurator

Browser app that packs solar cells onto a 2D vector outline (DXF, SVG, or HPGL), then lets you edit the layout by hand. Packing, checks, and export all run in the browser. There is no API.

## Run

```bash
docker compose up --build
```

Open http://localhost:8080

The container only serves the built files. You can also open `frontend/dist` with any static host after `npm run build`.

## Parameters

- **Cell footprint** — physical size used for packing and collisions
- **Usable / active W×H** — PV area that counts toward the target (can be smaller than the footprint)
- Cell gap, panel gap, max cells wide × tall, target area

Upload an outline, click regions to choose what to populate, then Generate.

## Local dev

```bash
cd frontend && npm install && node scripts/warm-pyodide.mjs && npm run dev
```

Open http://localhost:5173

Geometry tests:

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
PYTHONPATH=backend .venv/bin/pytest
```
