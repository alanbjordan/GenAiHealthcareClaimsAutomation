import os
import requests
import random
import string
from flask import Blueprint, request, jsonify
from models.sql_models import SupportMessage, Users, ServicePeriod
from database.session import ScopedSession
from datetime import datetime
# from sqlalchemy.exc import IntegrityError  # Only if you handle collisions

session = ScopedSession()
supportbp = Blueprint('supportbp', __name__)

# Slack webhook URL from environment variable
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

def generate_ticket_number(prefix="TKT", length=6):
    """
    Generate a ticket number like "TKT-123456".
    Collisions are very unlikely, but not impossible.
    """
    random_digits = ''.join(random.choices(string.digits, k=length))
    return f"{prefix}-{random_digits}"

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

    # If branch_of_service is in the "service_periods" table, get the first record
    service_period = session.query(ServicePeriod).filter_by(user_id=user.user_id).first()
    if service_period:
        branch_of_service = service_period.branch_of_service
    else:
        branch_of_service = "N/A"

    # Generate a random ticket number (Option A)
    ticket_num = generate_ticket_number(prefix="TKT", length=6)

    # Create the support message in DB
    new_support_message = SupportMessage(
        user_id=user.user_id,
        rating=rating,
        issue_type=issue_type,
        feedback=feedback,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        branch_of_service=branch_of_service,
        ticket_number=ticket_num
    )

    session.add(new_support_message)
    # If you want to handle collisions:
    # try:
    #     session.commit()
    # except IntegrityError:
    #     session.rollback()
    #     # re-generate or raise an error
    session.commit()

    # Optional: Post to Slack
    if SLACK_WEBHOOK_URL:
        slack_payload = {
            "text": (
                f"*New Support Ticket:* `{ticket_num}`\n"
                f"• Name: {user.first_name} {user.last_name}\n"
                f"• Email: {user.email}\n"
                f"• Branch of Service: {branch_of_service}\n"
                f"• Issue Type: {issue_type}\n"
                f"• Rating: {rating}\n"
                f"• Message:\n{feedback}"
            )
        }
        try:
            resp = requests.post("https://hooks.slack.com/services/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", json=slack_payload)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Slack post failed: {e}")
    else:
        print("SLACK_WEBHOOK_URL not set. Skipping Slack notification.")

    return jsonify({
        "success": True,
        "ticket_number": ticket_num  # Return the ticket number to the frontend if desired
    }), 200
