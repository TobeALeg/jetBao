from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.database import Database
from app.routers import admin, attachments, auth, expenses


def create_app() -> FastAPI:
    settings = Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.db.init(settings.seed_demo_users, settings.bootstrap_admin)
        yield

    app = FastAPI(title="JetBao Reimbursement API", lifespan=lifespan)
    app.state.settings = settings
    app.state.db = Database(settings.database_path)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8080", "http://localhost:8080"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(attachments.router)
    app.include_router(expenses.router)
    app.include_router(admin.router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
