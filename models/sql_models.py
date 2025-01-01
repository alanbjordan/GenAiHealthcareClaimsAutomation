# sql_models.py contains the SQLAlchemy models for the database tables used in the application.

from datetime import datetime
import uuid

from database import db, bcrypt
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy import Table, Column, Integer, ForeignKey, String, DateTime, func


class Users(db.Model):
    __tablename__ = 'users'

    user_id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(255), nullable=False)
    last_name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)  # Nullable for Google users
    google_id = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    user_uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    # Relationships
    service_periods = db.relationship('ServicePeriod', back_populates='user', cascade="all, delete-orphan", lazy='select')
    files = db.relationship('File', back_populates='user', cascade="all, delete-orphan", lazy='select')
    conditions = db.relationship('Conditions', back_populates='user', cascade="all, delete-orphan", lazy='select')

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)


class File(db.Model):
    __tablename__ = 'files'

    file_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    file_url = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(50), nullable=False)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    file_size = db.Column(db.Integer, nullable=True)
    file_category = db.Column(db.String(50), nullable=False)

    user = db.relationship('Users', back_populates='files', lazy='select')


class ServicePeriod(db.Model):
    __tablename__ = 'service_periods'

    service_period_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    branch_of_service = db.Column(db.String(255), nullable=True)
    service_start_date = db.Column(db.Date, nullable=False)
    service_end_date = db.Column(db.Date, nullable=False)

    user = db.relationship('Users', back_populates='service_periods', lazy='select')

# Association Table for conditions and tags
condition_tags = Table(
    'condition_tags',
    db.Model.metadata,
    Column('condition_id', Integer, ForeignKey('conditions.condition_id', ondelete='CASCADE'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.tag_id', ondelete='CASCADE'), primary_key=True)
)

class Conditions(db.Model):
    __tablename__ = 'conditions'

    condition_id = db.Column(db.Integer, primary_key=True)
    service_connected = db.Column(db.Boolean, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)
    file_id = db.Column(db.Integer, db.ForeignKey('files.file_id'), nullable=True)
    page_number = db.Column(db.Integer, nullable=True)
    condition_name = db.Column(db.String(255), nullable=False)
    date_of_visit = db.Column(db.Date, nullable=True)
    medical_professionals = db.Column(db.String(255), nullable=True)
    medications_list = db.Column(ARRAY(db.String(255)), nullable=True)
    treatments = db.Column(db.TEXT, nullable=True)
    findings = db.Column(db.TEXT, nullable=True)
    comments = db.Column(db.TEXT, nullable=True)
    is_ratable = db.Column(db.Boolean, nullable=True, default=True)
    in_service = db.Column(db.Boolean, nullable=False, default=False)

    user = db.relationship('Users', back_populates='conditions', lazy='select')
    embedding = db.relationship("ConditionEmbedding", back_populates="conditions", uselist=False, lazy='select')
    tags = db.relationship('Tag', secondary=condition_tags, back_populates='conditions', lazy='select')


class ConditionEmbedding(db.Model):
    __tablename__ = 'condition_embeddings'
    
    embedding_id = db.Column(db.Integer, primary_key=True)
    condition_id = db.Column(db.Integer, ForeignKey('conditions.condition_id', ondelete='CASCADE'), nullable=False)
    embedding = db.Column(Vector(3072))  # Ensure pgvector is properly configured
    
    conditions = db.relationship("Conditions", back_populates="embedding", lazy='select')


class Tag(db.Model):
    __tablename__ = 'tags'
    
    tag_id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.Integer, nullable=False)
    disability_name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    embeddings = db.Column(Vector(3072))  # Ensure pgvector is properly configured
    
    conditions = db.relationship(
        'Conditions',
        secondary=condition_tags,
        back_populates='tags',
        lazy='select'
    )

class UserDecisionSaves(db.Model):
    __tablename__ = 'user_decision_saves'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    decision_citation = db.Column(db.String(255), nullable=False)
    notes = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('Users', backref='saved_decisions', lazy='select')

class Waitlist(db.Model):
    __tablename__ = 'waitlist'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255))
    veteran_status = db.Column(db.String(10))   # e.g. "yes" or "no"
    service_branch = db.Column(db.String(50))   # e.g. "army", "navy", etc.
    signup_date = db.Column(db.DateTime, default=func.now())
    theme_mode = db.Column(db.String(10), default='light')
    country = db.Column(db.String(50))
    region = db.Column(db.String(50))
    city = db.Column(db.String(50))
    zip_code = db.Column(db.String(20))

class NexusTags(db.Model):
    __tablename__ = 'nexus_tags'

    nexus_tags_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.tag_id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    discovered_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Relationships
    tag = db.relationship('Tag', backref='nexus_tags', lazy='select')
    user = db.relationship('Users', backref='nexus_tags', lazy='select')