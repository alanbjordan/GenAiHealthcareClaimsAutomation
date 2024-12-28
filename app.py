# IMPORTS
from create_app import create_app
from routes.auth_routes import auth_bp  # Import the Blueprint
from routes.documents_routes import document_bp  # Import the document blueprint
from routes.analysis_routes import analysis_bp  # Import the analysis blueprint
from routes.service_periods import service_periods_bp
from routes.categorize_routes import extract_structured_bp
from routes.condition_routes import condition_bp
from routes.summary_routes import summary_bp  # Import the new blueprint
from routes.bva_routes import bva_bp
from routes.decision_routes import decision_bp
from routes.marketing_routes import marketing_bp
from routes.chatbot_route import chatbot_bp
import os


# Create the app instance
app = create_app()

# Register the blueprints without any prefix
app.register_blueprint(auth_bp)       # Routes like '/login', etc.
app.register_blueprint(document_bp)   # Routes like '/documents', etc.
app.register_blueprint(analysis_bp)   # Routes like '/analysis', etc.
app.register_blueprint(service_periods_bp)
app.register_blueprint(extract_structured_bp)  # Adjust the URL prefix as needed
app.register_blueprint(condition_bp)
app.register_blueprint(summary_bp)
app.register_blueprint(bva_bp) 
app.register_blueprint(decision_bp)
app.register_blueprint(marketing_bp)
app.register_blueprint(chatbot_bp)

#if __name__ == "__main__":
    #app.run(host="0.0.0.0", port=5000, debug=True)
if __name__ == "__main__":
    # Use the PORT environment variable or default to 5000
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Flask on port {port}")
    app.run(host="0.0.0.0", port=port, debug=True)
