from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.models.schemas import AnalyzeRequest, AnalyzeResponse
from app.services.pipeline import QuantPipeline

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
pipeline = QuantPipeline()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse("app/static/index.html")


@app.get("/api/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "llm_enabled": settings.llm_provider != "mock" and bool(settings.llm_api_key),
        "akshare_enabled": settings.enable_akshare,
    }


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    return pipeline.analyze(request)
