from flask import Blueprint, request, jsonify
from models.sql_models import File, Users, Conditions, Tag, condition_tags
from config import Config
from datetime import datetime
from helpers.azure_helpers import generate_sas_url, extract_blob_name
import logging
import time
from sqlalchemy.orm import defer
from database.session import ScopedSession
from models.sql_models import *

condition_bp = Blueprint('condition_bp', __name__)
session = ScopedSession()

@condition_bp.route('/conditions', methods=['OPTIONS', 'GET'])
def get_conditions():
    start_time = time.time()  # Start timing the entire request

    if request.method == 'OPTIONS':
        print("Received CORS preflight request.")
        response = jsonify({"message": "CORS preflight successful"})
        response.headers["Access-Control-Allow-Origin"] = Config.CORS_ORIGINS
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, user-uuid"
        response.headers["Access-Control-Allow-Methods"] = "GET, PUT, POST, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        print("CORS preflight response sent.")
        print(f"Total time for OPTIONS request: {time.time() - start_time:.4f} seconds.")
        return response, 200

    user_uuid = request.args.get('userUUID')
    print(f"Received GET /conditions request with userUUID: {user_uuid}")

    if not user_uuid:
        print("User UUID not provided in the request.")
        print(f"Total time for request: {time.time() - start_time:.4f} seconds.")
        return jsonify({"error": "User UUID is required"}), 400

    user_start_time = time.time()
    user = session.query(Users).filter_by(user_uuid=user_uuid).first()
    user_elapsed_time = time.time() - user_start_time

    if not user:
        print(f"Invalid user UUID: {user_uuid}")
        print(f"User lookup time: {user_elapsed_time:.4f} seconds.")
        print(f"Total time for request: {time.time() - start_time:.4f} seconds.")
        return jsonify({"error": "Invalid user UUID"}), 404

    print(f"Found user with user_id: {user.user_id}")
    print(f"User lookup time: {user_elapsed_time:.4f} seconds.")

    # Start timing the database query
    query_start_time = time.time()

    try:
        # Fetch conditions, files, and tags, excluding Tag.embeddings
        conditions = session.query(
            Conditions,
            File,
            Tag
        ).options(
            defer(Tag.embeddings)  # Exclude the 'embeddings' column
        ).join(File, Conditions.file_id == File.file_id)\
        .join(condition_tags, Conditions.condition_id == condition_tags.c.condition_id)\
        .join(Tag, condition_tags.c.tag_id == Tag.tag_id)\
        .filter(Conditions.user_id == user.user_id)\
        .order_by(Tag.disability_name, Conditions.condition_name).all()

        query_elapsed_time = time.time() - query_start_time
        print(f"POINT OF INTEREST: Database query executed in {query_elapsed_time:.4f} seconds. Retrieved {len(conditions)} records.")
    except Exception as e:
        print(f"Database query failed: {e}")
        print(f"Total time for request: {time.time() - start_time:.4f} seconds.")
        return jsonify({"error": "Failed to retrieve conditions."}), 500

    # Extract unique blob names
    extract_start_time = time.time()
    unique_blob_names = set()
    for condition, file, tag in conditions:
        blob_name = extract_blob_name(file.file_url)
        unique_blob_names.add(blob_name)

    extract_elapsed_time = time.time() - extract_start_time
    print(f"Extracted {len(unique_blob_names)} unique blobs in {extract_elapsed_time:.4f} seconds.")

    # Generate SAS URLs
    sas_urls = {}
    sas_url_start_time = time.time()
    for blob_name in unique_blob_names:
        sas_url = generate_sas_url(blob_name)
        sas_urls[blob_name] = sas_url if sas_url else None

    sas_url_elapsed_time = time.time() - sas_url_start_time
    print(f"Generated {len(sas_urls)} SAS URLs in {sas_url_elapsed_time:.4f} seconds.")

    # Organize conditions by tag
    organize_start_time = time.time()
    conditions_by_tag = {}
    for condition, file, tag in conditions:
        tag_name = tag.disability_name
        if tag_name not in conditions_by_tag:
            conditions_by_tag[tag_name] = {
                'tag_id': tag.tag_id,
                'tag_name': tag_name,
                'description': tag.description,
                'conditions': []
            }

        blob_name = extract_blob_name(file.file_url)
        file_sas_url = sas_urls.get(blob_name)

        condition_data = {
            "condition_id": condition.condition_id,
            "condition_name": condition.condition_name,
            "page_number": condition.page_number,
            "date_of_visit": condition.date_of_visit.strftime('%Y-%m-%d') if condition.date_of_visit else None,
            "in_service": condition.in_service,
            "medical_professionals": condition.medical_professionals,
            "medications_list": condition.medications_list,
            "treatments": condition.treatments,
            "findings": condition.findings,
            "comments": condition.comments,
            "file": {
                "id": file.file_id,
                "name": file.file_name,
                "type": file.file_type,
                "url": file_sas_url
            }
        }

        conditions_by_tag[tag_name]['conditions'].append(condition_data)

    organize_elapsed_time = time.time() - organize_start_time
    print(f"Organized conditions in {organize_elapsed_time:.4f} seconds.")

    # Convert to list for response
    response_data_start_time = time.time()
    response_data = list(conditions_by_tag.values())
    response_data_elapsed_time = time.time() - response_data_start_time

    total_conditions = sum(len(tag_group['conditions']) for tag_group in conditions_by_tag.values())
    print(f"Prepared response data with {len(response_data)} tags and {total_conditions} conditions in {response_data_elapsed_time:.4f} seconds.")

    print(f"Total time for request: {time.time() - start_time:.4f} seconds.")

    return jsonify(response_data), 200


@condition_bp.route("/feed_updates", methods=["GET"])
def feed_updates():
    """
    Returns a list of active nexus tags along with 
    all associated Conditions (including their fields).
    This can be used in a front-end "Updates" or "Feed" section 
    to highlight newly discovered nexus tags and the relevant 
    in-service/current conditions that triggered them.
    """
    if request.method == 'OPTIONS':
        print("Received CORS preflight request.")
        response = jsonify({"message": "CORS preflight successful"})
        response.headers["Access-Control-Allow-Origin"] = Config.CORS_ORIGINS
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, user-uuid"
        response.headers["Access-Control-Allow-Methods"] = "GET, PUT, POST, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        print("CORS preflight response sent.")
        return response, 200
    
    # 1. Query all active nexus rows (revoked_at is still NULL)
    active_nexus_tags = (
        session.query(NexusTags)
        .filter(NexusTags.revoked_at.is_(None))
        .all()
    )

    response_data = []

    # 2. Build the response
    for nexus in active_nexus_tags:
        # "tag" is the Tag object (relationship from NexusTags to Tag)
        t = nexus.tag

        # 3. Find all Conditions associated with this tag
        #    (Use your many-to-many table condition_tags)
        conditions = (
            session.query(Conditions)
            .join(condition_tags, condition_tags.c.condition_id == Conditions.condition_id)
            .filter(condition_tags.c.tag_id == t.tag_id)
            .all()
        )

        # 4. Assemble the list of condition dictionaries
        condition_list = []
        for c in conditions:
            condition_list.append({
                "condition_id": c.condition_id,
                "condition_name": c.condition_name,
                "date_of_visit": c.date_of_visit.isoformat() if c.date_of_visit else None,
                "medical_professionals": c.medical_professionals,
                "treatments": c.treatments,
                "findings": c.findings,
                "comments": c.comments,
                "in_service": c.in_service,
                # Add more fields if needed
            })

        # 5. Build the nexus-level entry
        response_data.append({
            "nexus_tags_id": nexus.nexus_tags_id,
            "tag_id": t.tag_id,
            "disability_name": t.disability_name,  # e.g., "Knee Condition"
            "discovered_at": nexus.discovered_at.isoformat() if nexus.discovered_at else None,
            "conditions": condition_list,
        })

    return jsonify(response_data), 200
