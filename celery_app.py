# celery_app.py

from celery import Celery, chain
import logging
import os
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
import ssl
from helpers.azure_helpers import download_blob_to_tempfile
from helpers.visit_processor import process_visit
from helpers.sql_helpers import discover_nexus_tags, revoke_nexus_tags_if_invalid
from helpers.text_ext_helpers import read_and_extract_document
from database.session import ScopedSession

# Example: "redis://localhost:6379/0" or use your actual Redis connection string
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'rediss://:e9QG8zns7nfaWIqwhG3jbvlBEJnmvnDcjAzCaKxrbp8=@vaclaimguard.redis.cache.windows.net:6380/0')
CELERY_RESULT_BACKEND = CELERY_BROKER_URL

celery = Celery('vaclaimguard', broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)
"""
vaclaimguard.redis.cache.windows.net:6380,password=e9QG8zns7nfaWIqwhG3jbvlBEJnmvnDcjAzCaKxrbp8=,ssl=True,abortConnect=False


redis-cli -h vaclaimguard.redis.cache.windows.net -p 6380 -a e9QG8zns7nfaWIqwhG3jbvlBEJnmvnDcjAzCaKxrbp8= --tls
"""



celery.conf.update(
    broker_use_ssl={
        'ssl_cert_reqs': ssl.CERT_REQUIRED
    },
    redis_backend_use_ssl={
        'ssl_cert_reqs': ssl.CERT_REQUIRED
    }
)

@celery.task(bind=True, max_retries=3, default_retry_delay=10)
def extraction_task(self, blob_url, file_type):
    """
    Downloads the file from Azure (if needed) and extracts document details.
    Returns parsed details as a Python object.
    """
    try:
        # Download the blob to a local temp file
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            local_path = tmp_file.name

        download_blob_to_tempfile(blob_url, local_path)

        # Now read & extract
        details_str = read_and_extract_document(local_path, file_type)
        os.remove(local_path)  # Clean up local copy after extraction

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
    Processes the pages extracted from a document, handling visits concurrently.
    Writes results to the DB using a ScopedSession.
    """
    try:
        print(f"service_periods******: {file_info.get('service_periods')}")
        service_periods = file_info.get('service_periods')
        print(f"service_periods******: {service_periods}")
        file_id = file_info.get('file_id')

        # We'll store aggregated results (optional usage)
        processed_results = []

        with ScopedSession() as session:
            max_workers = 10
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []

                # Iterate over each page in details
                for page in details:
                    page_number = page.get('page')
                    logging.info(f"Processing page {page_number}")

                    if page.get('category') == 'Clinical Records':
                        visits = page.get('details', {}).get('visits', [])
                        logging.info(f"Found {len(visits)} visits on page {page_number}")

                        for visit in visits:
                            # We can process each visit in a ThreadPool
                            future = executor.submit(
                                process_visit,
                                visit=visit,
                                page_number=page_number,
                                service_periods=service_periods,
                                user_id=user_id,
                                file_id=file_id
                            )
                            futures.append(future)

                for future in as_completed(futures):
                    try:
                        visit_result = future.result()
                        processed_results.append(visit_result)
                    except Exception as e:
                        logging.exception(f"Error processing visit: {str(e)}")

            # You might do additional session.commit() logic or other updates here
            session.commit()

        # Return processed results for next step in chain if needed
        return processed_results

    except Exception as exc:
        logging.exception(f"Processing pages failed: {exc}")
        raise self.retry(exc=exc)


@celery.task(bind=True, max_retries=3, default_retry_delay=10)
def finalize_task(self, processed_results, user_id):
    """
    Final DB updates after pages are processed, e.g. discovering and revoking nexus tags.
    """
    try:
        with ScopedSession() as session:
            # Now discover any newly qualified nexus tags for this user
            discover_nexus_tags(session, user_id)

            # Optionally revoke nexus tags that no longer qualify
            revoke_nexus_tags_if_invalid(session, user_id)

            session.commit()

        # Return final status or any other info needed
        return {"status": "complete", "user_id": user_id}

    except Exception as exc:
        logging.exception(f"Finalize step failed: {exc}")
        raise self.retry(exc=exc)
