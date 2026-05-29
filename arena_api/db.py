from pathlib import Path
from sqlmodel import SQLModel, Session, create_engine
from arena_api.config import DB_PATH

Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

def init_db() -> None:
    from arena_api import models  # noqa: F401
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
