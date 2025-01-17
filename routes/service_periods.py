# routes/service_periods.py

from flask import Blueprint, request, jsonify, g
import logging
import os
import tempfile
from werkzeug.utils import secure_filename
from datetime import datetime
import json
from models.sql_models import Users, ServicePeriod, File  # Import specific models as needed
from helpers.azure_helpers import upload_to_azure_blob
from helpers.llm_helpers import process_document_based_on_type
from helpers.text_ext_helpers import read_and_extract_document, validate_dd214
from sqlalchemy.orm.attributes import flag_modified
from enum import Enum
import time
from config import Config

# Create a blueprint for service periods routes
service_periods_bp = Blueprint('service_periods_bp', __name__)

# Setting up logger for error tracking and debugging
logger = logging.getLogger(__name__)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'pdf'} 

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ====================================================
# = GET SERVICE PERIODS FOR USER ENDPOINT
# ====================================================
# Description: Retrieves all service periods for a user
# based on their user UUID.
# ====================================================
@service_periods_bp.route('/service-periods/<string:user_uuid>', methods=['GET'])
def get_service_dates(user_uuid):
    """
    Endpoint to retrieve service periods for a specific user.
    :param user_uuid: The UUID of the user for whom service periods are being retrieved.
    
    Responses:
    - Returns 404 if the user is not found.
    - Returns 200 with the user's service periods if successful.
    """
    try:
        # Retrieve user by UUID
        user = g.session.query(Users).filter_by(user_uuid=user_uuid).first()
        if not user:
            logger.warning(f'User not found for UUID: {user_uuid}')
            return jsonify({'error': 'User not found'}), 404

        # Retrieve service periods for the user
        service_periods = g.session.query(ServicePeriod).filter_by(user_id=user.user_id).all()
        response_data = [
            {
                'branchOfService': period.branch_of_service,
                'startDate': period.service_start_date.strftime('%Y-%m-%d'),
                'endDate': period.service_end_date.strftime('%Y-%m-%d')
            }
            for period in service_periods
        ]

        return jsonify({'service_periods': response_data}), 200

    except Exception as e:
        logger.error(f'Failed to retrieve service periods: {str(e)}')
        return jsonify({'error': 'An unexpected error occurred. Please try again later.'}), 500

@service_periods_bp.route('/service-periods', methods=['POST'])
def save_service_dates():
    """
    Endpoint to save service periods for a user.
    Receives a JSON payload with a user UUID and a list of service periods.
    Each service period contains a start date, end date, and branch of service.
    """

    try:
        # Extract data from the request body
        data = request.get_json()
        user_uuid = data.get('user_uuid')
        service_periods = data.get('service_periods')

        # Logging incoming data
        logger.debug(f"Received request data: {data}")

        # Validate request data to ensure required fields are present
        if not user_uuid or not service_periods:
            logger.warning('Missing user_uuid or service_periods in the request.')
            return jsonify({'error': 'user_uuid and service_periods are required'}), 400

        # Retrieve user by UUID
        user = g.session.query(Users).filter_by(user_uuid=user_uuid).first()
        if not user:
            logger.warning('User not found with provided user_uuid.')
            return jsonify({'error': 'User not found'}), 404

        # Remove all previous service period records for this user to avoid duplicates
        g.session.query(ServicePeriod).filter_by(user_id=user.user_id).delete()

        # Prepare new service period records for bulk saving
        new_service_periods = []
        for period in service_periods:
            # Parse and validate service start and end dates
            try:
                start_date = datetime.strptime(period['startDate'], '%Y-%m-%d')
                end_date = datetime.strptime(period['endDate'], '%Y-%m-%d')
            except ValueError as ve:
                return jsonify({'error': f'Invalid date format for service period: {str(ve)}'}), 400

            branch_of_service = period.get('branchOfService', '')

            # Ensure that the start date is before the end date
            if start_date >= end_date:
                return jsonify({'error': f'Start date {start_date} must be before end date {end_date}'}), 400

            # Create a new ServicePeriod object for each period
            service_period = ServicePeriod(
                user_id=user.user_id,
                service_start_date=start_date,
                service_end_date=end_date,
                branch_of_service=branch_of_service
            )
            new_service_periods.append(service_period)

        # Save all new service periods in the database in a single transaction for efficiency
        g.session.bulk_save_objects(new_service_periods)
        g.session.commit()

        # Return success response
        return jsonify({'message': 'Service periods saved successfully'}), 200

    except ValueError as ve:
        # Handle invalid date formats in the request data
        return jsonify({'error': f'Invalid date format: {str(ve)}'}), 400

    except Exception as e:
        # Handle unexpected errors, log them, and rollback the session to maintain data integrity
        g.session.rollback()
        logger.error(f'Failed to save service periods: {str(e)}')
        return jsonify({'error': 'An unexpected error occurred. Please try again later.'}), 500

@service_periods_bp.route('/upload-dd214', methods=['POST'])
def upload_dd214():
    """
    Endpoint to upload DD214 documents, validate them, upload to Azure,
    extract service periods, and store relevant information in the database.
    Handles single-page, multi-page, and multiple file uploads.
    """
    logging.info("DD214 upload route was hit")
    print("DD214 upload route was hit")

    try:
        process_start_time = time.time()

        # Retrieve user UUID from the form
        user_uuid = request.form.get('user_uuid')

        if not user_uuid:
            logging.error("User UUID is missing in the request")
            print("User UUID is missing in the request")
            return jsonify({"error": "User UUID is required"}), 400

        logging.info(f"Received upload request from user_uuid: {user_uuid}")
        print(f"Received upload request from user_uuid: {user_uuid}")

        # Query the user to get the user_id using user_uuid
        user = g.session.query(Users).filter_by(user_uuid=user_uuid).first()
        if not user:
            logging.error(f"Invalid user UUID: {user_uuid}")
            print(f"Invalid user UUID: {user_uuid}")
            return jsonify({"error": "Invalid user UUID"}), 404

        logging.info(f"User found: user_id={user.user_id}, user_uuid={user_uuid}")
        print(f"User found: user_id={user.user_id}, user_uuid={user_uuid}")

        # Retrieve uploaded files
        if 'files' not in request.files:
            logging.error("No files part in the request")
            print("No files part in the request")
            return jsonify({"error": "No files part in the request"}), 400

        uploaded_files = request.files.getlist('files')
        if not uploaded_files:
            logging.error("No files selected for uploading")
            print("No files selected for uploading")
            return jsonify({"error": "No files selected for uploading"}), 400

        uploaded_urls = []
        all_extracted_service_periods = []  # Collect all extracted service periods

        for uploaded_file in uploaded_files:
            if uploaded_file.filename == '':
                logging.error("One of the uploaded files has no filename")
                print("One of the uploaded files has no filename")
                uploaded_urls.append({
                    'fileName': '',
                    'blobUrl': None,
                    'error': "No selected file"
                })
                continue

            # Validate file type
            if not allowed_file(uploaded_file.filename):
                logging.error(f"Invalid file type for file {uploaded_file.filename}")
                print(f"Invalid file type for file {uploaded_file.filename}")
                uploaded_urls.append({
                    'fileName': uploaded_file.filename,
                    'blobUrl': None,
                    'error': "Invalid file type. Only PDF files are supported."
                })
                continue

            # Save the file temporarily on the server
            temp_file_path = os.path.join(tempfile.gettempdir(), secure_filename(uploaded_file.filename))
            uploaded_file.save(temp_file_path)
            logging.info(f"Saved uploaded file to temporary path: {temp_file_path}")
            print(f"Saved uploaded file to temporary path: {temp_file_path}")

            # Validate DD214 using AI
            validation_result = validate_dd214(temp_file_path)

            if "error" in validation_result:
                logging.error(f"Validation failed for file {uploaded_file.filename}: {validation_result['error']}")
                print(f"Validation failed for file {uploaded_file.filename}: {validation_result['error']}")
                uploaded_urls.append({
                    'fileName': uploaded_file.filename,
                    'blobUrl': None,
                    'error': validation_result['error']
                })
                # Optionally, remove the temp file if validation fails
                try:
                    os.remove(temp_file_path)
                    logging.info(f"Removed temporary file: {temp_file_path}")
                except OSError as e:
                    logging.warning(f"Failed to remove temporary file {temp_file_path}: {e}")
                continue

            # If validation is successful, proceed to upload to Azure
            message = validation_result.get('message', '')
            classifications = validation_result.get('classification') or validation_result.get('classifications')

            # Determine category for blob storage (since it's DD214, we set it accordingly)
            category = 'DD214'

            # Create the blob name using user UUID and determined category
            blob_name = f"{user_uuid}/{category}/{secure_filename(uploaded_file.filename)}"
            logging.info(f"Constructed blob name: {blob_name}")
            print(f"Constructed blob name: {blob_name}")

            # Upload the file to Azure Blob Storage
            blob_url = upload_to_azure_blob(blob_name, file_path=temp_file_path)
            if not blob_url:
                logging.error(f"Failed to upload file '{uploaded_file.filename}' to Azure.")
                print(f"Failed to upload file '{uploaded_file.filename}' to Azure.")
                uploaded_urls.append({
                    'fileName': uploaded_file.filename,
                    'blobUrl': None,
                    'error': "Failed to upload to Azure"
                })
                # Remove temp file
                try:
                    os.remove(temp_file_path)
                    logging.info(f"Removed temporary file: {temp_file_path}")
                except OSError as e:
                    logging.warning(f"Failed to remove temporary file {temp_file_path}: {e}")
                continue

            # Push metadata into the database
            new_file = File(
                user_id=user.user_id,
                file_name=uploaded_file.filename,
                file_type='pdf',
                file_url=blob_url,
                file_date=datetime.now().date(),
                uploaded_at=datetime.utcnow(),
                file_size=os.path.getsize(temp_file_path),
                file_category=category,
            )

            g.session.add(new_file)
            g.session.flush()  # To get file_id
            file_id = new_file.file_id
            logging.info(f"Inserted new file record with file_id={file_id}")
            print(f"Inserted new file record with file_id={file_id}")

            # Extract and store information
            try:
                # Extract text from the document
                extracted_text = read_and_extract_document(temp_file_path, 'pdf')
                print(f'Extracted Text: {type(extracted_text)} : {extracted_text}')
                extracted_dd214 = json.loads(extracted_text)
                if extracted_dd214:
                    # Assuming extracted_dd214 is a list of dictionaries
                    # Iterate through each entry
                    for entry in extracted_dd214:
                        details = entry.get('details', {})
                        service_periods_extracted = details.get('service_periods', [])

                        if service_periods_extracted:
                            # Save service periods to the database
                            for period in service_periods_extracted:
                                # Parse and validate service start and end dates
                                try:
                                    start_date = datetime.strptime(period['startDate'], '%Y-%m-%d').date()
                                    end_date = datetime.strptime(period['endDate'], '%Y-%m-%d').date()
                                except ValueError as ve:
                                    logging.error(f"Invalid date format in extracted service period: {ve}")
                                    print(f"Invalid date format in extracted service period: {ve}")
                                    # Optionally skip or handle differently
                                    continue

                                branch_of_service = period.get('branchOfService', '')

                                # Ensure that the start date is before the end date
                                if start_date >= end_date:
                                    logging.error(f"Start date {start_date} must be before end date {end_date} in extracted service period.")
                                    print(f"Start date {start_date} must be before end date {end_date} in extracted service period.")
                                    continue

                                # Check if the service period already exists
                                existing_period = g.session.query(ServicePeriod).filter_by(
                                    user_id=user.user_id,
                                    service_start_date=start_date,
                                    service_end_date=end_date,
                                    branch_of_service=branch_of_service
                                ).first()

                                if existing_period:
                                    logging.info(f"Service period already exists: {existing_period}")
                                    print(f"Service period already exists: {existing_period}")
                                    continue

                                # Create a new ServicePeriod object
                                new_service_period = ServicePeriod(
                                    user_id=user.user_id,
                                    service_start_date=start_date,
                                    service_end_date=end_date,
                                    branch_of_service=branch_of_service
                                )
                                g.session.add(new_service_period)

                                # Collect the service period to include in the response
                                all_extracted_service_periods.append({
                                    'startDate': period['startDate'],
                                    'endDate': period['endDate'],
                                    'branchOfService': branch_of_service
                                })

                            g.session.commit()
                            logging.info(f"Saved extracted service periods for file_id={file_id}")
                            print(f"Saved extracted service periods for file_id={file_id}")
                        else:
                            logging.warning(f"No service periods extracted from file '{uploaded_file.filename}'.")
                            print(f"No service periods extracted from file '{uploaded_file.filename}'.")
                else:
                    logging.warning(f"No information extracted from file '{uploaded_file.filename}'.")
                    print(f"No information extracted from file '{uploaded_file.filename}'.")

            except Exception as e:
                logging.error(f"Failed to extract and save information from file '{uploaded_file.filename}': {e}")
                print(f"Failed to extract and save information from file '{uploaded_file.filename}': {e}")
                # Handle or continue based on your requirements

            # Append successful upload info
            uploaded_urls.append({
                'fileName': uploaded_file.filename,
                'blobUrl': blob_url,
                'message': message
            })

            # Clean up the temporary file
            try:
                os.remove(temp_file_path)
                logging.info(f"Temporary file {temp_file_path} removed successfully.")
                print(f"Temporary file {temp_file_path} removed successfully.")
            except OSError as e:
                logging.warning(f"Failed to remove temporary file {temp_file_path}: {e}")
                print(f"Failed to remove temporary file {temp_file_path}: {e}")

        process_end_time = time.time()
        elapsed_time = process_end_time - process_start_time
        logging.info(f"Total processing time: {elapsed_time:.2f} seconds.")
        print(f"Total processing time: {elapsed_time:.2f} seconds.")

        # Log processing time to a file
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        LOG_FILE_PATH = os.path.join(BASE_DIR, "logs", "processing_times_log.txt")
        os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)
        with open(LOG_FILE_PATH, "a") as log_file:
            log_file.write(f"Processing time for DD214 upload: {elapsed_time:.2f} seconds\n")

        return jsonify({
            "message": "File(s) processed",
            "files": uploaded_urls,
            "service_periods": all_extracted_service_periods  # Include extracted service periods
        }), 201

    except Exception as e:
        g.session.rollback()
        logging.exception(f"DD214 Upload failed: {e}")
        print(f"DD214 Upload failed: {e}")
        return jsonify({"error": "Failed to upload file(s)"}), 500
