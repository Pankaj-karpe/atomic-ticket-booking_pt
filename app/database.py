from sqlalchemy import create_engine, URL
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings



engine = create_engine(settings.DATABASE_URL, pool_size=50,max_overflow=50,pool_timeout=30,pool_recycle=1800,)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()