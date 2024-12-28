# routes/decision_routes.py

from flask import Blueprint, request, jsonify, g
from models.sql_models import UserDecisionSaves, Users
from database.session import ScopedSession
from config import Config
import jwt
from datetime import datetime
from helpers.llm_helpers import structured_summarize_bva_decision_llm

decision_bp = Blueprint('decision_bp', __name__)

def log_with_timing(prev_time, message):
    current_time = datetime.utcnow()
    if prev_time is None:
        elapsed = 0.0
    else:
        elapsed = (current_time - prev_time).total_seconds()
    print(f"[{current_time.isoformat()}] {message} (Elapsed: {elapsed:.4f}s)")
    return current_time

@decision_bp.before_request
def create_session():
    t = log_with_timing(None, "[BEFORE_REQUEST] Creating session...")
    g.session = ScopedSession()
    t = log_with_timing(t, "[BEFORE_REQUEST] Session created and attached to g.")

@decision_bp.teardown_request
def remove_session(exception=None):
    t = log_with_timing(None, "[TEARDOWN_REQUEST] Starting teardown...")
    session = g.pop('session', None)
    if session:
        if exception:
            t = log_with_timing(t, "[TEARDOWN_REQUEST] Exception detected. Rolling back session.")
            session.rollback()
        else:
            t = log_with_timing(t, "[TEARDOWN_REQUEST] No exception. Committing session.")
            session.commit()
        ScopedSession.remove()
        t = log_with_timing(t, "[TEARDOWN_REQUEST] Session removed.")
    else:
        t = log_with_timing(t, "[TEARDOWN_REQUEST] No session found.")

def get_user_from_token(request):
    t = log_with_timing(None, "[get_user_from_token] Extracting user from token...")
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        t = log_with_timing(t, "[get_user_from_token] No Authorization header found.")
        return None, "Authorization token is required"
    try:
        token = auth_header.split(" ")[1]
        payload = jwt.decode(token, Config.SECRET_KEY, algorithms=['HS256'])
        user_uuid = payload.get('user_uuid')
        t = log_with_timing(t, f"[get_user_from_token] Successfully decoded token for user_uuid: {user_uuid}")
        return user_uuid, None
    except Exception as e:
        t = log_with_timing(t, f"[get_user_from_token][ERROR] Error decoding token: {e}")
        return None, "Invalid or expired token"

@decision_bp.route('/user_decision_save', methods=['GET', 'POST', 'OPTIONS'])
def user_decision_save():
    t = log_with_timing(None, f"[user_decision_save] Route called with method {request.method}")

    if request.method == 'OPTIONS':
        t = log_with_timing(t, "[user_decision_save] Handling OPTIONS request.")
        response = jsonify({"message": "CORS preflight successful"})
        response.headers["Access-Control-Allow-Origin"] = Config.CORS_ORIGINS
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, user-uuid"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        t = log_with_timing(t, "[user_decision_save] Returning OPTIONS response.")
        return response, 200

    user_uuid, error = get_user_from_token(request)
    if error:
        t = log_with_timing(t, f"[user_decision_save][WARNING] Invalid user token: {error}")
        return jsonify({"error": error}), 403

    session = g.session
    t = log_with_timing(t, f"[user_decision_save] Fetching user from DB for user_uuid: {user_uuid}")
    user = session.query(Users).filter_by(user_uuid=user_uuid).first()

    if not user:
        t = log_with_timing(t, f"[user_decision_save][WARNING] User not found for user_uuid: {user_uuid}")
        return jsonify({"error": "Invalid user UUID"}), 404

    if request.method == 'GET':
        t = log_with_timing(t, "[user_decision_save][GET] Processing GET request...")
        decision_citation = request.args.get('decision_citation')
        if not decision_citation:
            t = log_with_timing(t, "[user_decision_save][GET][WARNING] Missing decision_citation parameter.")
            return jsonify({"error": "decision_citation is required"}), 400

        t = log_with_timing(t, f"[user_decision_save][GET] Querying UserDecisionSaves for user_id={user.user_id}, citation={decision_citation}")
        uds = session.query(UserDecisionSaves).filter_by(user_id=user.user_id, decision_citation=decision_citation).first()
        if uds:
            t = log_with_timing(t, f"[user_decision_save][GET] Found existing record (id={uds.id}). Returning record.")
            return jsonify({
                "id": uds.id,
                "decision_citation": uds.decision_citation,
                # Notes structure is flexible. Now expected { comments: [...] }
                "notes": uds.notes or {},
                "created_at": uds.created_at.isoformat(),
                "updated_at": uds.updated_at.isoformat()
            }), 200
        else:
            t = log_with_timing(t, "[user_decision_save][GET] No record found. Returning empty notes.")
            return jsonify({"notes": {}}), 200

    elif request.method == 'POST':
        t = log_with_timing(t, "[user_decision_save][POST] Processing POST request...")
        data = request.get_json()
        t = log_with_timing(t, f"[user_decision_save][POST] JSON data received: {data}")
        decision_citation = data.get('decision_citation')
        if not decision_citation:
            t = log_with_timing(t, "[user_decision_save][POST][WARNING] Missing decision_citation in request body.")
            return jsonify({"error": "decision_citation is required"}), 400

        # Notes expected as { comments: [...] } but we store as-is.
        notes = data.get('notes', {})
        t = log_with_timing(t, f"[user_decision_save][POST] Checking if record exists in DB for user_id={user.user_id}, decision_citation={decision_citation}")
        uds = session.query(UserDecisionSaves).filter_by(user_id=user.user_id, decision_citation=decision_citation).first()
        if uds:
            t = log_with_timing(t, f"[user_decision_save][POST] Record found (id={uds.id}). Updating notes.")
            uds.notes = notes
            uds.updated_at = datetime.utcnow()
        else:
            t = log_with_timing(t, "[user_decision_save][POST] No existing record. Creating new entry.")
            uds = UserDecisionSaves(
                user_id=user.user_id,
                decision_citation=decision_citation,
                notes=notes
            )
            session.add(uds)

        t = log_with_timing(t, "[user_decision_save][POST] Notes saved/updated successfully.")
        return jsonify({"message": "Notes saved successfully"}), 200

@decision_bp.route('/structured_summarize_bva_decision', methods=['POST', 'OPTIONS'])
def structured_summarize_bva_decision():
    t = log_with_timing(None, f"[structured_summarize_bva_decision] Route called with method {request.method}")

    if request.method == 'OPTIONS':
        t = log_with_timing(t, "[structured_summarize_bva_decision] Handling OPTIONS request.")
        response = jsonify({"message": "CORS preflight successful"})
        response.headers["Access-Control-Allow-Origin"] = Config.CORS_ORIGINS
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, user-uuid"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        t = log_with_timing(t, "[structured_summarize_bva_decision] Returning OPTIONS response.")
        return response, 200

    user_uuid, error = get_user_from_token(request)
    if error:
        t = log_with_timing(t, f"[structured_summarize_bva_decision][WARNING] Invalid token: {error}")
        return jsonify({"error": error}), 403

    session = g.session
    t = log_with_timing(t, f"[structured_summarize_bva_decision] Fetching user from DB for user_uuid: {user_uuid}")
    user = session.query(Users).filter_by(user_uuid=user_uuid).first()
    if not user:
        t = log_with_timing(t, f"[structured_summarize_bva_decision][WARNING] User not found for user_uuid: {user_uuid}")
        return jsonify({"error": "Invalid user UUID"}), 404

    data = request.get_json()
    t = log_with_timing(t, f"[structured_summarize_bva_decision] Received JSON data: {data}")
    decision_citation = data.get('decision_citation')
    full_text = data.get('fullText')

    if not decision_citation or not full_text:
        t = log_with_timing(t, "[structured_summarize_bva_decision][WARNING] Missing required fields: decision_citation or fullText.")
        return jsonify({"error": "decision_citation and fullText are required"}), 400

    try:
        t = log_with_timing(t, f"[structured_summarize_bva_decision] Calling structured_summarize_bva_decision_llm with decision_citation={decision_citation}")
        structured_data = structured_summarize_bva_decision_llm(decision_citation, full_text)
        t = log_with_timing(t, f"[structured_summarize_bva_decision] Received structured_data: {structured_data}")
    except Exception as e:
        t = log_with_timing(t, f"[structured_summarize_bva_decision][ERROR] Error extracting structured summary from decision: {e}")
        return jsonify({"error": "Could not generate structured summary."}), 500

    t = log_with_timing(t, "[structured_summarize_bva_decision] Returning structured_data.")
    return jsonify(structured_data), 200
