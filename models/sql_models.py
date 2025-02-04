# sql_models.py contains the SQLAlchemy models for the database tables used in the application.

from datetime import datetime
import uuid
import random
import string

from database import db, bcrypt
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy import Table, Column, Integer, ForeignKey, String, DateTime, func, Text


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

    # New Fields for Credits
    credits_remaining = db.Column(db.Integer, nullable=False, default=0)
    total_tokens_used = db.Column(db.Integer, nullable=False, default=0)

    # Relationships
    service_periods = db.relationship('ServicePeriod', back_populates='user', cascade="all, delete-orphan", lazy='select')
    files = db.relationship('File', back_populates='user', cascade="all, delete-orphan", lazy='select')
    conditions = db.relationship('Conditions', back_populates='user', cascade="all, delete-orphan", lazy='select')
    saved_decisions = db.relationship('UserDecisionSaves', back_populates='user', cascade="all, delete-orphan", lazy='select')
    chat_threads = db.relationship(
    'ChatThread',
    back_populates='user',
    cascade="all, delete-orphan",
    lazy='select'
)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<Users user_id={self.user_id} email={self.email}>"


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
    status = db.Column(db.String(50), nullable=False, default='Uploading')

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
    decision_url = db.Column(db.String(500), nullable=False)
    notes = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('Users', back_populates='saved_decisions', lazy='select')


class Waitlist(db.Model):
    __tablename__ = 'waitlist'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(255))  # Added first_name
    last_name = db.Column(db.String(255))   # Added last_name
    veteran_status = db.Column(db.String(10))  # e.g., "yes" or "no"
    service_branch = db.Column(db.String(50))  # e.g., "army", "navy", etc.
    signup_date = db.Column(db.DateTime, default=func.now())

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

class NexusSummary(db.Model):
    __tablename__ = 'nexus_summaries'

    nexus_summary_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nexus_tags_id = db.Column(db.Integer, db.ForeignKey('nexus_tags.nexus_tags_id', ondelete='CASCADE'), nullable=False)
    summary_text = db.Column(db.Text, nullable=True)
    condition_ids = db.Column(ARRAY(db.Integer), nullable=True)
    needs_update = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime, onupdate=func.now())
    # Relationship back to NexusTags
    nexus_tag = db.relationship('NexusTags', backref=db.backref('nexus_summaries', lazy='select', cascade='all, delete-orphan'))

class RefreshToken(db.Model):
    __tablename__ = 'refresh_tokens'

    refresh_token_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    token = db.Column(db.Text, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship back to the Users model
    user = db.relationship('Users', backref='refresh_tokens', lazy='select')

class SubscriptionPlan(db.Model):
    __tablename__ = 'subscription_plans'

    plan_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    monthly_credits = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)  # Monthly subscription fee
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user_subscriptions = db.relationship(
        'UserSubscription',
        back_populates='plan',
        cascade="all, delete-orphan",
        lazy='select'
    )

    def __repr__(self):
        return f"<SubscriptionPlan {self.name}>"
    
class TokenBundlePurchase(db.Model):
    __tablename__ = 'token_bundles'

    purchase_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    bundle_type_id = db.Column(db.Integer, db.ForeignKey('token_bundle_catalog.bundle_type_id', ondelete='RESTRICT'), nullable=False)
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    final_price = db.Column(db.Numeric(10, 2), nullable=False)
    # Optional: store the tokens actually added, in case you override the default
    tokens_added = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f"<TokenBundlePurchase id={self.purchase_id} user_id={self.user_id}>"

class TokenBundleCatalog(db.Model):
    __tablename__ = 'token_bundle_catalog'

    bundle_type_id = db.Column(db.Integer, primary_key=True)
    tokens = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    description = db.Column(db.String(255), nullable=True)  # Optional

    def __repr__(self):
        return f"<TokenBundleCatalog id={self.bundle_type_id} tokens={self.tokens}>"

class UserSubscription(db.Model):
    __tablename__ = 'user_subscriptions'

    subscription_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plans.plan_id', ondelete='RESTRICT'), nullable=False)
    start_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    end_date = db.Column(db.DateTime, nullable=True)      # For canceled or expired subscriptions
    status = db.Column(db.String(50), default='active', nullable=False)  # e.g., 'active', 'canceled', etc.
    next_billing_date = db.Column(db.DateTime, nullable=True)            # When to bill again
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    #user = db.relationship('Users', back_populates='user_subscriptions', lazy='select')
    plan = db.relationship('SubscriptionPlan', back_populates='user_subscriptions', lazy='select')

    def __repr__(self):
        return f"<UserSubscription subscription_id={self.subscription_id} user_id={self.user_id} plan_id={self.plan_id}>"

class OpenAIUsageLog(db.Model):
    __tablename__ = 'openai_usage_logs'

    usage_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    model = db.Column(db.String(255), nullable=False)
    prompt_tokens = db.Column(db.Integer, nullable=False, default=0)
    completion_tokens = db.Column(db.Integer, nullable=False, default=0)
    total_tokens = db.Column(db.Integer, nullable=False, default=0)
    cost = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Optional relationship back to Users
    user = db.relationship('Users', backref='openai_usage_logs', lazy='select')

    def __repr__(self):
        return f"<OpenAIUsageLog usage_id={self.usage_id} user_id={self.user_id} model={self.model}>"

class ChatThread(db.Model):
    __tablename__ = 'chat_threads'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # A unique ID for your frontend/client to reference
    thread_id = db.Column(db.String(64), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = db.relationship('Users', back_populates='chat_threads', lazy='select')
    messages = db.relationship('ChatMessage', back_populates='thread', cascade='all, delete-orphan', lazy='select')


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    thread_id = db.Column(db.String(64), db.ForeignKey('chat_threads.thread_id', ondelete='CASCADE'), nullable=False)
    is_bot = db.Column(db.Boolean, default=False, nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationship back to ChatThread
    thread = db.relationship('ChatThread', back_populates='messages', lazy='select')

class SupportMessage(db.Model):
    __tablename__ = 'support_messages'

    support_message_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='SET NULL'), nullable=True)
    rating = db.Column(db.Integer, nullable=False)
    issue_type = db.Column(db.String(50), nullable=False, default='general')
    feedback = db.Column(db.Text, nullable=False)
    first_name = db.Column(db.String(255), nullable=False)
    last_name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    branch_of_service = db.Column(db.String(255), nullable=False)

    # Ticket number with a UNIQUE constraint to prevent duplicates
    ticket_number = db.Column(db.String(30), nullable=False, unique=True)

    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    # Relationship back to the Users table
    user = db.relationship("Users", backref="support_messages", lazy='select')

    def __init__(self, user_id, rating, issue_type, feedback,
                 first_name, last_name, email, branch_of_service,
                 ticket_number):
        self.user_id = user_id
        self.rating = rating
        self.issue_type = issue_type
        self.feedback = feedback
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
        self.branch_of_service = branch_of_service
        self.ticket_number = ticket_number

    def __repr__(self):
        return (f"<SupportMessage ticket={self.ticket_number} "
                f"user={self.user_id} rating={self.rating} issue={self.issue_type}>")
    
class Claims(db.Model):
    __tablename__ = 'claims'

    claim_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    # Optional: link a claim to a condition if you want to reference it.
    condition_id = Column(Integer, ForeignKey('conditions.condition_id', ondelete='SET NULL'), nullable=True)
    claim_name = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default='Draft')  # e.g., Draft, In-Progress, Submitted
    description = Column(Text, nullable=True)
    evidence_progress = Column(Integer, nullable=False, default=0)  # Percent complete, e.g., 0-100
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Claims claim_id={self.claim_id} claim_name={self.claim_name}>"