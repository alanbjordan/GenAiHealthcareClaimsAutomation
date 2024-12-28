from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
import os

# Get the raw database URL from the environment
raw_db_url = os.getenv("DATABASE_URL")

# If the URL starts with postgres://, replace it with postgresql://
if raw_db_url and raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)

engine = create_engine(raw_db_url, pool_pre_ping=True)

# Create a configured "Session" class
SessionFactory = sessionmaker(bind=engine)

# Create a scoped session
ScopedSession = scoped_session(SessionFactory)
