# routes/claims_routes.py
from flask import Blueprint, request, jsonify, g
from models.sql_models import Claims, Users
from database import db  # assuming you have a db instance
from datetime import datetime

claims_bp = Blueprint('claims_bp', __name__)

@claims_bp.route("/claims", methods=["GET"])
def get_claims():
    """
    GET /claims?userUUID=<user_uuid>
    Retrieves all claims for a given user.
    """
    user_uuid = request.args.get("userUUID")
    if not user_uuid:
        return jsonify({"error": "Missing userUUID query parameter"}), 400

    user = g.session.query(Users).filter_by(user_uuid=user_uuid).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    claims = g.session.query(Claims).filter_by(user_id=user.user_id).all()
    claims_list = [{
        "claim_id": claim.claim_id,
        "user_id": claim.user_id,
        "condition_id": claim.condition_id,
        "claim_name": claim.claim_name,
        "status": claim.status,
        "description": claim.description,
        "evidence_progress": claim.evidence_progress,
        "created_at": claim.created_at.isoformat(),
        "updated_at": claim.updated_at.isoformat()
    } for claim in claims]

    return jsonify(claims_list), 200

@claims_bp.route("/claims/<int:claim_id>", methods=["GET"])
def get_claim(claim_id):
    """
    GET /claims/<claim_id>?userUUID=<user_uuid>
    Retrieves details for a single claim.
    """
    # Optionally, you can check the userUUID or rely on authentication.
    claim = g.session.query(Claims).filter_by(claim_id=claim_id).first()
    if not claim:
        return jsonify({"error": "Claim not found"}), 404

    claim_data = {
        "claim_id": claim.claim_id,
        "user_id": claim.user_id,
        "condition_id": claim.condition_id,
        "claim_name": claim.claim_name,
        "status": claim.status,
        "description": claim.description,
        "evidence_progress": claim.evidence_progress,
        "created_at": claim.created_at.isoformat(),
        "updated_at": claim.updated_at.isoformat()
    }
    return jsonify(claim_data), 200

@claims_bp.route("/claims", methods=["POST"])
def create_claim():
    """
    POST /claims
    Expected JSON body:
    {
        "userUUID": "<user_uuid>",
        "claim_name": "Name of claim",
        "condition_id": <optional condition id>,
        "status": "Draft",         # optional, default 'Draft'
        "description": "Some description",
        "evidence_progress": 0     # optional, default 0
    }
    """
    data = request.get_json()
    user_uuid = data.get("userUUID")
    claim_name = data.get("claim_name")
    if not user_uuid or not claim_name:
        return jsonify({"error": "Missing required fields: userUUID and claim_name"}), 400

    user = g.session.query(Users).filter_by(user_uuid=user_uuid).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    new_claim = Claims(
        user_id=user.user_id,
        condition_id=data.get("condition_id"),
        claim_name=claim_name,
        status=data.get("status", "Draft"),
        description=data.get("description", ""),
        evidence_progress=data.get("evidence_progress", 0)
    )
    g.session.add(new_claim)
    g.session.commit()

    return jsonify({
        "claim_id": new_claim.claim_id,
        "user_id": new_claim.user_id,
        "claim_name": new_claim.claim_name,
        "status": new_claim.status
    }), 201

@claims_bp.route("/claims/<int:claim_id>", methods=["PUT"])
def update_claim(claim_id):
    """
    PUT /claims/<claim_id>
    Expected JSON body with fields to update.
    """
    data = request.get_json()
    claim = g.session.query(Claims).filter_by(claim_id=claim_id).first()
    if not claim:
        return jsonify({"error": "Claim not found"}), 404

    if "claim_name" in data:
        claim.claim_name = data["claim_name"]
    if "status" in data:
        claim.status = data["status"]
    if "description" in data:
        claim.description = data["description"]
    if "evidence_progress" in data:
        claim.evidence_progress = data["evidence_progress"]

    claim.updated_at = datetime.utcnow()
    g.session.commit()

    return jsonify({
        "claim_id": claim.claim_id,
        "user_id": claim.user_id,
        "claim_name": claim.claim_name,
        "status": claim.status
    }), 200

@claims_bp.route("/claims/<int:claim_id>", methods=["DELETE"])
def delete_claim(claim_id):
    """
    DELETE /claims/<claim_id>
    """
    claim = g.session.query(Claims).filter_by(claim_id=claim_id).first()
    if not claim:
        return jsonify({"error": "Claim not found"}), 404

    g.session.delete(claim)
    g.session.commit()

    return jsonify({"message": "Claim deleted"}), 200
