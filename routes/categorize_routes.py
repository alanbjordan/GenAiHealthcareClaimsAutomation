from models.llm_models import *
from datetime import date
from helpers.llm_helpers import *
from flask import Blueprint, request, jsonify, Response
from models.sql_models import File  # Import the File model
import time
import logging
from helpers.llm_helpers import *
from helpers.azure_helpers import *
from database.session import ScopedSession

session=ScopedSession()

# Create a Blueprint for analysis routes
extract_structured_bp = Blueprint('extract_structured_bp', __name__)

# Route for structured document extraction
@extract_structured_bp.route('/extract_structured_data', methods=['POST'])
def extract_structured_data():
    """Extract structured data from a document by its ID."""
    try:
        # Extract the document ID from the request
        data = request.get_json()
        document_id = data.get('document_id')

        if not document_id:
            return jsonify({"error": "Document ID is required."}), 400

        # Retrieve the file record from the database
        file_record = session.query(File).filter_by(file_id=document_id).first()
        if not file_record:
            return jsonify({"error": "Document not found."}), 404

        # Download the file from Azure Blob Storage
        file_content = download_file_from_azure(file_record.file_url)
        if file_content is None:
            return jsonify({"error": "Failed to download document."}), 500

        # Process the document to extract text content
        text_content = process_document(file_content, file_record.file_type)

        # Parse the extracted text to get structured data
        structured_data = parse_chat_completion(text_content)

        # If structured_data is a Pydantic model, convert it to a dict
        if isinstance(structured_data, PageClassification):
            structured_data = structured_data.dict()

        # Return the structured data
        return jsonify({
            "document_id": document_id,
            "structured_data": structured_data
        }), 200

    except Exception as e:
        logging.error(f"Error extracting structured data from document ID {document_id}: {str(e)}")
        return jsonify({"error": f"Failed to extract structured data: {str(e)}"}), 500
        return jsonify({"error": f"Failed to extract structured data: {str(e)}"}), 500