from sqlalchemy import func, case
from datetime import datetime
from models.sql_models import *

def discover_nexus_tags(session, user_id):
    """
    For a given user:
    1. Identify tag_ids that have at least one in-service condition (in_service=TRUE)
       and at least one current condition (in_service=FALSE).
    2. Insert a new row into nexus_tags for any tag that doesn't already have an active entry
       for that user.
    """

    # 1) Find all tag_ids for this user that have both T & F conditions
    tags_with_tf = (
        session.query(condition_tags.c.tag_id)
        .join(Conditions, condition_tags.c.condition_id == Conditions.condition_id)
        .filter(Conditions.user_id == user_id)  # Only conditions for this user
        .group_by(condition_tags.c.tag_id)
        .having(
            func.count(case((Conditions.in_service == True, 1), else_=None)) > 0
        )
        .having(
            func.count(case((Conditions.in_service == False, 1), else_=None)) > 0
        )
        .all()
    )

    # Convert the rows to a simple set of tag_ids
    tags_with_tf_ids = {row.tag_id for row in tags_with_tf}

    # 2) Find which tags are already "active" for this user in nexus_tags (revoked_at is NULL)
    active_tag_ids = set(
        row[0] for row in (
            session.query(NexusTags.tag_id)
            .filter(NexusTags.revoked_at.is_(None))
            .filter(NexusTags.user_id == user_id)
            .all()
        )
    )

    # 3) Insert new nexus_tags rows for newly qualified tags
    newly_qualified = tags_with_tf_ids - active_tag_ids
    for t_id in newly_qualified:
        nexus = NexusTags(
            tag_id=t_id,
            user_id=user_id,  # Include the user info here
            # discovered_at will default to NOW() if set in your model
        )
        session.add(nexus)

    session.commit()


def revoke_nexus_tags_if_invalid(session, user_id):
    still_valid_subq = (
        session.query(condition_tags.c.tag_id)
        .join(Conditions, condition_tags.c.condition_id == Conditions.condition_id)
        .filter(Conditions.user_id == user_id)  # only for this user
        .group_by(condition_tags.c.tag_id)
        .having(
            func.count(case((Conditions.in_service == True, 1), else_=None)) > 0
        )
        .having(
            func.count(case((Conditions.in_service == False, 1), else_=None)) > 0
        )
        .subquery()
    )

    to_revoke = (
        session.query(NexusTags)
        .filter(NexusTags.user_id == user_id)         # only tags for this user
        .filter(NexusTags.revoked_at.is_(None))
        .filter(~NexusTags.tag_id.in_(still_valid_subq))
        .all()
    )

    now_time = datetime.utcnow()
    for nexus_row in to_revoke:
        nexus_row.revoked_at = now_time

    session.commit()