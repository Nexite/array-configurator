# Array Configurator

Dockerized web app that packs solar cells onto a 2D vector outline (DXF, SVG, PDF, and other common vector types), then lets you edit the layout by hand.

## Run

```bash
docker compose up --build
```

Open http://localhost:8080

## Parameters

- **Cell footprint** — physical size used for packing and collisions
- **Usable / active W×H** — PV area that counts toward the target (can be smaller than the footprint)
- Cell gap, panel gap, max cells wide × tall, target area

Load the included `TOPSHELL.DXF` sample, click regions to choose what to populate, then Generate.

## Local dev

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8080
# in another shell
cd frontend && npm install && npm run dev
```
