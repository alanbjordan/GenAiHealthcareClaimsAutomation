# diagnosis_list.py


from helpers.diagnosis_worker import worker_process_diagnosis
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging


def process_diagnosis_list(diagnosis_list, user, file_id, page_number, date_of_visit, medical_professionals_str, in_service):
    """
    Processes a list of diagnoses using a thread pool.
    """
    max_workers = 10  # Adjust based on your environment
    futures = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for diagnosis in diagnosis_list:
            future = executor.submit(
                worker_process_diagnosis,
                diagnosis,
                user.user_id,
                file_id,
                page_number,
                date_of_visit,
                medical_professionals_str,
                in_service,
                # Each worker_process_diagnosis call requires a session; consider how session is passed if needed.
                # If you need a session, you'll need to create or pass one here. 
                # If worker_process_diagnosis creates its own session inside the call, this line can remain as is.
            )
            futures.append(future)

        for future in as_completed(futures):
            try:
                future.result()  # To catch exceptions raised in threads
            except Exception as e:
                logging.error(f"Error in thread: {e}")

    logging.info("All diagnoses have been processed.")
