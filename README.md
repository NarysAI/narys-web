# NarysAI Repository

Local, Git-backed catalog for AI-ready engineering drawings, PartCAD packages,
and active CAD projects. Released public packages are canonical in
[`NarysAI/PUB`](https://github.com/NarysAI/PUB). Open projects use a small PUB
pointer while their editable history remains in a standalone Git repository.
Private standalone repositories are registered through the private
`NarysAI/indra` overlay.

## Platform ports

- `http://localhost:3100` is the test platform used for preview and acceptance checks.
- `http://localhost:3000` is the production platform port.

Never treat a successful check on port `3100` as proof that production is available; production health must be verified separately on port `3000` and through the public HTTPS domain.

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

Public package links point to `NarysAI/PUB`; project links point to their
canonical Git repositories and contribution workflows. Private names are absent
from guest catalog/search responses and private downloads use authenticated
one-use tickets. NarysAI does not rewrite package paths or model geometry.

The catalog UI is unified: use its type, category, and access filters to move
between published drawings and active projects without changing URL contracts.

## Add a drawing package

Create a directory in `../PUB` containing a `partcad.yaml` and its source models:

```yaml
name: //pub/narysai/my-package
parts:
  camera-module:
    type: scad
    path: camera-module.scad
    model_role: electronic_component
    desc: AI-readable representation of a real electronic component.
  printable-bracket:
    type: freecad
    path: printable-bracket.FCStd
    model_role: printable_part
    desc: Editable FreeCAD master for a printable custom part.
```

The role and source format are enforced by the backend. Electronic, purchased,
and other real-world components use SCAD only. Printable/manufacturable custom
parts use FreeCAD FCStd only; STL and STEP are generated derivatives.

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

## Add an open project

An open project keeps its editable files in a standalone Git repository. Add
`narys_project` to that repository's `partcad.yaml` and repeat the same metadata
in a source-free PUB pointer:

```yaml
name: //pub/fpv/case-holder
desc: Editable FPV Case_holder project.
narys_project:
  schema_version: 1
  kind: project
  access: public
  canonical_repo: https://github.com/NarysAI/Case_holder
  default_branch: main
  contribution_url: https://github.com/NarysAI/Case_holder/blob/main/CONTRIBUTING.md
  issues_url: https://github.com/NarysAI/Case_holder/issues
  current_drawing: drawing-v1.0.0
  category: FPV
```

The `narys-index` import points to the canonical project repository. The PUB
pointer contains no `parts`, `assemblies`, `sketches`, or CAD assets.

## Add a private project

Register a standalone private Git repository in `indra/index/partcad.yaml`:

```yaml
import:
  comp-ivins-case-4:
    type: git
    url: https://github.com/NarysAI/COMP-IVINS-CASE-4.git
    catalog_path: projects/comp-ivins-case-4
    revision: main
    category: private
    narys_project:
      schema_version: 1
      kind: project
      access: private
      canonical_repo: https://github.com/NarysAI/COMP-IVINS-CASE-4
      default_branch: main
```

The production API reads a fine-grained, read-only GitHub token from a Docker
secret. Copy `docker-compose.private.yml.example` outside the repository or use
it as an explicit override, set `NARYS_GITHUB_TOKEN_PATH` to a root-readable
secret file on the host, and start Compose with both files. The token is passed
to Git through an askpass environment and is never placed in a clone URL, log,
or catalog database.

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

## Production recovery and rollout

Before updating production, back up the Caddy configuration, Compose files, and
`var/catalog.sqlite3`. Start the new Compose project on alternate loopback ports,
verify `/api/v1/health`, guest/private visibility, search, and project links,
then switch the Caddy upstream. Roll back by restoring the previous image/commit
and database backup; never rewrite published catalog or drawing tags.

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
