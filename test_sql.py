from sqlalchemy import create_engine, text

# Database connection
DATABASE_URL = 'postgres+psycopg2://u5442k5srljlin:pa36f82db4877e9b1c60d150ce786909119bd1ef04da1ea034443a6972584a6ed@c4c161t4pf58h3.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/d7fdovei4vd90b'

engine = create_engine(DATABASE_URL)

# Query to get semantic matches for each condition with in_service = FALSE
query = text("""
    WITH target_conditions AS (
        SELECT condition_id, condition_name, date_of_visit, embedding
        FROM condition_embeddings e
        JOIN conditions c ON e.condition_id = c.condition_id
        WHERE c.in_service = FALSE
    )
    SELECT t.condition_id AS target_id, t.condition_name AS target_name, t.date_of_visit AS target_date,
           c.condition_id AS match_id, c.condition_name AS match_name, c.date_of_visit AS match_date,
           e.embedding <=> t.embedding AS similarity
    FROM condition_embeddings e
    JOIN conditions c ON e.condition_id = c.condition_id
    JOIN target_conditions t ON TRUE
    WHERE c.in_service = TRUE
    AND (e.embedding <=> t.embedding) < 0.4  -- Adjust threshold as needed
    ORDER BY t.condition_id, similarity ASC
    LIMIT 5;
""")

try:
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        result = conn.execute("SELECT 1")
        print(result.fetchall())  # Expected output: [(1,)]
    print("✅ Connection successful!")

    # Format output into sections
    output_text = ""

    # Process results and group by target condition
    current_condition_id = None
    for row in results:
        target_id, target_name, target_date, match_id, match_name, match_date, similarity = row

        # Add section header for each new target condition
        if target_id != current_condition_id:
            if current_condition_id is not None:
                output_text += "\n"  # Space between sections
            output_text += f"===== Condition ID: {target_id} - {target_name} (Date: {target_date}) =====\n"
            current_condition_id = target_id

        # Add matched conditions
        output_text += f"- Matched: {match_name} (ID: {match_id}, Date: {match_date}, Similarity: {similarity:.4f})\n"

    # Write results to output.txt
    with open("output.txt", "w") as f:
        f.write(output_text)

except Exception as e:
    print("❌ Connection failed:", e)
    print("Results saved to output.txt ✅")
