# helpers/upload/usr_svcp_helpers.py
from flask import jsonify, g
from models.sql_models import Users, ServicePeriod
import logging


def get_user_and_service_periods(user_uuid):
    """
    Retrieve the user and their associated service periods from the database.
    
    :param user_uuid: UUID of the user
    :return: tuple (user, service_periods) or (error_response, None)
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
    if not service_periods:
        logging.warning(f'No service periods found for user {user_uuid}')
        print(f'No service periods found for user {user_uuid}')
        # Service periods are not mandatory, so this is informational.

    return (user, service_periods), None
