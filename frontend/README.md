# FDMS React Frontend

Optional React dashboard for FDMS Control Panel.

## Setup

```bash
cd frontend
npm install
```

## Development

Start Django (with staff user logged in), then:

```bash
npm run dev
```

Vite proxies `/api` and `/fdms` to Django (http://127.0.0.1:8000). Log in at http://127.0.0.1:8000/admin/ first so session cookies apply.

## Build

```bash
npm run build
```

Output in `dist/`. Serve from Django static files or a separate static server.
