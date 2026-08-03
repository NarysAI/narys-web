# NarysAI Repository

Local, Git-backed catalog for AI-ready engineering drawings and PartCAD packages. Public packages are canonical in [`NarysAI/PUB`](https://github.com/NarysAI/PUB); private packages are held in the private `NarysAI/indra` overlay.

## Start on Windows

1. Install Docker Desktop and enable Docker Compose.
2. Copy `.env.example` to `.env` if you need non-default settings.
3. Run:

```powershell
docker compose up --build
```

Open [http://localhost:3000/repository](http://localhost:3000/repository). The frontend proxies `/api` to the API container, so the same-origin health endpoint is available at [http://localhost:3000/api/v1/health](http://localhost:3000/api/v1/health). Host ports `3000` and `8001` bind to loopback only; the direct API docs remain available to the local owner at [http://localhost:8001/docs](http://localhost:8001/docs). Override `NARYS_WEB_PORT` or `NARYS_API_PORT` only when the corresponding loopback port is unavailable.

The first start clones the index and packages and creates immutable commit-SHA snapshots. SQLite, checkouts, snapshots and previews are persisted below `./var`; the old named Docker volume is intentionally retained as a rollback backup.

Object pages use readable PartCAD paths compatible with the public repository. For example:

```text
http://localhost:3000/repository/part/electrical/battery/ego:battery-7_5
```

The catalog is generated entirely from `NarysAI/narys-index`; it does not depend on the PartCAD.org backend.

Public object and package links point to `NarysAI/PUB`. Private names are absent from guest catalog/search responses and private downloads use authenticated one-use tickets. NarysAI does not rewrite package paths or model geometry.

## Add a drawing package

Create a directory in `../PUB` containing a `partcad.yaml` and its source models:

```yaml
name: //pub/narysai/my-package
parts:
  my-part:
    type: stl
    path: models/my-part.stl
    desc: A manufacturable part.
```

Then add an import below the matching folder in [`NarysAI/narys-index`](https://github.com/NarysAI/narys-index):

```yaml
import:
  my-package:
    type: git
    url: https://github.com/NarysAI/PUB.git
    revision: main
    relPath: narysai/my-package
```

Commit and push the index change, then use **Оновити індекс** in the UI or call:

```powershell
$key = Read-Host "Admin API key"
Invoke-RestMethod -Method Post -Headers @{Authorization="Bearer $key"} http://localhost:3000/api/v1/catalog/refresh
```

For a private package, place it below `../indra/packages/<project>/<package>` and register its relative path in `../indra/index/partcad.yaml`. The repository must remain private.

## Access keys

Bootstrap an administrator locally (the plaintext is printed only once):

```powershell
docker compose run --rm api python -m app.admin create-key --name owner --role admin
```

Paste the key into the site header. Keys remain only in tab memory. Admins can create User keys and inspect audit/sync activity at `/repository/admin`. Production deployments must terminate HTTPS before enabling private access.

## Import and upstream export

`tools/migrate_pub.py` materializes the official index into PUB, records SHA-256 provenance and rejects files over 100 MiB. `tools/export_upstream.py` prepares a package-only upstream branch and excludes `.narys-*` metadata; add `--create-pr` only when the branch is ready to publish.

## Development

Docker Compose bind-mounts `backend/app`, `frontend/src`, and `frontend/index.html`, so both services reload after edits. Run tests independently with:

```powershell
docker compose run --rm api pytest -q
docker compose run --rm web npm test
```

## Sync upstream forks

```powershell
git -C ../partcad fetch upstream
git -C ../partcad checkout devel
git -C ../partcad merge --ff-only upstream/devel
git -C ../partcad push origin devel

git -C ../narys-index fetch upstream
git -C ../narys-index checkout main
git -C ../narys-index merge upstream/main
git -C ../narys-index push origin main
```

The NarysAI frontend is an independent implementation. Package ownership and licensing remain with each upstream maintainer; `license_status: unverified` is an explicit review warning, not a claim of NarysAI ownership.
