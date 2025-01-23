# routes/chatbot_route.py
from flask import Blueprint, request, jsonify, g
from config import Config
from helpers.chatbot_helper import continue_conversation
from models.sql_models import Users, ServicePeriod
import traceback
from helpers.cors_helpers import cors_preflight

chatbot_bp = Blueprint("chatbot_bp", __name__)

@chatbot_bp.route("/chat", methods=["POST"])
def chat():
    """
    Handle a single user message and get a single assistant response, 
    with optional multi-turn memory via thread_id, and user identification via user_uuid.

    Expects JSON:
    {
        "message": "<User's question or statement>",
        "thread_id": "<optional existing thread ID>",
        "user_uuid": "<the user’s UUID (optional)>"
    }
    Returns JSON:
    {
        "assistant_message": "...",
        "thread_id": "..."
    }
    """
    try:
        # 2) Parse JSON request body
        data = request.get_json(force=True)
        if not data:
            return jsonify({"error": "Missing JSON body"}), 400

        user_message = data.get("message", "")
        thread_id = data.get("thread_id")
        user_uuid = data.get("user_uuid")  # Retrieve the user’s UUID

        if not user_message:
            return jsonify({"error": "No 'message' provided"}), 400

        print(f"User UUID received: {user_uuid}")

        # 3) Look up the user in the DB
        user = g.session.query(Users).filter_by(user_uuid=user_uuid).first()
        if not user:
            print(f"Invalid user UUID: {user_uuid}")
            return jsonify({"error": "Invalid user UUID"}), 404
        
        # 3a) Look up the user credits in the DB and block if not enough
        if user.credits_remaining <= 0:
            return jsonify({"error": "You do not have enough credits to continue this conversation. Please visit your account and purchase more credits."}), 403


        # Retrieve the user_id (and optionally first/last name, email, etc.)
        db_user_id = user.user_id
        first_name = user.first_name  # or user.last_name, user.email, etc.
        print(f"[DEBUG] Found user_id={db_user_id} for UUID={user_uuid} (First name: {first_name})")

        # 4) Retrieve the user's service periods
        service_periods = g.session.query(ServicePeriod).filter_by(user_id=db_user_id).all()
        if service_periods:
            formatted_service_periods = [
                f"{sp.branch_of_service} from {sp.service_start_date.strftime('%Y-%m-%d')} to {sp.service_end_date.strftime('%Y-%m-%d')}"
                for sp in service_periods
            ]
            service_periods_str = "; ".join(formatted_service_periods)
        else:
            service_periods_str = "No service periods found."

        print(f"[DEBUG] Service periods for user_id={db_user_id}: {service_periods_str}")

        # 5) Build the system_message
        system_message = (
            f"My first name is {first_name}, user_id is {db_user_id}, "
            f"and my service periods are: {service_periods_str}."
        )

        # 6) Call continue_conversation, passing system_msg
        result = continue_conversation(
            user_id=db_user_id,
            user_input=user_message,
            thread_id=thread_id,
            system_msg=system_message  # <--- pass here
        )

        # 7) Return the assistant response
        response_data = {
            "assistant_message": result["assistant_message"],
            "thread_id": result["thread_id"]
        }
        return jsonify(response_data), 200

    except Exception as e:
        print("[ERROR] An exception occurred in /chat route:")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
