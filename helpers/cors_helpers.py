from flask import jsonify, request
from functools import wraps
from config import Config

def handle_dynamic_cors_preflight():
    """
    Handles dynamic CORS preflight requests by returning appropriate headers
    based on the current route's allowed methods. Enforces Authorization header.
    """
    # Check for Authorization header
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith("Bearer "):
        response = jsonify({"error": "Authorization header required for preflight"})
        response.headers["Access-Control-Allow-Origin"] = Config.CORS_ORIGINS
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response, 401  # Unauthorized

    # Get allowed methods for the current route
    allowed_methods = ', '.join(request.url_rule.methods)
    
    # Create preflight response with appropriate CORS headers
    response = jsonify({"message": "CORS preflight handled"})
    response.headers["Access-Control-Allow-Origin"] = Config.CORS_ORIGINS
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, userUUID"
    response.headers["Access-Control-Allow-Methods"] = allowed_methods
    response.headers["Access-Control-Allow-Credentials"] = "true"
    return response, 200


def cors_preflight(func):
    """
    A decorator to handle generic CORS preflight requests before invoking the main route logic.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if request.method == 'OPTIONS':
            return handle_dynamic_cors_preflight()
        return func(*args, **kwargs)
    return wrapper

def pre_authorized_cors_preflight(func):
    """
    A decorator to handle CORS preflight requests for public routes.
    Does not enforce Authorization.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if request.method == 'OPTIONS':
            # Get allowed methods for the current route
            allowed_methods = ', '.join(request.url_rule.methods)

            # Create response with appropriate CORS headers
            response = jsonify({"message": "CORS preflight handled"})
            response.headers["Access-Control-Allow-Origin"] = Config.CORS_ORIGINS
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, userUUID"
            response.headers["Access-Control-Allow-Methods"] = allowed_methods
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response, 200
        
        # Proceed with the actual request logic for non-OPTIONS methods
        return func(*args, **kwargs)
    return wrapper

