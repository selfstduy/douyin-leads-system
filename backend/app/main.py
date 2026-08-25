from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1.router import api_router
from app.api.v1.openkf_spi import router as openkf_spi_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup / shutdown lifecycle."""
    # ── startup ──
    # Import models so that Alembic metadata is populated
    import app.models  # noqa: F401

    # 初始化默认系统配置
    from app.core.deps import async_session_factory
    from app.services.system_config_service import SystemConfigService
    async with async_session_factory() as session:
        try:
            inserted = await SystemConfigService.init_default_configs(session)
            await session.commit()
            if inserted > 0:
                print(f"[lifespan] Initialized {inserted} default system config(s)")
        except Exception as exc:
            await session.rollback()
            print(f"[lifespan] Failed to init default configs: {exc}")

    yield
    # ── shutdown ──
    # Dispose the async engine
    from app.core.deps import engine
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ─────────────────────────────────────────────────────────────────────
app.include_router(api_router, prefix=settings.API_V1_PREFIX)

# OpenKF SPI endpoints (no JWT, protected by AES-256-GCM envelope)
app.include_router(openkf_spi_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
