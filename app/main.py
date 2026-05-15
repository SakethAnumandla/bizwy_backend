from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import expenses, ocr, wallet, dashboard
from app.schemas import get_all_categories, get_category_hierarchy


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Expense Tracker API",
    description="Track expenses with manual entry and OCR scanning",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(expenses.router)
app.include_router(ocr.router)
app.include_router(wallet.router)
app.include_router(dashboard.router)

@app.get("/")
async def root():
    return {"message": "Expense Tracker API", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/categories")
async def list_categories():
    return get_all_categories()


@app.get("/categories/hierarchy")
async def category_hierarchy():
    return get_category_hierarchy()