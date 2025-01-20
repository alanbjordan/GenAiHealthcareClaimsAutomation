# routes/auth_routes.py

from flask import Blueprint, request, jsonify, g
from models.sql_models import Users, RefreshToken
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from config import Config
from datetime import datetime, timedelta
import os
import jwt
import uuid
import logging
from helpers.cors_helpers import pre_authorized_cors_preflight

auth_bp = Blueprint('auth_bp', __name__)

# ----- Sign-up Endpoint -----
@auth_bp.route('/signup', methods=['POST', 'OPTIONS'])
@pre_authorized_cors_preflight
def signup():
    data = request.get_json()
    logging.debug('Received signup request with data: %s', data)

    first_name = data.get('first_name')
    last_name = data.get('last_name')
    email = data.get('email')
    password = data.get('password')

    if not first_name or not last_name or not email or not password:
        logging.warning('Missing required fields in signup request')
        return jsonify({"error": "First name, last name, email, and password are required"}), 400

    # Check if user already exists
    existing_user = g.session.query(Users).filter(Users.email == email).first()
    if existing_user:
        logging.warning('User with email %s already exists', email)
        return jsonify({"error": "User with that email already exists"}), 409

    # Create a new user
    new_user = Users(
        first_name=first_name,
        last_name=last_name,
        email=email,
        user_uuid=str(uuid.uuid4())
    )
    new_user.set_password(password)
    logging.debug('Created new user object for email: %s', email)

    try:
        g.session.add(new_user)
        g.session.commit()
        logging.info('User with email %s created successfully', email)

        # Generate tokens
        access_token_str = create_jwt_token(new_user.user_uuid, new_user.email, expires_in_hours=1)
        refresh_token_str = create_jwt_token(new_user.user_uuid, new_user.email, expires_in_hours=24*30)

        # Store refresh token in DB
        decoded_refresh = decode_jwt_no_verify(refresh_token_str)
        exp_timestamp = decoded_refresh.get('exp')
        expires_dt = datetime.utcfromtimestamp(exp_timestamp)

        new_db_refresh = RefreshToken(
            user_id=new_user.user_id,
            token=refresh_token_str,
            expires_at=expires_dt
        )
        g.session.add(new_db_refresh)
        g.session.commit()

        return jsonify({
            "message": "User created successfully",
            "user_uuid": new_user.user_uuid,
            "user_id": new_user.user_id,
            "email": new_user.email,
            "first_name": new_user.first_name,
            "last_name": new_user.last_name,
            "access_token": access_token_str,
            "refresh_token": refresh_token_str,
        }), 201
    except Exception as e:
        g.session.rollback()
        logging.error('Failed to create user with email %s: %s', email, str(e))
        return jsonify({"error": f"Failed to create user: {str(e)}"}), 500

# Utility function to create JWT payload
def create_jwt_token(user_uuid, email, expires_in_hours=1):
    """
    Creates a JWT token with user_uuid, email, and an expiration.
    :param user_uuid: str
    :param email: str
    :param expires_in_hours: int
    :return: str (the JWT)
    """
    payload = {
        'user_uuid': user_uuid,
        'email': email,
        'exp': datetime.utcnow() + timedelta(hours=expires_in_hours)
    }
    return jwt.encode(payload, Config.SECRET_KEY, algorithm='HS256')

def decode_jwt_no_verify(token_str):
    """
    Decodes a JWT *without* verifying the signature, so we can read 'exp' if needed.
    Be sure to do a proper verification later in the flow.
    """
    return jwt.decode(token_str, options={"verify_signature": False, "verify_exp": False})

# ----- Login Endpoint -----
@auth_bp.route('/login', methods=['POST', 'OPTIONS'])
def login():
    data = request.get_json()
    logging.debug('Received login request with data: %s', data)

    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        logging.warning('Missing email or password in login request')
        return jsonify({"error": "Email and password are required"}), 400

    user = g.session.query(Users).filter_by(email=email).first()
    if user and user.check_password(password):
        logging.info('User with email %s logged in successfully', email)

        # 1) Short-lived Access Token (e.g. 1 hour)
        access_token_str = create_jwt_token(user.user_uuid, user.email, expires_in_hours=1)

        # 2) Long-lived Refresh Token (e.g. 30 days)
        refresh_token_str = create_jwt_token(user.user_uuid, user.email, expires_in_hours=24*30)

        # Insert refresh token record in the DB
        decoded_refresh = decode_jwt_no_verify(refresh_token_str)
        exp_timestamp = decoded_refresh.get('exp')  # e.g. 1695244001
        expires_dt = datetime.utcfromtimestamp(exp_timestamp)

        new_db_refresh = RefreshToken(
            user_id=user.user_id,
            token=refresh_token_str,
            expires_at=expires_dt
        )
        g.session.add(new_db_refresh)
        g.session.commit()

        return jsonify({
            "message": "Login successful",
            "user_id": user.user_id,
            "user_uuid": user.user_uuid,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "access_token": access_token_str,
            "refresh_token": refresh_token_str
        }), 200
    else:
        logging.warning('Invalid email or password for email %s', email)
        return jsonify({"error": "Invalid email or password"}), 401


# ----- Google Login Endpoint -----
@auth_bp.route('/google-login', methods=['POST', 'OPTIONS'])
def google_login():
    logging.debug('google/login backend hit')
    data = request.get_json()
    token = data.get('tokenId')
    logging.debug('Received Google login request with tokenId')

    if not token:
        logging.warning('Missing token in Google login request')
        return jsonify({"error": "Token is required"}), 400
    
    try:
        # Verify the Google ID token
        id_info = id_token.verify_oauth2_token(
            token, 
            google_requests.Request(), 
            os.getenv("GOOGLE_CLIENT_ID"), 
            clock_skew_in_seconds=20
        )
        email = id_info.get('email')
        first_name = id_info.get('given_name', '')
        last_name = id_info.get('family_name', '')
        google_id = id_info.get('sub')

        logging.debug(
            'Google ID token verified. Extracted info: email=%s, first_name=%s, last_name=%s', 
            email, first_name, last_name
        )

        # Check if user already exists
        user = g.session.query(Users).filter_by(email=email).first()

        # Flag to indicate if the user is new
        is_new_user = False

        # If user does not exist, create a new one
        if not user:
            user = Users(
                first_name=first_name,
                last_name=last_name,
                email=email,
                google_id=google_id,
                user_uuid=str(uuid.uuid4())
            )
            g.session.add(user)
            g.session.commit()
            logging.info('New Google user created with email %s', email)
            is_new_user = True

        # 1) Short-lived Access Token (1 hour)
        access_token_str = create_jwt_token(user.user_uuid, user.email, expires_in_hours=1)

        # 2) Long-lived Refresh Token (30 days)
        refresh_token_str = create_jwt_token(user.user_uuid, user.email, expires_in_hours=24*30)

        # Insert the refresh token into DB
        decoded_refresh = decode_jwt_no_verify(refresh_token_str)
        exp_timestamp = decoded_refresh.get('exp')
        expires_dt = datetime.utcfromtimestamp(exp_timestamp)

        new_db_refresh = RefreshToken(
            user_id=user.user_id,
            token=refresh_token_str,
            expires_at=expires_dt
        )
        g.session.add(new_db_refresh)
        g.session.commit()

        return jsonify({
            "message": "Login successful",
            "user_id": user.user_id,
            "user_uuid": user.user_uuid,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "isNewUser": is_new_user,
            "access_token": access_token_str,
            "refresh_token": refresh_token_str
        }), 200

    except ValueError as e:
        logging.error('Invalid token received for Google login: %s', str(e))
        return jsonify({"error": "Invalid token"}), 400
    except Exception as e:
        logging.error('Failed to handle Google login: %s', str(e))
        return jsonify({"error": f"Failed to handle Google login: {str(e)}"}), 500


# ----- Refresh Token Endpoint -----
@auth_bp.route('/refresh', methods=['POST', 'OPTIONS'])
@pre_authorized_cors_preflight
def refresh():
    """
    Expects JSON body: { "refresh_token": "<the long-lived token>" }
    Returns a new access_token if valid.
    """
    data = request.get_json() or {}
    refresh_token_str = data.get('refresh_token')

    if not refresh_token_str:
        return jsonify({"error": "refresh_token is required"}), 400

    # 1) Look up the token record in DB
    db_refresh = g.session.query(RefreshToken).filter_by(token=refresh_token_str).first()

    if not db_refresh:
        # Token not found in DB => invalid
        return jsonify({"error": "Invalid or revoked refresh token"}), 401

    # 2) Check if refresh token is expired at DB level
    if db_refresh.expires_at < datetime.utcnow():
        # Optionally delete this token from DB since it's expired
        g.session.delete(db_refresh)
        g.session.commit()
        return jsonify({"error": "Refresh token expired, please log in again"}), 401

    # 3) Decode & verify the token signature as well
    try:
        payload = jwt.decode(refresh_token_str, Config.SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        # The JWT claims are expired, so also remove from DB
        g.session.delete(db_refresh)
        g.session.commit()
        return jsonify({"error": "Refresh token expired, please log in again."}), 401
    except jwt.InvalidTokenError as e:
        # If the token signature is invalid, remove it from DB
        g.session.delete(db_refresh)
        g.session.commit()
        logging.error('Invalid refresh token: %s', str(e))
        return jsonify({"error": "Invalid refresh token"}), 401

    # If we reach here, token is valid + not expired
    user_uuid = payload.get('user_uuid')
    email = payload.get('email')

    # 4) Ensure user still exists
    user = g.session.query(Users).filter_by(user_uuid=user_uuid).first()
    if not user:
        # Also consider deleting or revoking the token
        g.session.delete(db_refresh)
        g.session.commit()
        return jsonify({"error": "User not found"}), 404

    # 5) Create new short-lived access token
    new_access_token_str = create_jwt_token(user_uuid, email, expires_in_hours=1)

    return jsonify({
        "access_token": new_access_token_str
    }), 200
