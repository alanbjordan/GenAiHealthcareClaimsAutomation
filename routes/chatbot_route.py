# routes/chatbot_route.py

from flask import Blueprint, request, jsonify, g
from config import Config
from helpers.chatbot_helper import continue_conversation
from models.sql_models import Users, ServicePeriod, ChatThread, ChatMessage
import traceback
from helpers.cors_helpers import cors_preflight
import uuid
from datetime import datetime
from openai import OpenAI
import os

# Initialize the OpenAI client & forced update.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

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
      "thread_id": "...",
      "credits_remaining": ...
    }
    """
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"error": "Missing JSON body"}), 400

        user_message = data.get("message", "").strip()
        thread_id = data.get("thread_id")
        user_uuid = data.get("user_uuid")

        if not user_message:
            return jsonify({"error": "No 'message' provided"}), 400

        print(f"User UUID received: {user_uuid}")

        # 1) Retrieve the user
        user = g.session.query(Users).filter_by(user_uuid=user_uuid).first()
        print(f" User id: {user.user_id}")
        if not user:
            print(f"Invalid user UUID: {user_uuid}")
            return jsonify({"error": "Invalid user UUID"}), 404
        
        user_id = user.user_id

        if user.credits_remaining <= 0:
            return jsonify({
                "error": f"You do not have enough credits. Balance = {user.credits_remaining}. Please buy more."
            }), 403

        # 2) Create or retrieve ChatThread
        if not thread_id:
            thread = client.beta.threads.create() 
            thread_id = thread.id
            print('Creating New thread_id:', thread_id)
            new_thread = ChatThread(
                thread_id=thread_id,
                user_id=user.user_id
            )
            g.session.add(new_thread)
            g.session.commit()
        else:
            # Validate that this thread belongs to the user
            existing_thread = g.session.query(ChatThread).filter_by(
                thread_id=thread_id, 
                user_id=user.user_id
            ).first()
            if not existing_thread:
                return jsonify({"error": "Thread not found or does not belong to user"}), 404

        # 3) Store the user's message in ChatMessage (is_bot=False)
        user_msg = ChatMessage(
            thread_id=thread_id,
            is_bot=False,
            text=user_message
        )
        g.session.add(user_msg)
        g.session.commit()

        # 4) Retrieve user’s service periods for context
        service_periods = g.session.query(ServicePeriod).filter_by(user_id=user.user_id).all()
        if service_periods:
            formatted_service_periods = [
                f"{sp.branch_of_service} from {sp.service_start_date.strftime('%Y-%m-%d')} to {sp.service_end_date.strftime('%Y-%m-%d')}"
                for sp in service_periods
            ]
            service_periods_str = "; ".join(formatted_service_periods)
        else:
            service_periods_str = "No service periods found."

        # 5) Build the system_message
        system_message = (
            f"My first name is {user.first_name}, user_id is {user.user_id}, "
            f"and my service periods are: {service_periods_str}."
        )

        # 6) Call continue_conversation to get the assistant’s reply
        result = continue_conversation(
            user_id=user.user_id,
            user_input=user_message,
            thread_id=thread_id,
            system_msg=system_message
        )
        assistant_text = result.get("assistant_message", "[No assistant response]")

        # 7) Store the assistant’s response in ChatMessage (is_bot=True)
        bot_msg = ChatMessage(
            thread_id=thread_id,
            is_bot=True,
            text=assistant_text
        )
        g.session.add(bot_msg)
        g.session.commit()

        # Refresh the user’s credits or other data if needed
        updated_user = g.session.query(Users).filter_by(user_id=user_id).first()
        if not updated_user:
            return jsonify({"error": "User record not found after chat."}), 404

        # 8) Return final response
        return jsonify({
            "assistant_message": assistant_text,
            "thread_id": thread_id,
            "credits_remaining": updated_user.credits_remaining
        }), 200

    except Exception as e:
        print("[ERROR] An exception occurred in /chat route:")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@chatbot_bp.route("/all_chats", methods=["GET"])
def all_chats():
    """
    GET /all_chats?user_uuid=<the user's UUID>

    Returns a JSON object with a list of the user's chat threads. 
    Example response:
    {
      "threads": [
          {
             "thread_id": "thread_pabcd1234", 
             "created_at": "2025-01-30 12:34:56", 
             "messages_count": 7,
             "first_message_preview": "Hello, how can I help you?"
          },
          ...
      ]
    }
    """
    try:
        user_uuid = request.args.get("user_uuid")
        if not user_uuid:
            return jsonify({"error": "user_uuid query param is required"}), 400

        # 1) Look up the user by UUID
        user = g.session.query(Users).filter_by(user_uuid=user_uuid).first()
        if not user:
            return jsonify({"error": "Invalid user UUID"}), 404

        # 2) Retrieve the user’s ChatThreads
        threads = g.session.query(ChatThread).filter_by(user_id=user.user_id).all()

        # 3) Build a JSON-friendly response
        result_list = []
        for t in threads:
            created_str = t.created_at.strftime("%Y-%m-%d %H:%M:%S") if t.created_at else None

            # Optional: Show how many messages are in the thread
            msg_count = len(t.messages)

            # Optional: Add a short preview of the first or last message
            first_msg = None
            if t.messages:
                # Sort messages by created_at ascending (or rely on your DB order)
                sorted_msgs = sorted(t.messages, key=lambda m: m.created_at)
                first_msg_obj = sorted_msgs[0]
                first_msg = (first_msg_obj.text[:50] + "...") if len(first_msg_obj.text) > 50 else first_msg_obj.text

            result_list.append({
                "thread_id": t.thread_id,
                "created_at": created_str,
                "messages_count": msg_count,
                "first_message_preview": first_msg
            })

        # 4) Return JSON
        return jsonify({"threads": result_list}), 200

    except Exception as e:
        print("[ERROR] Exception in /all_chats route:")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@chatbot_bp.route("/chat_history", methods=["GET"])
def chat_history():
    """
    GET /chat_history?thread_id=<the-openai-thread-id>&user_uuid=<user’s-uuid>
    Returns the entire message history for that thread in chronological order.
    """
    try:
        thread_id = request.args.get("thread_id")
        user_uuid = request.args.get("user_uuid")

        if not thread_id or not user_uuid:
            return jsonify({"error": "Missing thread_id or user_uuid"}), 400

        # 1) Look up the user by UUID
        user = g.session.query(Users).filter_by(user_uuid=user_uuid).first()
        if not user:
            return jsonify({"error": "Invalid user UUID"}), 404

        # 2) Find the ChatThread by thread_id and user_id
        thread = g.session.query(ChatThread).filter_by(
            thread_id=thread_id,
            user_id=user.user_id
        ).first()
        if not thread:
            return jsonify({"error": "Thread not found or does not belong to user"}), 404

        # 3) Get messages for this thread, sorted by created_at
        messages = (
            g.session.query(ChatMessage)
            .filter_by(thread_id=thread_id)
            .order_by(ChatMessage.created_at.asc())  # oldest to newest
            .all()
        )

        # 4) Transform the DB rows into a JSON-friendly structure
        messages_data = []
        for m in messages:
            messages_data.append({
                "id": m.id,
                "text": m.text,
                "isBot": m.is_bot,
                "timestamp": m.created_at.strftime("%H:%M:%S")  # or full date/time
            })

        return jsonify({"messages": messages_data}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
