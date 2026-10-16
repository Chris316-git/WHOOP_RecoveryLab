"""Create all tables. Safe to run more than once."""
import _bootstrap  # noqa: F401

from src.db.models import Base
from src.db.session import engine

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    print("Tables ready:", ", ".join(Base.metadata.tables))
