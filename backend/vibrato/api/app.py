from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..config import Settings, configure, get_settings
from ..db import init_db
from ..logging_setup import get_logger, setup_logging
from ..tasks.manager import get_tasks, init_tasks
from .errors import install_error_handlers
from .routes import analysis, comparisons, extras, projects, recordings, system

log = get_logger("app")


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is not None:
        configure(settings)
    active = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        setup_logging(active.logs_dir)
        database = init_db(active.db_path, active.backups_dir)
        if database.recovery_status.get("recovered"):
            log.warning(str(database.recovery_status.get("message")))
        init_tasks(active.workers)
        from ..analysis.base import all_analyzers

        all_analyzers()
        log.info("Vibrato %s ready (data: %s)", __version__, active.data_dir)
        yield
        get_tasks().shutdown()

    app = FastAPI(
        title="Vibrato",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(GZipMiddleware, minimum_size=2048)
    install_error_handlers(app)
    for module in (projects, recordings, analysis, comparisons, extras, system):
        app.include_router(module.router, prefix="/api")
    dist = active.frontend_dist
    if dist is not None and (dist / "index.html").exists():
        assets = dist / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        @app.get("/{path:path}", include_in_schema=False, response_model=None)
        async def spa(path: str) -> Response:
            if path.startswith("api/"):
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": {
                            "code": "not_found",
                            "what": "Unknown API endpoint.",
                            "why": path,
                            "action": "Check the URL.",
                            "details": [],
                        }
                    },
                )
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and Path(dist).resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})
    else:

        @app.get("/", include_in_schema=False)
        async def root() -> JSONResponse:
            return JSONResponse(
                {
                    "name": "Vibrato API",
                    "version": __version__,
                    "frontend": "Not built. Run the frontend dev server or build it with 'npm run build' in frontend/.",
                }
            )

    return app
