import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typing import Generator

env_path = Path(__file__).resolve().parents[2] / ".env"
if not env_path.exists():
    raise RuntimeError(f"Missing env file: {env_path}")
if not load_dotenv(env_path):
    raise RuntimeError(f"Failed to load env file: {env_path}")

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required (SQLite fallback is disabled)")

engine_args = {}
if DATABASE_URL.startswith('sqlite'):
    engine_args["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, echo=False, future=True, **engine_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def get_engine():
    return engine

def get_session() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
