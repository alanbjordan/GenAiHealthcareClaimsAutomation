# routes/marketing_routes.py

from flask import Blueprint, request, jsonify
import logging
from datetime import datetime
from models.sql_models import Waitlist
from database.session import ScopedSession
from helpers.get_location_from_ip import get_location_from_ip  # new file

marketing_bp = Blueprint('marketing_bp', __name__)

session = ScopedSession()
logger = logging.getLogger(__name__)

@marketing_bp.route('/waitlist', methods=['POST'])
def add_to_waitlist():
    """
    Endpoint to add a user to the waitlist.
    Expected input (JSON or form-data):
    {
        "email": "user@example.com",
        "name": "User Name",               # optional
        "veteranStatus": "yes" or "no",    # optional
        "serviceBranch": "army" etc.       # optional
        "source_section": "homepage",      # optional
        "theme_mode": "dark"               # optional
    }
    If theme_mode or source_section are not provided, defaults or empty values are used.
    Location data is derived from the user's IP.
    """
    
    try:
        # Extract input
        data = request.get_json() if request.is_json else request.form
        email = data.get('email')
        name = data.get('name')
        veteran_status = data.get('veteranStatus')
        service_branch = data.get('serviceBranch', '')
        source_section = data.get('source_section', '')
        theme_mode = data.get('theme_mode', 'light')

        # Validate required fields
        if not email:
            logger.warning('Email is required for waitlist signup.')
            return jsonify({'error': 'Email is required'}), 400

        # Detect IP
        ip_address = request.remote_addr or '127.0.0.1'

        # Get location data from IP
        location_data = get_location_from_ip(ip_address)
        country = location_data.get('country')
        region = location_data.get('region')
        city = location_data.get('city')
        zip_code = location_data.get('zip_code')

        # Insert into database
        new_entry = Waitlist(
            email=email,
            name=name,
            veteran_status=veteran_status,
            service_branch=service_branch,
            signup_date=datetime.utcnow(),
            theme_mode=theme_mode,
            country=country,
            region=region,
            city=city,
            zip_code=zip_code
        )

        session.add(new_entry)
        session.commit()

        return jsonify({
            'message': 'User added to waitlist successfully',
            'email': email,
            'name': name,
            'veteranStatus': veteran_status,
            'serviceBranch': service_branch,
            'theme_mode': theme_mode,
            'source_section': source_section,
            'location': {
                'country': country,
                'region': region,
                'city': city,
                'zip_code': zip_code
            }
        }), 201

    except Exception as e:
        session.rollback()
        logger.error(f'Failed to add user to waitlist: {str(e)}')
        return jsonify({'error': 'An unexpected error occurred. Please try again later.'}), 500

    finally:
        ScopedSession.remove()
