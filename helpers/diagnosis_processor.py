# diagnosis_processor.py is a helper function to process a single diagnosis and save it to the database.

import logging
from models.sql_models import Conditions

def process_diagnosis(diagnosis, user_id, file_id, page_number, date_of_visit, medical_professionals_str, in_service, session):
    """
    Processes a single diagnosis and saves it to the database.
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

        return {
            "condition_name": condition_name,
            "findings": findings,
            "condition_id": condition_id,
            "new_condition": new_condition
        }
    except Exception as e:
        logging.error(f"Error processing diagnosis on page {page_number}: {e}")
        print(f"Error processing diagnosis on page {page_number}: {e}")
        session.rollback()
        return None
