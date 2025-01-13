# routes/marketing_routes.py

from flask import Blueprint, request, jsonify
import requests
import logging
from datetime import datetime
from models.sql_models import Waitlist
from database.session import ScopedSession
from helpers.get_location_from_ip import get_location_from_ip  # new file

marketing_bp = Blueprint('marketing_bp', __name__)

session = ScopedSession()
logger = logging.getLogger(__name__)

mailchimp_api_key = '5ce21f0070d774209e05f901f25b8dd7-us19'
mailchimp_list_id = 'f14dc49254'
mailchimp_base_url = 'https://us19.api.mailchimp.com/3.0'

@marketing_bp.route('/waitlist', methods=['POST'])
def add_to_waitlist():
    """
    Endpoint to add a user to the waitlist and sync with Mailchimp.
    """
    try:
        # Extract input
        data = request.get_json() if request.is_json else request.form
        email = data.get('email')
        name = data.get('name', '')  # Full name provided, split it
        first_name, last_name = (name.split(' ', 1) + [''])[:2]  # Split into first and last name
        veteran_status = data.get('veteranStatus', None)
        service_branch = data.get('serviceBranch', '')

        # Validate required fields
        if not email:
            logger.warning('Email is required for waitlist signup.')
            return jsonify({'error': 'Email is required'}), 400

        # Insert into database
        new_entry = Waitlist(
            email=email,
            first_name=first_name,
            last_name=last_name,
            veteran_status=veteran_status,
            service_branch=service_branch,
            signup_date=datetime.utcnow()
        )

        session.add(new_entry)
        session.commit()

        # Push to Mailchimp
        mailchimp_url = f'{mailchimp_base_url}/lists/{mailchimp_list_id}/members'
        payload = {
            'email_address': email,
            'status': 'subscribed',
            'merge_fields': {
                'FNAME': first_name,
                'LNAME': last_name
            }
        }
        headers = {
            'Authorization': f'Bearer {mailchimp_api_key}'
        }

        response = requests.post(mailchimp_url, json=payload, headers=headers)

        if response.status_code not in [200, 204]:
            logger.error(f'Mailchimp API error: {response.status_code}, {response.text}')
            return jsonify({'error': 'Failed to sync with Mailchimp. User added locally.'}), 201

        return jsonify({
            'message': 'User added to waitlist and Mailchimp successfully',
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
            'veteran_status': veteran_status,
            'service_branch': service_branch
        }), 201

    except Exception as e:
        session.rollback()
        logger.error(f'Failed to add user to waitlist: {str(e)}')
        return jsonify({'error': 'An unexpected error occurred. Please try again later.'}), 500

    finally:
        ScopedSession.remove()

