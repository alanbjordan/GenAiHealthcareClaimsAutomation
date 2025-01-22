# diagnosis_processor.py is a helper function to process a single diagnosis and save it to the database.

import logging
from models.sql_models import Conditions

def process_diagnosis(diagnosis, user_id, file_id, page_number, date_of_visit, medical_professionals_str, in_service, session):
    """
    Processes a single diagnosis and saves it to the database.

    Returns a dictionary with the newly created condition_id, condition_name, and findings,
    but NOT the actual 'new_condition' ORM object, to avoid passing a detached object elsewhere.
    """
    condition_name = diagnosis.get('diagnosis_name')
    medications = diagnosis.get('medication_list', [])
    treatments = diagnosis.get('treatments')
    findings = diagnosis.get('findings')
    comments = diagnosis.get('doctor_comments')

    if not isinstance(condition_name, str):
        logging.warning(f"Invalid condition_name: {condition_name} on page {page_number}")
        print(f"Invalid condition_name: {condition_name} on page {page_number}")
        return None

    try:
        new_condition = Conditions(
            user_id=user_id,
            file_id=file_id,
            page_number=page_number,
            condition_name=condition_name,
            date_of_visit=date_of_visit,
            medical_professionals=medical_professionals_str,
            medications_list=medications,
            treatments=treatments,
            findings=findings,
            comments=comments,
            in_service=in_service
        )

        session.add(new_condition)
        session.flush()  # Assigns condition_id
        condition_id = new_condition.condition_id

        logging.info(f"Inserted new condition with ID {condition_id}")
        print(f"Inserted new condition with ID {condition_id}")

        # Return only scalar data (and anything else you need), NOT the ORM object
        return {
            "condition_id": condition_id,
            "condition_name": condition_name,
            "findings": findings
        }

    except Exception as e:
        logging.error(f"Error processing diagnosis on page {page_number}: {e}")
        print(f"Error processing diagnosis on page {page_number}: {e}")
        session.rollback()
        return None



# celery_app.py

from celery import Celery, chain
import logging
import os
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
import ssl

from helpers.text_ext_helpers import read_and_extract_document
from database.session import ScopedSession
from helpers.azure_helpers import download_blob_to_tempfile
from helpers.sql_helpers import discover_nexus_tags, revoke_nexus_tags_if_invalid, File
from helpers.visit_processor import process_visit

# Example: "redis://localhost:6379/0" or use your actual Redis connection string
CELERY_BROKER_URL = os.getenv(
    'CELERY_BROKER_URL',
    'rediss://:e9QG8zns7nfaWIqwhG3jbvlBEJnmvnDcjAzCaKxrbp8=@vaclaimguard.redis.cache.windows.net:6380/0'
)
CELERY_RESULT_BACKEND = CELERY_BROKER_URL

celery = Celery('vaclaimguard', broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)

celery.conf.update(
    broker_use_ssl={'ssl_cert_reqs': ssl.CERT_REQUIRED},
    redis_backend_use_ssl={'ssl_cert_reqs': ssl.CERT_REQUIRED}
)


@celery.task(bind=True, max_retries=3, default_retry_delay=10)
def extraction_task(self, user_id, blob_url, file_type, file_id):
    """
    Downloads the file from Azure (if needed) and extracts document details.
    Returns parsed details as a Python object.
    """
    try:
        # 1) Mark the file as "Extracting Data"
        with ScopedSession() as session:
            file_record = session.query(File).filter_by(file_id=file_id).first()
            if file_record:
                file_record.status = 'Extracting Data'
                session.add(file_record)
                session.commit()

        # 2) Download the blob to a local temp file
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            local_path = tmp_file.name

        download_blob_to_tempfile(blob_url, local_path)

        # 3) Perform extraction
        details_str = read_and_extract_document(user_id, local_path, file_type)

        # 4) Clean up local copy after extraction
        os.remove(local_path)

        # If extraction returns None or fails, parse as empty
        if not details_str:
            return []

        # Convert JSON string -> Python object
        parsed_details = json.loads(details_str)
        return parsed_details

    except Exception as exc:
        logging.exception(f"Extraction failed: {exc}")
        raise self.retry(exc=exc)


@celery.task(bind=True, max_retries=3, default_retry_delay=10)
def process_pages_task(self, details, user_id, user_uuid, file_info):
    """
    Processes pages in parallel at the 'visit' level using a ThreadPoolExecutor.
    Each thread calls process_visit, which handles its own DB session internally.

    :param details: List of pages from the extraction step, each containing 'page' and 'category' keys,
                    plus any extracted data (like 'visits').
    :param user_id: The user ID (needed for DB operations).
    :param user_uuid: Potentially used to track user (not explicitly used here).
    :param file_info: Dictionary that includes the file_id and service_periods used in the process.
    :return: A list of processed_results from each visit, typically minimal info (e.g. date_of_visit).
    """
    try:
        service_periods = file_info.get('service_periods')
        file_id = file_info.get('file_id')

        # 1) Mark the file as "Finding Evidence" (quick DB update)
        with ScopedSession() as session:
            file_record = session.query(File).filter_by(file_id=file_id).first()
            if file_record:
                file_record.status = 'Finding Evidence'
                session.add(file_record)
                session.commit()

        processed_results = []

        # 2) Use a ThreadPoolExecutor to handle multiple visits concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []

            # Iterate over each page in details
            for page in details:
                page_number = page.get('page')
                logging.info(f"Processing page {page_number}")

                if page.get('category') == 'Clinical Records':
                    visits = page.get('details', {}).get('visits', [])
                    logging.info(f"Found {len(visits)} visits on page {page_number}")

                    # Submit each visit to the executor
                    for visit in visits:
                        # process_visit handles its own DB session usage
                        future = executor.submit(
                            process_visit,
                            visit=visit,
                            page_number=page_number,
                            service_periods=service_periods,
                            user_id=user_id,
                            file_id=file_id
                        )
                        futures.append(future)

            # 3) Gather results as they complete
            for future in as_completed(futures):
                try:
                    visit_result = future.result()  # process_visit return
                    if visit_result is not None:
                        processed_results.append(visit_result)
                except Exception as e:
                    logging.exception(f"Error processing a visit: {e}")

        # 4) Return processed results
        return processed_results

    except Exception as exc:
        logging.exception(f"Processing pages failed: {exc}")
        # Optionally, you can raise self.retry(...) if you want Celery to retry
        raise


@celery.task(bind=True, max_retries=3, default_retry_delay=10)
def finalize_task(self, processed_results, user_id, file_id):
    """
    Final DB updates after pages are processed, e.g. discovering and revoking nexus tags.

    :param processed_results: The list returned by process_pages_task (not used directly for DB updates here).
    :param user_id: The user ID for DB updates.
    :param file_id: The file ID to mark as 'Complete' or 'Failed'.
    :return: A dictionary with status info.
    """
    try:
        with ScopedSession() as session:
            # Now discover any newly qualified nexus tags for this user
            discover_nexus_tags(session, user_id)

            # Optionally revoke nexus tags that no longer qualify
            revoke_nexus_tags_if_invalid(session, user_id)

            # Mark the file as "Complete"
            file_record = session.query(File).filter_by(file_id=file_id).first()
            if file_record:
                file_record.status = 'Complete'
                session.add(file_record)
            session.commit()

        return {"status": "complete", "user_id": user_id}

    except Exception as exc:
        logging.exception(f"Finalize step failed: {exc}")
        # Optionally mark the file as 'Failed' in DB, then retry
        with ScopedSession() as session:
            file_record = session.query(File).filter_by(file_id=file_id).first()
            if file_record:
                file_record.status = 'Failed'
                session.add(file_record)
                session.commit()

        raise self.retry(exc=exc)




# duagbisus_worker.py

import logging
from database.session import ScopedSession
from helpers.diagnosis_processor import process_diagnosis
from helpers.embedding_helpers import process_condition_embedding
from models.sql_models import Conditions

def worker_process_diagnosis(diagnosis, user_id, file_id, page_number, date_of_visit, medical_professionals_str, in_service):
    """
    Worker function to process a single diagnosis and handle embedding.

    This function creates its own session for diagnosis insertion,
    and calls process_condition_embedding (which also creates its own session).
    """
    # STEP 1: Insert the new condition within our own session
    try:
        with ScopedSession() as session:
            result = process_diagnosis(
                diagnosis=diagnosis,
                user_id=user_id,
                file_id=file_id,
                page_number=page_number,
                date_of_visit=date_of_visit,
                medical_professionals_str=medical_professionals_str,
                in_service=in_service,
                session=session  # pass local session to process_diagnosis
            )
            session.commit()  # commit the new condition creation

        # STEP 2: If condition was created, handle embeddings in a BRAND-NEW session inside process_condition_embedding
        if result:
            condition_id = result["condition_id"]
            condition_name = result["condition_name"]
            findings = result["findings"]

            combined_text = f"Condition Name: {condition_name}, Findings: {findings}"
            logging.debug(f"Combined text for embedding: {combined_text.strip()}")
            logging.info(f"Combined text for embedding: {combined_text.strip()}")
            print(f"Combined text for embedding: {combined_text.strip()}")

            try:
                process_condition_embedding(user_id, condition_id, combined_text)
            except Exception as e:
                # Embedding step failed. We'll mark the condition as non-ratable in a new session.
                logging.error(f"Failed to generate or assign embedding for condition_id in diagnosis worker {condition_id}: {str(e)}")
                print(f"Failed to generate or assign embedding for condition_id in diagnosis worker {condition_id}: {str(e)}")

                with ScopedSession() as session:
                    condition_obj = session.query(Conditions).get(condition_id)
                    if condition_obj:
                        condition_obj.is_ratable = False
                        session.commit()

    except Exception as e:
        logging.error(f"Unexpected error in worker_process_diagnosis: {e}")



# helpers/embedding_helpers.py

import logging
from database.session import ScopedSession
from models.sql_models import Tag, Conditions, ConditionEmbedding
from sqlalchemy import func
from pgvector.sqlalchemy import Vector
from helpers.llm_helpers import generate_embedding

MAX_COSINE_DISTANCE = 0.559

def find_top_tags(session, embedding_vector: list, top_n: int = 2):
    """
    Finds the top N tags with the smallest cosine distance to the provided embedding_vector.
    Returns a list of tuples (Tag, cosine_distance).
    """
    distance = Tag.embeddings.cosine_distance(embedding_vector)
    similar_tags = (
        session.query(Tag, distance.label('distance'))
        .order_by(distance)
        .limit(top_n)
        .all()
    )
    return similar_tags


def process_condition_embedding(user_id, condition_id, combined_text):
    """
    Generates an embedding for the given condition (in a brand-new session),
    stores it, and associates top tags based on similarity.
    """
    logging.debug(f"[process_condition_embedding] Starting with user_id={user_id}, condition_id={condition_id}")
    logging.debug(f"[process_condition_embedding] combined_text={combined_text[:100]}... (truncated)")

    with ScopedSession() as session:
        # Optional: log the session identity, if helpful for debugging
        logging.debug(f"[process_condition_embedding] Opened new session {session}, is_active={session.is_active}")

        try:
            # 1) Re-fetch Condition in this new session
            condition_obj = session.query(Conditions).get(condition_id)
            if not condition_obj:
                logging.error(f"[process_condition_embedding] Condition with ID {condition_id} not found in DB.")
                return

            logging.debug(f"[process_condition_embedding] Fetched condition_id={condition_id}, is_ratable={condition_obj.is_ratable}, in_service={condition_obj.in_service}")

            # 2) Generate the embedding
            logging.info(f"[process_condition_embedding] Generating embedding for condition_id={condition_id}")
            embedding_vector = generate_embedding(user_id, combined_text.strip())

            logging.info(f"[process_condition_embedding] Embedding generation complete for condition_id={condition_id}")
            logging.info(f"[process_condition_embedding] embedding_vector length={len(embedding_vector) if embedding_vector else 'None'}")

            if embedding_vector is not None:
                # 3) Create & store the ConditionEmbedding row
                new_embedding = ConditionEmbedding(
                    condition_id=condition_id,
                    embedding=embedding_vector
                )
                session.add(new_embedding)
                logging.info(f"[process_condition_embedding] ***** NEW CODDDDDEEEE!!!!! Created new ConditionEmbedding row for condition_id={condition_id}")

                # 4) Perform similarity search and associate tag
                logging.info(f"[process_condition_embedding] Performing similarity search for condition_id={condition_id}")
                top_tags_with_distance = find_top_tags(session, embedding_vector, top_n=1)

                if top_tags_with_distance:
                    top_tag, distance = top_tags_with_distance[0]
                    logging.info(f"[process_condition_embedding] Closest tag_id={top_tag.tag_id}, distance={distance}")

                    if distance <= MAX_COSINE_DISTANCE:
                        logging.info(f"[process_condition_embedding] Appending tag_id={top_tag.tag_id} to condition_id={condition_id} tags relationship.")
                        condition_obj = session.query(Conditions).get(condition_id)
                        condition_obj.tags.append(top_tag)

                        logging.info(
                            f"[process_condition_embedding] Associated tag {top_tag.tag_id} "
                            f"with condition_id={condition_id} (distance={distance:.4f})"
                        )
                    else:
                        logging.info(f"[process_condition_embedding] distance={distance:.4f} > MAX_COSINE_DISTANCE={MAX_COSINE_DISTANCE}, marking non-ratable.")
                        session.query(Conditions).get(condition_id).is_ratable = False
                        logging.info(
                            f"[process_condition_embedding] Condition_id={condition_id} marked as non-ratable "
                            f"(distance={distance:.4f} exceeds threshold)"
                        )
                else:
                    logging.info("[process_condition_embedding] No tags found, marking non-ratable.")
                    condition_obj.is_ratable = False
                    logging.info(
                        f"[process_condition_embedding] Condition_id={condition_id} marked as non-ratable (no tags found)"
                    )

            else:
                # Embedding call returned None
                logging.info(f"[process_condition_embedding] Embedding was None, marking condition_id={condition_id} as non-ratable.")
                session.query(Conditions).get(condition_id).is_ratable = False
                logging.error(
                    f"[process_condition_embedding] Embedding vector is None for condition_id {condition_id}; marked as non-ratable"
                )

            # Commit changes in this brand-new session
            logging.info(f"[process_condition_embedding] Attempting session.commit() for condition_id={condition_id}.")
            session.commit()
            logging.info(f"[process_condition_embedding] session.commit() complete for condition_id={condition_id}.")

        except Exception as e:
            logging.error(
                f"[process_condition_embedding] Failed to generate or assign embedding for condition_id {condition_id}: {str(e)} in embedding helper"
            )
            logging.info(
                f"[process_condition_embedding] Rolling back session for condition_id {condition_id} due to exception."
            )
            session.rollback()

        finally:
            logging.debug(f"[process_condition_embedding] Exiting session block for condition_id={condition_id}. is_active={session.is_active}")



# visit_processor.py
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from database.session import ScopedSession
from helpers.diagnosis_worker import worker_process_diagnosis

def process_visit(visit, page_number, service_periods, user_id, file_id):
    """
    Processes a single visit, including its diagnoses, using a ThreadPoolExecutor
    for concurrency (no chunking). Each diagnosis is handled in its own session.
    """

    # 1) Parse the visit date
    date_of_visit = visit.get('date_of_visit')
    try:
        date_of_visit_dt = datetime.strptime(date_of_visit, '%Y-%m-%d').date()
    except ValueError as ve:
        logging.error(f"Invalid date format '{date_of_visit}' on page {page_number}: {ve}")
        print(f"Invalid date format '{date_of_visit}' on page {page_number}: {ve}")
        return

    # 2) Extract relevant fields from the visit
    diagnosis_list = visit.get('diagnosis', [])
    medical_professionals = visit.get('medical_professionals', [])
    medical_professionals_str = ', '.join(medical_professionals) if medical_professionals else None

    logging.info(f"Processing visit on {date_of_visit} with {len(diagnosis_list)} diagnoses")
    print(f"check new file Processing visit on {date_of_visit} with {len(diagnosis_list)} diagnoses")
    logging.debug(f"Medical professionals: {medical_professionals_str}")
    print(f"Medical professionals: {medical_professionals_str}")

    # 3) Check if date_of_visit is within any service period
    in_service = any(
        period['service_start_date'] <= date_of_visit_dt <= period['service_end_date']
        for period in service_periods
    )
    logging.debug(f"Visit date {date_of_visit_dt} in service period: {in_service}")
    logging.info(f"Visit date {date_of_visit_dt} in service period: {in_service}")
    print(f"Visit date {date_of_visit_dt} in service period: {in_service}")

    # 4) Define a helper function to process a single diagnosis in its own session
    def process_single_diagnosis(diagnosis):
        session = ScopedSession()
        try:
            worker_process_diagnosis(
                diagnosis=diagnosis,
                user_id=user_id,
                file_id=file_id,
                page_number=page_number,
                date_of_visit=date_of_visit_dt,
                medical_professionals_str=medical_professionals_str,
                in_service=in_service
            )
            session.commit()
        except Exception as e:
            session.rollback()
            logging.error(f"Error processing diagnosis: {e}")
            print(f"Error processing diagnosis: {e}")
        finally:
            # Remove (close) the scoped session
            ScopedSession.remove()

    # 5) Use a ThreadPoolExecutor to process each diagnosis concurrently
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_single_diagnosis, diag) for diag in diagnosis_list]
        # Wait for all tasks to complete
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logging.error(f"Thread raised an exception: {e}")

    # 6) Return any relevant data about this visit
    return {
        "date_of_visit": date_of_visit,
        "date_of_visit_dt": date_of_visit_dt
    }
