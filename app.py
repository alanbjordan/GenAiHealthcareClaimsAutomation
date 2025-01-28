# main.py (or wherever you have your Flask entry point)

from flask import g
from create_app import create_app
from database.session import ScopedSession
from datetime import datetime
import os

# --- Import all your Blueprints ---
from routes.auth_routes import auth_bp
from routes.documents_routes import document_bp
from routes.analysis_routes import analysis_bp
from routes.service_periods import service_periods_bp
from routes.categorize_routes import extract_structured_bp
from routes.condition_routes import condition_bp
from routes.summary_routes import summary_bp
from routes.bva_routes import bva_bp
from routes.decision_routes import decision_bp
from routes.marketing_routes import marketing_bp
from routes.chatbot_route import chatbot_bp
from routes.credit_routes import credits_bp

# Create the app instance
app = create_app()

# -------------------------------
# Global session handling
# -------------------------------
def log_with_timing(prev_time, message):
    current_time = datetime.utcnow()
    elapsed = (current_time - prev_time).total_seconds() if prev_time else 0
    print(f"[{current_time.isoformat()}] {message} (Elapsed: {elapsed:.4f}s)")
    return current_time

@app.before_request
def create_session():
    """ Runs before every request to create a new session. """
    t = log_with_timing(None, "[GLOBAL BEFORE_REQUEST] Creating session...")
    g.session = ScopedSession()
    t = log_with_timing(t, "[GLOBAL BEFORE_REQUEST] Session created and attached to g.")

@app.teardown_request
def remove_session(exception=None):
    """
    Runs after every request.
    - Rolls back if there's an exception,
    - Otherwise commits,
    - Then removes the session from the registry.
    """
    t = log_with_timing(None, "[GLOBAL TEARDOWN_REQUEST] Starting teardown...")
    session = getattr(g, 'session', None)
    if session:
        if exception:
            t = log_with_timing(t, "[GLOBAL TEARDOWN_REQUEST] Exception detected. Rolling back session.")
            session.rollback()
        else:
            t = log_with_timing(t, "[GLOBAL TEARDOWN_REQUEST] No exception. Committing session.")
            session.commit()
        ScopedSession.remove()
        t = log_with_timing(t, "[GLOBAL TEARDOWN_REQUEST] Session removed.")
    else:
        t = log_with_timing(t, "[GLOBAL TEARDOWN_REQUEST] No session found.")

# -------------------------------
# Register the Blueprints
# -------------------------------
app.register_blueprint(auth_bp)
app.register_blueprint(document_bp)
app.register_blueprint(analysis_bp)
app.register_blueprint(service_periods_bp)
app.register_blueprint(extract_structured_bp)
app.register_blueprint(condition_bp)
app.register_blueprint(summary_bp)
app.register_blueprint(bva_bp)
app.register_blueprint(decision_bp)
app.register_blueprint(marketing_bp)
app.register_blueprint(chatbot_bp)
app.register_blueprint(credits_bp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Flask on port {port}")
    app.run(host="0.0.0.0", port=port, debug=True)
