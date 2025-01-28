# credit_routes.py

from flask import Blueprint, request, jsonify, g
from models.sql_models import Users

credits_bp = Blueprint('credits_bp', __name__)

@credits_bp.route("/credits", methods=["GET"])
def get_user_credits():
    """
    GET /credits?userUUID=<the user's UUID>
    
    Returns a JSON object with the user's remaining credits if found.
    Example response:
    {
        "credits_remaining": 10
    }
    """
    try:
        # 1) Retrieve userUUID from query params (e.g., ?userUUID=some-uuid)
        user_uuid = request.args.get("userUUID", None)
        if not user_uuid:
            return jsonify({"error": "Missing userUUID query parameter"}), 400

        # 2) Query the database for this user
        user = g.session.query(Users).filter_by(user_uuid=user_uuid).first()
        if not user:
            return jsonify({"error": f"No user found with userUUID={user_uuid}"}), 404

        # 3) Return the user's remaining credits
        return jsonify({"credits_remaining": user.credits_remaining}), 200
    
    except Exception as e:
        print("[ERROR] An exception occurred in /credits route:")
        # Log or print stack trace if needed
        return jsonify({"error": str(e)}), 500
