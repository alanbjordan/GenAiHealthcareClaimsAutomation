# account_routes.py

from flask import Blueprint, request, jsonify, g
from models.sql_models import Users
from datetime import datetime
import logging

account_bp = Blueprint('account_bp', __name__)

@account_bp.route('/me', methods=['GET','PATCH','OPTIONS'])
def account_me():
    """
    GET /me?userUUID=...
       -> returns user info (first_name, last_name, email)
    PATCH /me?userUUID=...
       -> updates user first_name, last_name
    """

    if request.method == 'OPTIONS':
        # Return a preflight response or rely on a global after_request
        resp = jsonify({"message": "CORS preflight"})
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, PATCH, OPTIONS"
        return resp, 200

    user_uuid = request.args.get('userUUID')
    if not user_uuid:
        logging.warning("Missing userUUID query param")
        return jsonify({"error": "userUUID query param is required"}), 400

    user = g.session.query(Users).filter_by(user_uuid=user_uuid).first()
    if not user:
        return jsonify({"error": "User not found for provided userUUID"}), 404

    if request.method == 'GET':
        # Return user info
        return jsonify({
            "user_id": user.user_id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email
        }), 200

    elif request.method == 'PATCH':
        # Update user info
        data = request.get_json() or {}
        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')

        user.first_name = first_name
        user.last_name = last_name
        user.updated_at = datetime.utcnow()

        try:
            g.session.commit()
            return jsonify({
                "message": "User info updated",
                "first_name": user.first_name,
                "last_name": user.last_name
            }), 200
        except Exception as e:
            g.session.rollback()
            logging.error(f"Error updating user {user_uuid}: {str(e)}")
            return jsonify({"error": f"Failed to update user info: {str(e)}"}), 500

@account_bp.route('/me/password', methods=['PATCH','OPTIONS'])
def update_password():
    """
    PATCH /me/password?userUUID=...
      -> Expects JSON { "currentPassword": "...", "newPassword": "..." }
         to update the user's password. 
    """

    if request.method == 'OPTIONS':
        resp = jsonify({"message": "CORS preflight"})
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "PATCH, OPTIONS"
        return resp, 200

    user_uuid = request.args.get('userUUID')
    if not user_uuid:
        logging.warning("Missing userUUID query param")
        return jsonify({"error": "userUUID query param is required"}), 400

    user = g.session.query(Users).filter_by(user_uuid=user_uuid).first()
    if not user:
        return jsonify({"error": "User not found for provided userUUID"}), 404

    data = request.get_json() or {}
    current_password = data.get('currentPassword')
    new_password = data.get('newPassword')

    if not user.check_password(current_password):
        logging.warning(f"User {user.email} provided invalid current password")
        return jsonify({"error": "Current password is incorrect"}), 401

    # Update to new password (assuming set_password does hashing)
    user.set_password(new_password)
    user.updated_at = datetime.utcnow()

    try:
        g.session.commit()
        return jsonify({"message": "Password updated successfully"}), 200
    except Exception as e:
        logging.error(f"Error updating password for user {user.email}: {str(e)}")
        g.session.rollback()
        return jsonify({"error": f"Failed to update password: {str(e)}"}), 500
