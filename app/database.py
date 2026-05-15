from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

_connect_args = {}
if "sslmode=require" in settings.database_url or "aivencloud.com" in settings.database_url:
    _connect_args["sslmode"] = "require"

engine = (
    create_engine(settings.database_url, connect_args=_connect_args)
    if _connect_args
    else create_engine(settings.database_url)
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()