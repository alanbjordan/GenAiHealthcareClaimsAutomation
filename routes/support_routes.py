from flask import Blueprint, request, jsonify, g
from models.sql_models import SupportMessage, Users, ServicePeriod
from database.session import ScopedSession
from datetime import datetime

session = ScopedSession()
supportbp = Blueprint('supportbp', __name__)

@supportbp.route('/support_modal', methods=['POST'])
def handle_support_modal():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON data"}), 400

    user_uuid = data.get("user_uuid")
    rating = data.get("rating")
    feedback = data.get("feedback")
    issue_type = data.get("issue_type", "general")

    # Look up the user by user_uuid
    user = session.query(Users).filter_by(user_uuid=user_uuid).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # If branch_of_service is in the "service_periods" table, get the first one
    service_period = session.query(ServicePeriod).filter_by(user_id=user.user_id).first()
    if service_period:
        branch_of_service = service_period.branch_of_service
    else:
        # If user has no service periods, you can store 'None', 'N/A', or handle differently
        branch_of_service = "N/A"

    new_support_message = SupportMessage(
        user_id=user.user_id,
        rating=rating,
        issue_type=issue_type,
        feedback=feedback,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        branch_of_service=branch_of_service
    )

    session.add(new_support_message)
    session.commit()

    return jsonify({"success": True}), 200
