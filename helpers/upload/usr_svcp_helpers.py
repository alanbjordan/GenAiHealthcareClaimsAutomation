# helpers/upload/usr_svcp_helpers.py
from flask import jsonify, g
from models.sql_models import Users, ServicePeriod
import logging


def get_user_and_service_periods(user_uuid):
    """
    Retrieve the user and their associated service periods from the database.
    Serializes service periods for JSON compatibility.
    
    :param user_uuid: UUID of the user
    :return: tuple (user, serialized_service_periods) or (error_response, None)
    """
    logging.info(f"Looking up user with UUID: {user_uuid}")

    # Lookup the user by UUID
    user = g.session.query(Users).filter_by(user_uuid=user_uuid).first()
    if not user:
        error_message = f"Invalid user UUID: {user_uuid}"
        logging.error(error_message)
        return jsonify({"error": error_message}), None

    # Retrieve service periods
    service_periods = g.session.query(ServicePeriod).filter_by(user_id=user.user_id).all()

    # Serialize the service periods to dictionaries
    serialized_service_periods = [
        {
            "service_period_id": sp.service_period_id,
            "user_id": sp.user_id,
            "branch_of_service": sp.branch_of_service,
            "service_start_date": sp.service_start_date,  # keep as date
            "service_end_date": sp.service_end_date,      # keep as date
        }
        for sp in service_periods
    ]


    # Log warning if no service periods are found
    if not service_periods:
        logging.warning(f'No service periods found for user {user_uuid}')
        print(f'No service periods found for user {user_uuid}')

    return (user, serialized_service_periods), None
