import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from database.session import ScopedSession
from helpers.diagnosis_worker import worker_process_diagnosis

def process_visit(visit, page_number, service_periods, user_id, file_id):
    """
    Processes a single visit, including its diagnoses, using a ThreadPoolExecutor
    for concurrency (no chunking).
    """
    date_of_visit = visit.get('date_of_visit')
    try:
        date_of_visit_dt = datetime.strptime(date_of_visit, '%Y-%m-%d').date()
    except ValueError as ve:
        logging.error(f"Invalid date format '{date_of_visit}' on page {page_number}: {ve}")
        print(f"Invalid date format '{date_of_visit}' on page {page_number}: {ve}")
        return

    diagnosis_list = visit.get('diagnosis', [])
    medical_professionals = visit.get('medical_professionals', [])

    logging.info(f"Processing visit on {date_of_visit} with {len(diagnosis_list)} diagnoses")
    print(f"Processing visit on {date_of_visit} with {len(diagnosis_list)} diagnoses")

    # Convert medical_professionals list to a comma-separated string
    medical_professionals_str = ', '.join(medical_professionals) if medical_professionals else None
    logging.debug(f"Medical professionals: {medical_professionals_str}")
    print(f"Medical professionals: {medical_professionals_str}")

    # Determine if the visit date falls within any service period
    in_service = any(
        period['service_start_date'] <= date_of_visit_dt <= period['service_end_date']
        for period in service_periods
    )
    logging.debug(f"Visit date {date_of_visit_dt} in service period: {in_service}")
    logging.info(f"Visit date {date_of_visit_dt} in service period: {in_service}")
    print(f"Visit date {date_of_visit_dt} in service period: {in_service}")

    # Function to process a single diagnosis with its own session
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
                in_service=in_service,
                session=session
            )
            session.commit()
        except Exception as e:
            session.rollback()
            logging.error(f"Error processing diagnosis: {e}")
            print(f"Error processing diagnosis: {e}")
        finally:
            ScopedSession.remove()

    # Process all diagnoses concurrently with up to 10 worker threads
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_single_diagnosis, diag) for diag in diagnosis_list]
        # Wait for tasks to finish
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logging.error(f"Thread raised an exception: {e}")

    return {
        "date_of_visit": date_of_visit,
        "date_of_visit_dt": date_of_visit_dt
    }
