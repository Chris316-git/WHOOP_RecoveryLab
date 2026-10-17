"""Database engines and session factories.

`make_session_factory(url)` builds an independent factory for any database (tests, a second
environment, a future multi-tenant service). For convenience, `engine` and `SessionLocal`
remain available as lazily created module attributes bound to DATABASE_URL, so importing
this module no longer requires a database.
"""
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker


def normalize_url(url: str) -> str:
    # Supabase gives a URL starting with postgresql://. Use the psycopg 3 driver.
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def make_engine(url: str) -> Engine:
    return create_engine(normalize_url(url), pool_pre_ping=True)


def make_session_factory(url_or_engine) -> sessionmaker:
    engine = url_or_engine if isinstance(url_or_engine, Engine) else make_engine(url_or_engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@lru_cache(maxsize=1)
def default_session_factory() -> sessionmaker:
    from src.settings import Settings
    return make_session_factory(Settings.from_env().require("database_url"))


def __getattr__(name: str):  # PEP 562: lazy module attributes for existing scripts
    if name == "SessionLocal":
        return default_session_factory()
    if name == "engine":
        return default_session_factory().kw["bind"]
    raise AttributeError(name)
