import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    # default to sqlite for easy local dev if DATABASE_URL not provided
    DATABASE_URL = 'sqlite:///./docfoundry.db'

engine_args = {}
if DATABASE_URL.startswith('sqlite'):
    engine_args = {"connect_args": {"check_same_thread": False}}

engine = create_engine(DATABASE_URL, echo=False, future=True, **engine_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def get_engine():
    return engine

def get_session():
    return SessionLocal()
