from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import health
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.customers import router as customers_router
from app.api.invoices import router as invoices_router
from app.api.bank_accounts import router as bank_accounts_router
from app.core.config import settings
from app.core.firebase import init_firebase

app = FastAPI(title="AI Service API", version="1.0.0")

init_firebase()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(customers_router)
app.include_router(invoices_router)
app.include_router(bank_accounts_router)
