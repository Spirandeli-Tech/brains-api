from fastapi import FastAPI
from app.api import health

app = FastAPI(title="AI Service API", version="1.0.0")

app.include_router(health.router)
