import os

class Config:
    db_url = os.getenv('DATABASE_URL')
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    SQLALCHEMY_DATABASE_URI = db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv("SECRET_KEY")

    # CORS settings
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "https://portal.vaclaimguard.com")
    CORS_SUPPORTS_CREDENTIALS = True
