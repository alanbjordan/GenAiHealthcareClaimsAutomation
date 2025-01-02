# routes/analysis_routes.py

from flask import Blueprint, request, jsonify, Response, g
from models.sql_models import File  # Import the File model
import time
import logging
from helpers.llm_helpers import *
from helpers.azure_helpers import *

# Create a Blueprint for analysis routes
analysis_bp = Blueprint('analysis_bp', __name__)

# Route to track progress of the extraction process
@analysis_bp.route('/analyze_document', methods=['POST'])
def analyze_document():
    try:
        # Extract the document ID from the request
        data = request.get_json()
        document_id = data.get('document_id')

        if not document_id:
            return jsonify({"error": "Document ID is required."}), 400

        # Retrieve the file record from the database
        file_record = File.query.filter_by(file_id=document_id).first()
        if not file_record:
            return jsonify({"error": "Document not found."}), 404

        # Download the file from Azure Blob Storage
        file_content = download_file_from_azure(file_record.file_url)
        if file_content is None:
            return jsonify({"error": "Failed to download document."}), 500

        # Process the document to extract text content
        text_content = process_document(file_content, file_record.file_type)

        # Generate a summary of the document
        summary = generate_summary(text_content)

        # Determine the document type (e.g., In-Service or Post-Service)
        document_type = file_record.file_category

        # Return the summary and document type
        return jsonify({
            "document_id": document_id,
            "document_type": document_type,
            "summary": summary
        }), 200

    except Exception as e:
        logging.error(f"Error analyzing document ID {document_id}: {str(e)}")
        return jsonify({"error": f"Failed to analyze document: {str(e)}"}), 500


# Global dictionaries to store OCR results and diagnoses
in_service_page_texts = {}
post_service_page_texts = {}
in_service_diagnosis = {}
post_service_diagnosis = {}

# Global variable to store progress messages
progress_messages = []

# Route to extract and classify medical records
@analysis_bp.route('/extract_service_records', methods=['POST'])
def extract_service_records():
    global progress_messages
    progress_messages.clear()  # Clear previous progress messages

    # Extract the uploaded files from the request
    in_service_files = request.files.getlist('in_service_file')
    post_service_files = request.files.getlist('post_service_file')

    prompt_text = "Please classify medical diagnoses from the following text"

    # Append progress messages
    progress_messages.append(f"Files Uploaded: In-service files count: {len(in_service_files)}, Post-service files count: {len(post_service_files)}")

    # Process in-service files
    progress_messages.append("Processing in-service files...")
    in_service_page_texts = {}
    process_files(in_service_files, in_service_page_texts, "in-service")
    progress_messages.append("In-service files processing complete.")

    # Classify in-service diagnoses
    progress_messages.append("Classifying diagnoses for in-service texts...")
    in_service_classified = classify_and_store_diagnosis(in_service_page_texts, prompt_text)
    progress_messages.append("In-service diagnosis classification complete.")

    # Process post-service files
    progress_messages.append("Processing post-service files...")
    post_service_page_texts = {}
    process_files(post_service_files, post_service_page_texts, "post-service")
    progress_messages.append("Post-service files processing complete.")

    # Classify post-service diagnoses
    progress_messages.append("Classifying diagnoses for post-service texts...")
    post_service_classified = classify_and_store_diagnosis(post_service_page_texts, prompt_text)
    progress_messages.append("Post-service diagnosis classification complete.")

    # Generate the report
    response = generate_report(in_service_classified, post_service_classified)

    return response