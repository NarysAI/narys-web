from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import partcad

from .catalog import CatalogError, CatalogService

logging.basicConfig(level=os.getenv("NARYS_LOG_LEVEL", "INFO"))
logger = logging.getLogger("narys")

service = CatalogService(
    index_url=os.getenv("NARYS_INDEX_URL", "https://github.com/NarysAI/narys-index.git"),
    index_ref=os.getenv("NARYS_INDEX_REF", "main"),
    cache_dir=Path(os.getenv("NARYS_CACHE_DIR", ".cache/narys")),
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        service.refresh()
    except Exception:
        logger.exception("Initial catalog refresh failed")
    yield


app = FastAPI(title="NarysAI Catalog API", version="0.1.0", lifespan=lifespan)
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
        "partcad_version": getattr(partcad, "__version__", "unknown"),
        "packages": len(service.packages),
        "objects": len(service.objects),
    }


@app.get("/api/v1/catalog")
def catalog():
    return service.catalog()


@app.get("/api/v1/search")
def search(q: str = Query(min_length=1, max_length=120)):
    return {"query": q, "results": service.search(q)}


@app.get("/api/v1/packages/{package_id}")
def package(package_id: str):
    try:
        return service.load_package(package_id)
    except KeyError as exc:
        raise HTTPException(404, "Package not found") from exc
    except CatalogError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/objects/{object_id}")
def object_detail(object_id: str):
    try:
        return service.object_detail(object_id)
    except KeyError as exc:
        raise HTTPException(404, "Object not found") from exc


@app.get("/api/v1/by-path/{kind}/{semantic_path:path}")
def object_by_path(kind: str, semantic_path: str):
    try:
        return service.object_by_path(kind, semantic_path)
    except KeyError as exc:
        raise HTTPException(404, "Object path not found in the indexed PartCAD registry") from exc


@app.get("/api/v1/objects/{object_id}/preview.gltf")
def preview(object_id: str):
    try:
        return FileResponse(service.preview(object_id), media_type="model/gltf-binary", filename=f"{object_id}.glb")
    except KeyError as exc:
        raise HTTPException(404, "Object not found") from exc
    except CatalogError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/objects/{object_id}/source")
def object_source(object_id: str):
    try:
        source = service.source_file(object_id)
        return FileResponse(source, filename=source.name, media_type="application/octet-stream")
    except KeyError as exc:
        raise HTTPException(404, "Object not found") from exc
    except CatalogError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/packages/{package_id}/archive.zip")
def package_archive(package_id: str):
    try:
        archive = service.package_archive(package_id)
        return FileResponse(archive, filename=f"narys-{service.package_detail(package_id)['name']}.zip", media_type="application/zip")
    except KeyError as exc:
        raise HTTPException(404, "Package not found") from exc
    except CatalogError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/objects/{object_id}/thumbnail.png")
def thumbnail(object_id: str):
    try:
        return FileResponse(service.thumbnail(object_id), media_type="image/png")
    except KeyError as exc:
        raise HTTPException(404, "Object not found") from exc


@app.post("/api/v1/catalog/refresh")
def refresh():
    try:
        return {"status": "refreshed", **service.refresh()}
    except CatalogError as exc:
        raise HTTPException(502, str(exc)) from exc
