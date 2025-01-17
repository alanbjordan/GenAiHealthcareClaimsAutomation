# routes/document_routes.py

from flask import Blueprint, request, jsonify, g
from models.sql_models import *  # Import File and Users models
import os
import tempfile
import json
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import time
from azure.storage.blob import BlobSasPermissions
from azure.storage.blob import generate_blob_sas
import logging
from azure.storage.blob import BlobServiceClient
from helpers.azure_helpers import *
from config import Config
from helpers.llm_helpers import *
from helpers.text_ext_helpers import *
from helpers.embedding_helpers import *
from sqlalchemy.orm.attributes import flag_modified
from concurrent.futures import ThreadPoolExecutor, as_completed
from helpers.visit_processor import process_visit
from helpers.diagnosis_worker import worker_process_diagnosis
from helpers.diagnosis_processor import process_diagnosis
from helpers.diagnosis_list import process_diagnosis_list
from helpers.sql_helpers import *
from helpers.cors_helpers import cors_preflight
from helpers.upload.validation_helper import validate_and_setup_request
from helpers.upload.usr_svcp_helpers import get_user_and_service_periods

# Create a blueprint for document routes
document_bp = Blueprint('document_bp', __name__)

# ========== DOCUMENT CRUD ROUTES ==========

@document_bp.route('/upload', methods=['POST'])
def upload():
    logging.info("Upload route was hit")
    print("Upload route was hit")  # Keeping print statements as requested
    
    try:
        process_start_time = time.time()

        # Validate the request and extract data
        validation_result, error_response = validate_and_setup_request(request)
        if error_response:
            return validation_result  # Early exit if validation fails

        user_uuid, uploaded_files = validation_result

        # Step 2: Retrieve user and service periods
        user_lookup_result, error_response = get_user_and_service_periods(user_uuid)
        if error_response:
            return user_lookup_result  # Early exit if user lookup fails
        user, service_periods = user_lookup_result

        uploaded_urls = []

        for uploaded_file in uploaded_files:
            if uploaded_file.filename == '':
                logging.error("No selected file in the upload")
                print("No selected file in the upload")
                return jsonify({"error": "No selected file"}), 400

            # Determine file type based on extension
            file_extension = os.path.splitext(uploaded_file.filename)[1].lower()
            file_type_mapping = {
                '.pdf': 'pdf',
                '.jpg': 'image',
                '.jpeg': 'image',
                '.png': 'image',
                '.mp4': 'video',
                '.mov': 'video',
                '.mp3': 'audio'
            }
            file_type = file_type_mapping.get(file_extension, 'unknown')
            logging.info(f"Determined file type '{file_type}' for extension '{file_extension}'")
            print(f"Determined file type '{file_type}' for extension '{file_extension}'")

            # Save to a temp file
            temp_file_path = os.path.join(tempfile.gettempdir(), secure_filename(uploaded_file.filename))
            uploaded_file.save(temp_file_path)
            logging.info(f"Saved uploaded file to temporary path: {temp_file_path}")
            print(f"Saved uploaded file to temporary path: {temp_file_path}")

            # Extract details from the file
            details = read_and_extract_document(temp_file_path, file_type)
            if not details:
                logging.error(f"Failed to extract details from file: {uploaded_file.filename}")
                print(f"Failed to extract details from file: {uploaded_file.filename}")
                uploaded_urls.append({
                    'category': 'Unclassified',
                    "fileName": uploaded_file.filename,
                    "blobUrl": None,
                    "error": "Failed to extract document details"
                })
                continue

            # Attempt to parse extracted data as JSON
            try:
                details = json.loads(details)
            except json.JSONDecodeError as e:
                logging.error(f"JSON decoding failed for file {uploaded_file.filename}: {str(e)}")
                print(f"JSON decoding failed for file {uploaded_file.filename}: {str(e)}")
                uploaded_urls.append({
                    'category': 'Unclassified',
                    "fileName": uploaded_file.filename,
                    "blobUrl": None,
                    "error": "Failed to parse document details"
                })
                continue

            # Determine category (your logic may differ)
            category = 'Unclassified'
            blob_name = f"{user_uuid}/{category}/{uploaded_file.filename}"
            
            # Upload file to Azure
            blob_url = upload_file_to_azure(temp_file_path, blob_name)
            logging.info(f"Uploaded file to Azure Blob Storage: {blob_url}")
            print(f"Uploaded file to Azure Blob Storage: {blob_url}")

            if blob_url:
                # Create a File record
                new_file = File(
                    user_id=user.user_id,
                    file_name=uploaded_file.filename,
                    file_type=file_type,
                    file_url=blob_url,
                    file_date=datetime.now().date(),
                    uploaded_at=datetime.utcnow(),
                    file_size=os.path.getsize(temp_file_path),
                    file_category=category,
                )
                g.session.add(new_file)
                g.session.flush()  # get new_file.file_id
                file_id = new_file.file_id
                g.session.commit()
                
                logging.info(f"Inserted new file record with file_id={file_id}")
                print(f"Inserted new file record with file_id={file_id}")

                # Process pages & visits concurrently
                try:
                    max_workers = 10
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        futures = []
                        for page in details:
                            page_number = page.get('page')
                            logging.info(f"Processing page {page_number}")
                            print(f"Processing page {page_number}")

                            if page.get('category') == 'Clinical Records':
                                visits = page.get('details', {}).get('visits', [])
                                logging.info(f"Found {len(visits)} visits on page {page_number}")
                                print(f"Found {len(visits)} visits on page {page_number}")

                                for visit in visits:
                                    future = executor.submit(
                                        process_visit,
                                        visit=visit,
                                        page_number=page_number,
                                        service_periods=service_periods,
                                        user_id=user.user_id,  # Pass user's ID
                                        file_id=file_id
                                    )
                                    futures.append(future)

                        for future in as_completed(futures):
                            try:
                                visit_results = future.result()
                            except Exception as e:
                                logging.exception(f"Error processing visit: {str(e)}")
                                print(f"Error processing visit: {str(e)}")

                except Exception as e:
                    logging.exception(f"Inserting Conditions Failed: {str(e)}")
                    print(f"Inserting Conditions Failed: {str(e)}")
                    raise

                uploaded_urls.append({
                    'category': category,
                    "fileName": uploaded_file.filename,
                    "blobUrl": blob_url
                })
                logging.info(f"File '{uploaded_file.filename}' processed and uploaded successfully.")
                
                # Clean up temp file
                try:
                    os.remove(temp_file_path)
                    logging.info(f"Temporary file {temp_file_path} removed successfully.")
                except OSError as e:
                    logging.warning(f"Failed to remove temporary file {temp_file_path}: {e}")
                    print(f"Failed to remove temporary file {temp_file_path}: {e}")
            else:
                logging.error(f"Failed to upload file '{uploaded_file.filename}' to Azure.")
                print(f"Failed to upload file '{uploaded_file.filename}' to Azure.")
                uploaded_urls.append({
                    'category': category,
                    "fileName": uploaded_file.filename,
                    "blobUrl": None,
                    "error": "Failed to upload to Azure"
                })

        # Commit everything so newly inserted Conditions are in the DB
        g.session.commit()
        logging.info("All files have been processed and committed to the database.")
        print("All files have been processed and committed to the database.")

        # Now discover any newly qualified nexus tags for this user
        discover_nexus_tags(g.session, user.user_id)

        # Optional: Revoke nexus tags that no longer qualify for this user
        revoke_nexus_tags_if_invalid(g.session, user.user_id)
        
        # Final commit after nexus updates
        g.session.commit()

        process_end_time = time.time()
        elapsed_time = process_end_time - process_start_time
        logger.info(f"Total time to read and extract document: {elapsed_time:.2f} seconds.")
        print(f">>>>>>>>>>>>>>>>>>>>PROCESSING TIME: {elapsed_time}<<<<<<<<<<<<<<<<<<<<<<")

        return jsonify({"message": "File(s) processed", "files": uploaded_urls}), 201

    except Exception as e:
        g.session.rollback()
        logging.exception(f"Upload failed: {str(e)}")
        print(f"Upload failed: {str(e)}")
        return jsonify({"error": "Failed to upload file"}), 500


def extract_structured_data_from_file(file_path, file_type):
    try:
        # Read the file content
        with open(file_path, 'rb') as f:
            file_content = f.read()

        # Process the document to extract text content
        text_content = process_document(file_content, file_type)

        # Parse the extracted text to get structured data
        structured_data = parse_chat_completion(text_content)

        # If structured_data is a Pydantic model, convert it to a dict
        if hasattr(structured_data, 'dict'):
            structured_data = structured_data.dict()

        return structured_data

    except Exception as e:
        logging.error(f"Error extracting structured data from file {file_path}: {str(e)}")
        return None

@document_bp.route('/documents', methods=['OPTIONS', 'GET', 'POST', 'DELETE', 'PUT'])
@cors_preflight
def get_documents():

    # GET request logic
    user_uuid = request.args.get('userUUID')
    if not user_uuid:
        return jsonify({"error": "User UUID is required"}), 400

    user = g.session.query(Users).filter_by(user_uuid=user_uuid).first()
    if not user:
        return jsonify({"error": "Invalid user UUID"}), 404

    files = g.session.query(File).filter_by(user_id=user.user_id).order_by(File.uploaded_at.desc()).all()

    document_list = [{
        "id": file.file_id,
        "title": file.file_name,
        "file_category": file.file_category,
        "file_type": file.file_type,
        "size": f"{file.file_size / (1024 * 1024):.2f}MB" if file.file_size else "Unknown",
        "shared": "Only Me",
        "modified": file.uploaded_at.strftime("%d/%m/%Y")
    } for file in files]

    return jsonify(document_list), 200

@document_bp.route('/documents/delete/<int:file_id>', methods=['DELETE', 'OPTIONS'])
@cors_preflight
def delete_document(file_id):
    # 1) Grab the userUUID from the query param (e.g. ?userUUID=xxx)
    user_uuid = request.args.get('userUUID', None)
    if not user_uuid:
        return jsonify({'error': 'Missing user UUID'}), 400

    # 2) Look up the user by UUID
    user = g.session.query(Users).filter_by(user_uuid=user_uuid).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    try:
        # 3) Check if the file exists
        file_record = g.session.query(File).get(file_id)
        if not file_record:
            return jsonify({"error": "File not found"}), 404

        # 4) Confirm that this file belongs to the same user
        if file_record.user_id != user.user_id:
            return jsonify({"error": "You do not own this file"}), 403

        # 5) Delete the blob from Azure
        blob_name = '/'.join(file_record.file_url.split('/')[-3:])
        container_client = blob_service_client.get_container_client(container_name)
        try:
            container_client.delete_blob(blob_name)
        except Exception as e:
            logging.error(f"Failed to delete blob '{blob_name}' from Azure: {e}")
            return jsonify({"error": f"Failed to delete file from Azure: {e}"}), 500

        # 6) Remove the file record from the database
        g.session.delete(file_record)
        g.session.commit()

        # 7) Re-check user’s nexus tags
        revoke_nexus_tags_if_invalid(g.session, user.user_id)
        g.session.commit()

        return jsonify({"message": "File deleted successfully"}), 200

    except Exception as e:
        g.session.rollback()
        logging.error(f"Error deleting file with id {file_id}: {e}")
        return jsonify({"error": f"Failed to delete file: {str(e)}"}), 500


def extract_blob_name(blob_url):
    # Example URL: "https://<account_name>.blob.core.windows.net/<container_name>/<blob_name>"
    return "/".join(blob_url.split("/")[4:])  # Gets the blob name from the full URL


@document_bp.route('/documents/rename/<int:file_id>', methods=['PUT', 'OPTIONS'])
@cors_preflight
def rename_document(file_id):
    data = request.get_json()
    new_name = data.get('new_name')

    # Input validation
    if not new_name:
        return jsonify({"error": "New name is required"}), 400

    # Ensure the new name does not include the file extension
    new_name_without_extension = os.path.splitext(new_name)[0]

    # Find the file by ID
    file = g.session.query(File).filter_by(file_id=file_id).first()
    if not file:
        return jsonify({"error": "File not found"}), 404

    # Extract current blob details
    blob_url = file.file_url
    old_blob_name = extract_blob_name(blob_url)
    
    # Extract the original file extension from the current file name
    file_extension = os.path.splitext(file.file_name)[1]  # e.g., ".pdf"
    
    # Construct the new blob name without duplicating the extension
    new_blob_name = "/".join(old_blob_name.split("/")[:-1]) + f"/{new_name_without_extension}{file_extension}"

    try:
        # Get container client
        container_client = blob_service_client.get_container_client(container_name)

        # Copy blob to a new blob with the new name
        source_blob = f"https://{account_name}.blob.core.windows.net/{container_name}/{old_blob_name}"
        new_blob_client = container_client.get_blob_client(new_blob_name)
        new_blob_client.start_copy_from_url(source_blob)

        # Ensure the new blob copy completes (it may take time)
        properties = new_blob_client.get_blob_properties()
        copy_status = properties.copy.status
        while copy_status == 'pending':
            time.sleep(1)
            properties = new_blob_client.get_blob_properties()
            copy_status = properties.copy.status

        if copy_status != "success":
            raise Exception("Blob copy operation failed.")

        # Delete the old blob
        container_client.delete_blob(old_blob_name)

        # Update the file name in the database
        file.file_name = f"{new_name_without_extension}{file_extension}"
        file.file_url = f"https://{account_name}.blob.core.windows.net/{container_name}/{new_blob_name}"
        g.session.commit()
        logging.info(f"File '{old_blob_name}' renamed to '{new_blob_name}' successfully.")
        
        return jsonify({"message": f"File '{old_blob_name}' renamed to '{new_name_without_extension}' successfully."}), 200

    except Exception as e:
        g.session.rollback()
        logging.error(f"Failed to rename file ID {file_id}: {str(e)}")
        return jsonify({"error": f"Failed to rename file: {str(e)}"}), 500


@document_bp.route('/documents/change-category/<int:file_id>', methods=['PUT', 'OPTIONS'])
@cors_preflight
def change_document_category(file_id):
    # Extract the data from the request
    data = request.get_json()
    new_category = data.get('new_category')

    # Validate inputs
    if not new_category:
        return jsonify({"error": "New category is required"}), 400

    # Find the file by ID
    file = g.session.query(File).filter_by(file_id=file_id).first()
    if not file:
        return jsonify({"error": "File not found"}), 404

    # Extract current blob details
    blob_url = file.file_url
    old_blob_name = extract_blob_name(blob_url)
    old_category = file.file_category

    # Update the category in the blob path
    new_blob_name = old_blob_name.replace(f"/{old_category}/", f"/{new_category}/")

    try:
        # Get container client
        container_client = blob_service_client.get_container_client(container_name)

        # Copy blob to new category path
        source_blob = f"https://{account_name}.blob.core.windows.net/{container_name}/{old_blob_name}"
        new_blob_client = container_client.get_blob_client(new_blob_name)
        copy_response = new_blob_client.start_copy_from_url(source_blob)

        # Ensure the new blob copy completes
        properties = new_blob_client.get_blob_properties()
        copy_status = properties.copy.status
        while copy_status == 'pending':
            time.sleep(1)
            properties = new_blob_client.get_blob_properties()
            copy_status = properties.copy.status

        if copy_status != "success":
            raise Exception("Blob copy operation failed.")

        # Delete the old blob
        container_client.delete_blob(old_blob_name)

        # Update the category and blob URL in the database
        file.file_category = new_category
        file.file_url = f"https://{account_name}.blob.core.windows.net/{container_name}/{new_blob_name}"
        g.session.commit()

        logging.info(f"File category changed from '{old_category}' to '{new_category}' for file '{file.file_name}'.")
        
        return jsonify({"message": f"Category updated successfully to '{new_category}' for file '{file.file_name}'."}), 200

    except Exception as e:
        g.session.rollback()
        logging.error(f"Failed to change category for file ID {file_id}: {str(e)}")
        return jsonify({"error": f"Failed to change category: {str(e)}"}), 500

@document_bp.route('/documents/download/<int:file_id>', methods=['GET', 'OPTIONS'])
@cors_preflight
def download_document(file_id):
    try:
        # Fetch the file from the database
        file = g.session.query(File).filter_by(file_id=file_id).first()
        if not file:
            return jsonify({"error": "File not found"}), 404

        # Return the file URL directly for download
        return jsonify({"download_url": file.file_url}), 200

    except Exception as e:
        logging.error(f"Failed to get download URL for file ID {file_id}: {str(e)}")
        return jsonify({"error": f"Failed to get download URL: {str(e)}"}), 500

@document_bp.route('/documents/preview/<int:file_id>', methods=['GET', 'OPTIONS'])
@cors_preflight
def preview_document(file_id):
    
    try:
        # Fetch the file from the database
        file = g.session.query(File).filter_by(file_id=file_id).first()
        if not file:
            return jsonify({"error": "File not found"}), 404

        # Extract blob details from the URL
        blob_name = extract_blob_name(file.file_url)

        # Generate a SAS token for previewing the file (valid for 1 hour)
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container_name,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(hours=1)
        )

        if not sas_token:
            logging.error(f"Failed to generate SAS token for file ID {file_id}")
            return jsonify({"error": "Failed to generate SAS token"}), 500

        # Construct the preview URL using the SAS token and set disposition to inline
        preview_url = f"{file.file_url}?{sas_token}&response-content-disposition=inline"

        return jsonify({"preview_url": preview_url}), 200

    except FileNotFoundError as e:
        logging.error(f"File not found error for file ID {file_id}: {str(e)}")
        return jsonify({"error": "File not found."}), 404
    except PermissionError as e:
        logging.error(f"Permission error for file ID {file_id}: {str(e)}")
        return jsonify({"error": "Permission denied."}), 403
    except Exception as e:
        logging.error(f"Failed to generate preview URL for file ID {file_id}: {str(e)}")
        return jsonify({"error": f"Failed to generate preview URL: {str(e)}"}), 500

@document_bp.route('/upload-file', methods=['POST', 'OPTIONS'])
@cors_preflight
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    
    file = request.files['file']
    document_type = request.form.get("document_type")

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if not document_type:
        return jsonify({"error": "Document type is required"}), 400

    # Define blob name based on document type and filename
    blob_name = f"{document_type}_{file.filename}"
    
    # Save the file temporarily to upload it
    temp_file_path = f"/tmp/{file.filename}"
    file.save(temp_file_path)
    
    # Upload file to Azure
    blob_url = upload_file_to_azure(temp_file_path, blob_name)
    
    # Remove the temporary file
    os.remove(temp_file_path)
    
    if blob_url:
        return jsonify({"message": "File uploaded successfully", "url": blob_url}), 200
    else:
        return jsonify({"error": "Failed to upload file"}), 500

@document_bp.route('/get-file-url/<blob_name>', methods=['GET', 'OPTIONS'])
@cors_preflight
def get_file_url(blob_name):
    try:
        # Generate the SAS URL using the helper function
        file_url = generate_sas_url(blob_name)
        
        # If SAS URL generation was successful, return it as a JSON response
        if file_url:
            return jsonify({"url": file_url}), 200
        else:
            return jsonify({"error": "Failed to generate SAS URL"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
