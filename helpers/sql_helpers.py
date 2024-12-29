from sqlalchemy import func, case
from datetime import datetime
from models.sql_models import *


def discover_nexus_tags(session):
    """
    1. Identify tag_ids that have at least one in-service condition (in_service=TRUE)
       and at least one current condition (in_service=FALSE).
    2. Insert a new row into nexus_tags for any tag that doesn't already have an active entry.
    """
    # Subquery: find tag_ids with both T & F conditions
    tags_with_tf = (
        session.query(condition_tags.c.tag_id)
        .join(Conditions, condition_tags.c.condition_id == Conditions.condition_id)
        .group_by(condition_tags.c.tag_id)
        .having(
            func.count(
                case((Conditions.in_service == True, 1), else_=None)
            ) > 0
        )
        .having(
            func.count(
                case((Conditions.in_service == False, 1), else_=None)
            ) > 0
        )
        .all()
    )

    tags_with_tf_ids = {row.tag_id for row in tags_with_tf}

    # Find which tags are already "active" in nexus_tags (revoked_at is NULL)
    active_tag_ids = set(
        session.query(NexusTags.tag_id)
        .filter(NexusTags.revoked_at.is_(None))
        .all()
    )

    # Insert new nexus_tags rows for tags that just qualified
    newly_qualified = tags_with_tf_ids - active_tag_ids
    for t_id in newly_qualified:
        nexus = NexusTags(tag_id=t_id)  # discovered_at will default to NOW()
        session.add(nexus)

    session.commit()


def revoke_nexus_tags_if_invalid(session):
    still_valid_subq = (
        session.query(condition_tags.c.tag_id)
        .join(Conditions, condition_tags.c.condition_id == Conditions.condition_id)
        .group_by(condition_tags.c.tag_id)
        # Remove brackets around (Conditions.in_service == True, 1)
        .having(
            func.count(
                case((Conditions.in_service == True, 1), else_=None)
            ) > 0
        )
        .having(
            func.count(
                case((Conditions.in_service == False, 1), else_=None)
            ) > 0
        )
        .subquery()
    )

    to_revoke = (
        session.query(NexusTags)
        .filter(NexusTags.revoked_at.is_(None))
        .filter(~NexusTags.tag_id.in_(still_valid_subq))
        .all()
    )

    now_time = datetime.utcnow()
    for row in to_revoke:
        row.revoked_at = now_time

    session.commit()

