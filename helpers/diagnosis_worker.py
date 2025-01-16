import logging
from helpers.diagnosis_processor import process_diagnosis
from helpers.embedding_helpers import process_condition_embedding 

def worker_process_diagnosis(diagnosis, user_id, file_id, page_number, date_of_visit, medical_professionals_str, in_service, session):
    """
    Worker function to process a single diagnosis and handle embedding.
    """
    try:
        result = process_diagnosis(
            diagnosis=diagnosis,
            user_id=user_id,
            file_id=file_id,
            page_number=page_number,
            date_of_visit=date_of_visit,
            medical_professionals_str=medical_professionals_str,
            in_service=in_service,
            session=session
        )

        if result:
            condition_name = result["condition_name"]
            findings = result["findings"]
            condition_id = result["condition_id"]
            new_condition = result["new_condition"]

            combined_text = f"""
            Condition Name: {condition_name}, Findings: {findings}
            """

            logging.debug(f"Combined text for embedding: {combined_text.strip()}")
            logging.info(f"Combined text for embedding: {combined_text.strip()}")

            try:
                process_condition_embedding(condition_id, combined_text, new_condition, session)
            except Exception as e:
                logging.error(
                    f"Failed to generate or assign embedding for condition_id {condition_id}: {str(e)}"
                )
                print(
                    f"Failed to generate or assign embedding for condition_id {condition_id}: {str(e)}"
                )
                new_condition.is_ratable = False
                session.add(new_condition)
                session.commit()
    except Exception as e:
        logging.error(f"Unexpected error in worker: {e}")
    finally:
        session.commit()
