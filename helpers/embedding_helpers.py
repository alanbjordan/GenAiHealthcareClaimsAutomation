# helpers/embedding_helpers.py
import logging
from models.sql_models import Tag
#from sqlalchemy.orm import Session
from sqlalchemy import func
from pgvector.sqlalchemy import Vector
from models.sql_models import ConditionEmbedding  
#from models.sql_models import db
from helpers.llm_helpers import generate_embedding


MAX_COSINE_DISTANCE = .559


def find_top_tags(session, embedding_vector: list, top_n: int = 2):
    """
    Finds the top N tags with the smallest cosine distance to the provided embedding_vector.
    Returns a list of tuples (Tag, cosine_distance).
    """
    # Calculate cosine distance using the ORM's built-in method
    distance = Tag.embeddings.cosine_distance(embedding_vector)
    
    # Query both the Tag object and the distance, labeled as 'distance'
    similar_tags = (
        session.query(Tag, distance.label('distance'))
        .order_by(distance)
        .limit(top_n)
        .all()
    )
    return similar_tags


def process_condition_embedding(condition_id, combined_text, new_condition, session):
    """
    Generates an embedding for the given condition, stores it, and associates top tags based on similarity.

    Args:
        condition_id (int): The ID of the condition.
        combined_text (str): The text to generate the embedding from.
        new_condition (Condition): The condition instance to update.

    Returns:
        None
    """
    try:
        new_condition = session.merge(new_condition)
        # Generate the embedding vector
        embedding_vector = generate_embedding(combined_text.strip())
        logging.info(f"Generated embedding for condition_id {condition_id}")
        print(f"Generated embedding for condition_id {condition_id}")

        if embedding_vector is not None:
            # Create a new embedding instance
            new_embedding = ConditionEmbedding(
                condition_id=condition_id,
                embedding=embedding_vector
            )
            session.add(new_embedding)
            logging.info(f"Stored embedding for condition_id {condition_id}")
            print(f"Stored embedding for condition_id {condition_id}")

            # Perform similarity search to find top tags
            top_tags_with_distance = find_top_tags(session, embedding_vector, top_n=1)

            if top_tags_with_distance:
                top_tag, distance = top_tags_with_distance[0]
                if distance <= MAX_COSINE_DISTANCE:
                    new_condition.tags.append(top_tag)
                    logging.info(
                        f"Associated tag {top_tag.tag_id} with condition_id {condition_id} "
                        f"(cosine distance: {distance:.4f})"
                    )
                    print(
                        f"Associated tag {top_tag.tag_id} with condition_id {condition_id} "
                        f"(cosine distance: {distance:.4f})"
                    )
                else:
                    new_condition.is_ratable = False
                    logging.info(
                        f"Condition_id {condition_id} marked as non-ratable "
                        f"(cosine distance: {distance:.4f} exceeds threshold)"
                    )
                    print(
                        f"Condition_id {condition_id} marked as non-ratable "
                        f"(cosine distance: {distance:.4f} exceeds threshold)"
                    )
            else:
                new_condition.is_ratable = False
                logging.info(
                    f"Condition_id {condition_id} marked as non-ratable (no tags found)"
                )
                print(
                    f"Condition_id {condition_id} marked as non-ratable (no tags found)"
                )
        else:
            new_condition.is_ratable = False
            logging.error(
                f"Embedding vector is None for condition_id {condition_id}; marked as non-ratable"
            )
            print(
                f"Embedding vector is None for condition_id {condition_id}; marked as non-ratable"
            )
    except Exception as e:
        logging.error(
            f"Failed to generate or assign embedding for condition_id {condition_id}: {str(e)}"
        )
        logging.info(
            f"Failed to generate or assign embedding for condition_id {condition_id}: {str(e)}"
        )