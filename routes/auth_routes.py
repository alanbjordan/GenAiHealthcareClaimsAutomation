# routes/auth_routes.py

from flask import Blueprint, request, jsonify
from models.sql_models import *  # Correct absolute import for Users
#from database import db  # Correct absolute import for db
import uuid
import logging
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import os
import jwt
from datetime import datetime, timedelta
from config import Config
from database.session import ScopedSession

# Create a Blueprint for auth routes
auth_bp = Blueprint('auth_bp', __name__)

session=ScopedSession()
# ----- Sign-up Endpoint -----
@auth_bp.route('/signup', methods=['POST'])
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

    if session.query(Users).filter(Users.email == email).first():
        logging.warning('User with email %s already exists', email)
        return jsonify({"error": "User with that email already exists"}), 409

    new_user = Users(
        first_name=first_name,
        last_name=last_name,
        email=email,
        user_uuid=str(uuid.uuid4())
    )
    new_user.set_password(password)
    logging.debug('Created new user object for email: %s', email)

    try:
        session.add(new_user)
        session.commit()
        logging.info('User with email %s created successfully', email)
        return jsonify({
            "message": "User created successfully",
            "user_uuid": new_user.user_uuid,
            "user_id": new_user.user_id,
        }), 201
    except Exception as e:
        session.rollback()
        logging.error('Failed to create user with email %s: %s', email, str(e))
        return jsonify({"error": f"Failed to create user: {str(e)}"}), 500


# ----- Login Endpoint -----
@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    logging.debug('Received login request with data: %s', data)

    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        logging.warning('Missing email or password in login request')
        return jsonify({"error": "Email and password are required"}), 400

    user = session.query(Users).filter_by(email=email).first()
    if user and user.check_password(password):
        logging.info('User with email %s logged in successfully', email)
        return jsonify({
            "message": "Login successful",
            "user_id": user.user_id,
            "user_uuid": user.user_uuid,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
        }), 200
    else:
        logging.warning('Invalid email or password for email %s', email)
        return jsonify({"error": "Invalid email or password"}), 401


# ----- Google Login Endpoint -----
@auth_bp.route('/google-login', methods=['POST'])
def google_login():
    print('google/login backend hit')
    data = request.get_json()
    token = data.get('tokenId')
    logging.debug('Received Google login request with tokenId')

    if not token:
        logging.warning('Missing token in Google login request')
        return jsonify({"error": "Token is required"}), 400
    
    try:
        # Verify the Google ID token
        id_info = id_token.verify_oauth2_token(token, google_requests.Request(), os.getenv("GOOGLE_CLIENT_ID"), clock_skew_in_seconds=20)
        email = id_info.get('email')
        first_name = id_info.get('given_name', '')
        last_name = id_info.get('family_name', '')
        google_id = id_info.get('sub')

        logging.debug('Google ID token verified. Extracted info: email=%s, first_name=%s, last_name=%s', email, first_name, last_name)

        # Check if user already exists in the database
        user = session.query(Users).filter_by(email=email).first()

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
            session.add(user)
            session.commit()
            logging.info('New Google user created with email %s', email)
            is_new_user = True  # Set flag to true for new users

        # Create a payload for JWT
        payload = {
            'user_uuid': user.user_uuid,
            'email': user.email,
            'exp': datetime.utcnow() + timedelta(hours=1)
        }

        # Encode the JWT token
        jwt_token = jwt.encode(payload, Config.SECRET_KEY, algorithm='HS256')

        # Return the JWT token to the client
        return jsonify({
            "message": "Login successful",
            "user_id": user.user_id,
            "user_uuid": user.user_uuid,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "isNewUser": is_new_user,
            "token": jwt_token
        }), 200

    except ValueError as e:
        logging.error('Invalid token received for Google login: %s', str(e))
        return jsonify({"error": "Invalid token"}), 400

    except Exception as e:
        logging.error('Failed to handle Google login: %s', str(e))
        return jsonify({"error": f"Failed to handle Google login: {str(e)}"}), 500
