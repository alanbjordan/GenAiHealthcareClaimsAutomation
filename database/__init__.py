# database/__init__.py
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt

# Initialize SQLAlchemy and Bcrypt
db = SQLAlchemy()
bcrypt = Bcrypt()

# Other database-related code (optional)
