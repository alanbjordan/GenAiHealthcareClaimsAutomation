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

# Example: "redis://localhost:6379/0" or use your actual Redis connection string with password
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'rediss://:e9QG8zns7nfaWIqwhG3jbvlBEJnmvnDcjAzCaKxrbp8=@vaclaimguard.redis.cache.windows.net:6380/0')
CELERY_RESULT_BACKEND = CELERY_BROKER_URL

celery = Celery('vaclaimguard', broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)

celery.conf.update(
    broker_use_ssl={
        'ssl_cert_reqs': ssl.CERT_REQUIRED
    },
    redis_backend_use_ssl={
        'ssl_cert_reqs': ssl.CERT_REQUIRED
    }
)

# This task downloads the file from Azure (if needed) and extracts document details.
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
    """
    try:
        service_periods = file_info.get('service_periods')
        file_id = file_info.get('file_id')

        # 1) Mark the file as "Finding Evidence"
        with ScopedSession() as session:
            file_record = session.query(File).filter_by(file_id=file_id).first()
            if file_record:
                file_record.status = 'Finding Evidence'
                session.add(file_record)
                session.commit()

        processed_results = []

        # 2) Use a ThreadPoolExecutor to handle multiple visits concurrently.
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
        # Celery retry logic:


# This task performs final DB updates after pages are processed, e.g. discovering and revoking nexus tags.
@celery.task(bind=True, max_retries=3, default_retry_delay=10)
def finalize_task(self, processed_results, user_id, file_id):
    """
    Final DB updates after pages are processed, e.g. discovering and revoking nexus tags.
    """
    try:
        with ScopedSession() as session:
            # Now discover any newly qualified nexus tags for this user
            discover_nexus_tags(session, user_id)

            # Optionally revoke nexus tags that no longer qualify
            revoke_nexus_tags_if_invalid(session, user_id)
            # Now update the file’s status to "Complete"
            file_record = session.query(File).filter_by(file_id=file_id).first()
            if file_record:
                file_record.status = 'Complete'
                session.add(file_record)

            session.commit()

        # Return final status or any other info needed
        return {"status": "complete", "user_id": user_id}

    except Exception as exc:
        logging.exception(f"Finalize step failed: {exc}")
        # Optionally update status to "Failed"
        with ScopedSession() as session:
            file_record = session.query(File).filter_by(file_id=file_id).first()
            if file_record:
                file_record.status = 'Failed'
                session.add(file_record)
                session.commit()

            raise self.retry(exc=exc)
