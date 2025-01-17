# helpers/upload/validation_helper.py
from flask import jsonify
import logging

def validate_and_setup_request(request):
    """
    Validate the incoming request and extract necessary information.
    
    :param request: Flask request object
    :return: tuple (user_uuid, uploaded_files) or (error_response, None)
    """
    logging.info("Validating request")
    
    if 'file' not in request.files:
        error_message = "No file part in the request"
        logging.error(error_message)
        return jsonify({"error": error_message}), None

    uploaded_files = request.files.getlist('file')
    user_uuid = request.form.get('userUUID')  # Get user UUID from request

    if not user_uuid:
        error_message = "User UUID is missing in the request"
        logging.error(error_message)
        return jsonify({"error": error_message}), None

    return (user_uuid, uploaded_files), None
