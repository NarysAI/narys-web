# NarysAI Repository

Local, Git-backed catalog for AI-ready engineering drawings and PartCAD packages. It combines the NarysAI registry fork with an independent React interface and a FastAPI indexing/preview service.

## Start on Windows

1. Install Docker Desktop and enable Docker Compose.
2. Copy `.env.example` to `.env` if you need non-default settings.
3. Run:

```powershell
docker compose up --build
```

Open [http://localhost:3000/repository](http://localhost:3000/repository). The API is available at [http://localhost:8001/docs](http://localhost:8001/docs). Port `8001` avoids the services that commonly occupy port `8000`; override `NARYS_API_PORT` and `VITE_API_URL` together if needed.

The first start clones the index. Opening a package clones that package lazily. Git checkouts and generated GLB/PNG previews remain in the `narys-cache` Docker volume.

## Add a drawing package

Create a Git repository containing a `partcad.yaml` and its source models:

```yaml
name: //pub/narysai/my-package
parts:
  my-part:
    type: stl
    path: models/my-part.stl
    desc: A manufacturable part.
```

Then add an import to a `partcad.yaml` below the appropriate folder in [`NarysAI/narys-index`](https://github.com/NarysAI/narys-index):

```yaml
import:
  my-package:
    type: git
    url: https://github.com/NarysAI/my-package.git
    web: https://github.com/NarysAI/my-package
```

Commit and push the index change, then use **Оновити індекс** in the UI or call:

```powershell
Invoke-RestMethod -Method Post http://localhost:8001/api/v1/catalog/refresh
```

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

The NarysAI frontend is an independent implementation. It does not copy the unlicensed PartCAD.org website source or branding. Package ownership and licensing remain with each upstream maintainer.
