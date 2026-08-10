from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .catalog import CatalogError, CatalogService
from .auth import AuthService, Principal
from .snapshots import SnapshotManager

logging.basicConfig(level=os.getenv("NARYS_LOG_LEVEL", "INFO"))
logger = logging.getLogger("narys")

cache_root = Path(os.getenv("NARYS_CACHE_DIR", ".cache/narys"))
private_repository = Path(os.environ["NARYS_PRIVATE_REPO_DIR"]) if os.getenv("NARYS_PRIVATE_REPO_DIR") else None
public_repository = Path(os.environ["NARYS_PUBLIC_REPO_DIR"]) if os.getenv("NARYS_PUBLIC_REPO_DIR") else None
snapshots = SnapshotManager(cache_root / "snapshots")
environment = os.getenv("NARYS_ENV", "development")


def repository_view(name: str, repository: Path | None) -> Path | None:
    if environment == "production" and repository and (repository / ".git").is_dir():
        return snapshots.activate(name, repository)
    return repository


private_snapshot = repository_view("indra", private_repository)
public_snapshot = repository_view("PUB", public_repository)
service = CatalogService(
    index_url=os.getenv("NARYS_INDEX_URL", "https://github.com/NarysAI/narys-index.git"),
    index_ref=os.getenv("NARYS_INDEX_REF", "main"),
    cache_dir=cache_root,
    private_repo_dir=private_snapshot,
    public_repo_dir=public_snapshot,
    index_dir=Path(os.environ["NARYS_INDEX_DIR"]) if os.getenv("NARYS_INDEX_DIR") else None,
    github_token_file=Path(os.environ["NARYS_GITHUB_TOKEN_FILE"])
    if os.getenv("NARYS_GITHUB_TOKEN_FILE")
    else None,
)
auth = AuthService(service.database_path)


def _require_private_transport(request: Request) -> None:
    if os.getenv("NARYS_ENV", "development") == "production":
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        if scheme != "https":
            raise HTTPException(426, "HTTPS is required for private access")


def optional_principal(request: Request, authorization: str | None = Header(default=None)) -> Principal | None:
    if not authorization:
        return None
    _require_private_transport(request)
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid authorization scheme")
    principal = auth.authenticate(authorization.removeprefix("Bearer ").strip())
    if not principal:
        raise HTTPException(401, "Invalid or revoked API key")
    return principal


def require_user(principal: Principal | None = Depends(optional_principal)) -> Principal:
    if not principal:
        raise HTTPException(401, "API key required")
    return principal


def require_admin(principal: Principal = Depends(require_user)) -> Principal:
    if principal.role != "admin":
        raise HTTPException(403, "Admin role required")
    return principal


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        service.refresh()
    except Exception:
        logger.exception("Initial catalog refresh failed")
    yield


app = FastAPI(title="NarysAI Catalog API", version="0.4.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/v1/health")
def health():
    return {
        "status": "ok",
        "packages": len(service.packages),
        "objects": len(service.objects),
    }


@app.get("/api/v1/catalog")
def catalog(principal: Principal | None = Depends(optional_principal)):
    return service.catalog(include_private=principal is not None)


@app.get("/api/v1/search")
def search(q: str = Query(min_length=1, max_length=120), principal: Principal | None = Depends(optional_principal)):
    return {"query": q, "results": service.search(q, include_private=principal is not None)}


@app.get("/api/v1/packages/{package_id}")
def package(package_id: str, principal: Principal | None = Depends(optional_principal)):
    try:
        service.package_detail(package_id, include_private=principal is not None)
        service.load_package(package_id)
        detail = service.package_detail(package_id, include_private=principal is not None)
        if detail["entry_type"] != "project" and not detail["objects"]:
            raise KeyError(package_id)
        return detail
    except KeyError as exc:
        raise HTTPException(404, "Package not found") from exc
    except CatalogError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/objects/{object_id}")
def object_detail(object_id: str, principal: Principal | None = Depends(optional_principal)):
    try:
        return service.object_detail(object_id, include_private=principal is not None)
    except KeyError as exc:
        raise HTTPException(404, "Object not found") from exc


@app.get("/api/v1/by-path/{kind}/{semantic_path:path}")
def object_by_path(kind: str, semantic_path: str, principal: Principal | None = Depends(optional_principal)):
    try:
        return service.object_by_path(kind, semantic_path, include_private=principal is not None)
    except KeyError as exc:
        raise HTTPException(404, "Object path not found in the indexed PartCAD registry") from exc


@app.get("/api/v1/objects/{object_id}/preview.gltf")
def preview(
    object_id: str,
    request: Request,
    principal: Principal | None = Depends(optional_principal),
):
    try:
        service.object_detail(object_id, include_private=principal is not None)
        query_items = list(request.query_params.multi_items())
        if len({key for key, _ in query_items}) != len(query_items):
            raise CatalogError("Duplicate preview parameter")
        overrides = dict(query_items)
        overrides.pop("v", None)
        return FileResponse(
            service.preview(object_id, overrides),
            media_type="model/gltf-binary",
            filename=f"{object_id}.glb",
        )
    except KeyError as exc:
        raise HTTPException(404, "Object not found") from exc
    except CatalogError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/objects/{object_id}/source")
def object_source(object_id: str):
    try:
        item = service.object_detail(object_id)
        if item["visibility"] == "private":
            raise KeyError(object_id)
        source = service.source_file(object_id)
        return FileResponse(source, filename=source.name, media_type="application/octet-stream")
    except KeyError as exc:
        raise HTTPException(404, "Object not found") from exc
    except CatalogError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/objects/{object_id}/representations/{source_format}/preview.gltf")
def representation_preview(
    object_id: str,
    source_format: str,
    request: Request,
    principal: Principal | None = Depends(optional_principal),
):
    try:
        service.object_detail(object_id, include_private=principal is not None)
        query_items = list(request.query_params.multi_items())
        if len({key for key, _ in query_items}) != len(query_items):
            raise CatalogError("Duplicate preview parameter")
        overrides = dict(query_items)
        overrides.pop("v", None)
        return FileResponse(
            service.preview(object_id, overrides, source_format),
            media_type="model/gltf-binary",
            filename=f"{object_id}-{source_format}.glb",
        )
    except KeyError as exc:
        raise HTTPException(404, "Representation not found") from exc
    except CatalogError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/objects/{object_id}/representations/{source_format}/source")
def object_representation_source(object_id: str, source_format: str):
    try:
        item = service.object_detail(object_id)
        if item["visibility"] == "private":
            raise KeyError(object_id)
        source = service.representation_file(object_id, source_format)
        return FileResponse(source, filename=source.name, media_type="application/octet-stream")
    except KeyError as exc:
        raise HTTPException(404, "Representation not found") from exc
    except CatalogError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/packages/{package_id}/archive.zip")
def package_archive(package_id: str, principal: Principal | None = Depends(optional_principal)):
    try:
        package = service.package_detail(package_id, include_private=principal is not None)
        if package["visibility"] == "private":
            raise HTTPException(403, "Private packages must be downloaded with a one-time ticket")
        archive = service.package_archive(package_id)
        return FileResponse(archive, filename=f"narys-{service.package_detail(package_id)['name']}.zip", media_type="application/zip")
    except KeyError as exc:
        raise HTTPException(404, "Package not found") from exc
    except CatalogError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/objects/{object_id}/thumbnail.png")
def thumbnail(object_id: str, principal: Principal | None = Depends(optional_principal)):
    try:
        service.object_detail(object_id, include_private=principal is not None)
        return FileResponse(service.thumbnail(object_id), media_type="image/png")
    except KeyError as exc:
        raise HTTPException(404, "Object not found") from exc


@app.get("/api/v1/auth/me")
def me(principal: Principal = Depends(require_user)):
    return {"key_id": principal.key_id, "name": principal.name, "role": principal.role}


@app.post("/api/v1/download-tickets")
def create_download_ticket(payload: dict, principal: Principal = Depends(require_user)):
    object_id = str(payload.get("object_id", ""))
    try:
        item = service.object_detail(object_id, include_private=True)
    except KeyError as exc:
        raise HTTPException(404, "Object not found") from exc
    if item["visibility"] != "private":
        raise HTTPException(422, "Download tickets are only used for private objects")
    return {"ticket": auth.create_ticket(object_id, principal), "expires_in": 60}


@app.get("/api/v1/downloads/{ticket}")
def ticket_download(ticket: str, request: Request):
    _require_private_transport(request)
    consumed = auth.consume_ticket(ticket)
    if not consumed:
        raise HTTPException(410, "Download ticket is expired or already used")
    object_id, _ = consumed
    try:
        source = service.source_file(object_id)
        return FileResponse(source, filename=source.name, media_type="application/octet-stream")
    except (KeyError, CatalogError) as exc:
        raise HTTPException(404, "Private source file not found") from exc


@app.get("/api/v1/admin/keys")
def admin_keys(_: Principal = Depends(require_admin)):
    return {"keys": auth.list_keys()}


@app.post("/api/v1/admin/keys")
def admin_create_key(payload: dict, principal: Principal = Depends(require_admin)):
    try:
        plaintext, metadata = auth.create_key(str(payload.get("name", "")), str(payload.get("role", "user")))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    auth.audit(principal.key_id, "key.create", metadata["key_id"], "ok")
    return {**metadata, "key": plaintext}


@app.post("/api/v1/admin/keys/{key_id}/revoke")
def admin_revoke_key(key_id: str, principal: Principal = Depends(require_admin)):
    if key_id == principal.key_id:
        raise HTTPException(409, "An admin cannot revoke the active key")
    if not auth.revoke_key(key_id):
        raise HTTPException(404, "Active key not found")
    auth.audit(principal.key_id, "key.revoke", key_id, "ok")
    return {"status": "revoked"}


@app.get("/api/v1/admin/audit")
def admin_audit(_: Principal = Depends(require_admin)):
    return {"entries": auth.audit_entries()}


@app.get("/api/v1/admin/sync-runs")
def admin_sync_runs(_: Principal = Depends(require_admin)):
    return {"runs": auth.sync_runs()}


@app.post("/api/v1/catalog/refresh")
def refresh(principal: Principal = Depends(require_admin)):
    run_id = auth.start_sync()
    try:
        service.public_repo_dir = repository_view("PUB", public_repository)
        service.private_repo_dir = repository_view("indra", private_repository)
        result = {"status": "refreshed", **service.refresh()}
        auth.finish_sync(run_id, "complete", result)
        auth.audit(principal.key_id, "catalog.refresh", None, "ok")
        return result
    except CatalogError as exc:
        auth.finish_sync(run_id, "failed", {"error": str(exc)})
        raise HTTPException(502, str(exc)) from exc
