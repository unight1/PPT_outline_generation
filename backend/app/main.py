import logging
import threading

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import health, tasks
from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def _warmup_retriever_background() -> None:
    """Initialize retrieval models once at startup so cold HF downloads are not charged to generation timeout."""

    def _run() -> None:
        log = logging.getLogger(__name__)
        try:
            from app.retrieval import get_retriever

            get_retriever(
                documents_dir=settings.retrieval_documents_dir,
                chroma_persist_dir=settings.retrieval_chroma_dir,
                tavily_api_key=settings.tavily_api_key or "",
            )
            log.info("Retriever warmup completed.")
        except Exception:
            log.exception("Retriever warmup failed; first generation may still trigger lazy load.")

    threading.Thread(target=_run, name="retriever-warmup", daemon=True).start()

app = FastAPI(
    title="PPT Outline API",
    description="PPT 大纲智能生成与内容补全 — 后端 API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")


@app.on_event("startup")
async def recover_inflight_generation_jobs() -> None:
    recovered = tasks.recover_inflight_generations()
    if recovered:
        logging.getLogger(__name__).warning("Recovered inflight generation jobs count=%s", recovered)
    if settings.retrieval_warmup_on_startup:
        _warmup_retriever_background()


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "INTERNAL_ERROR", "message": str(exc.detail), "details": {}}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "details": {"errors": jsonable_encoder(exc.errors())},
            }
        },
    )


@app.get("/")
def root() -> dict:
    return {"message": "PPT Outline API", "docs": "/docs"}
