# routes/chatbot_route.py
from flask import Blueprint, request, jsonify
from config import Config  # or wherever you store your config
from helpers.chatbot_helper import continue_conversation

chatbot_bp = Blueprint("chatbot_bp", __name__)

@chatbot_bp.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    """
    Handle a single user message and get a single assistant response, 
    with optional multi-turn memory via thread_id.
    Expects JSON:
    {
        "message": "<User's question or statement>",
        "thread_id": "<optional existing thread ID>"
    }
    Returns JSON:
    {
        "assistant_message": "...",
        "thread_id": "..."
    }
    """

    # 1) Handle CORS Preflight
    if request.method == 'OPTIONS':
        response = jsonify({"message": "CORS preflight successful"})
        response.headers.update({
            "Access-Control-Allow-Origin": Config.CORS_ORIGINS,
            "Access-Control-Allow-Headers": "Content-Type, Authorization, user-uuid",
            "Access-Control-Allow-Methods": "GET, PUT, POST, DELETE, OPTIONS",
            "Access-Control-Allow-Credentials": "true"
        })
        return response, 200

    # 2) Parse JSON request body
    data = request.get_json(force=True)  # force=True just in case
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    user_message = data.get("message", "")
    thread_id = data.get("thread_id")

    if not user_message:
        return jsonify({"error": "No 'message' provided"}), 400

    # 3) Call our helper to continue or start a conversation
    result = continue_conversation(user_input=user_message, thread_id=thread_id)

    # 4) Return the assistant's response + the updated thread_id
    response_data = {
        "assistant_message": result["assistant_message"],
        "thread_id": result["thread_id"]
    }
    return jsonify(response_data), 200
