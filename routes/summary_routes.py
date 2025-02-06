import logging
from config import Config
from flask import Blueprint, request, jsonify, g
from helpers.azure_helpers import (
    download_blob_with_credentials,  # Make sure this exists in azure_helpers.py
    upload_to_azure_blob,
    generate_sas_url,
    extract_blob_name
)
from helpers.llm_helpers import generate_claim_response, generate_cheat_sheet_response
from models.sql_models import Users, Conditions, Tag, condition_tags, File
import fitz  # PyMuPDF
from io import BytesIO
from datetime import datetime
import os
from helpers.decision_helper import summarize_decision
from openai import OpenAI

logger = logging.getLogger(__name__)

# Set up the OpenAI API key to interact with the GPT models
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
if not client:
    raise ValueError("Please set the VA_AUTOMATION_API_KEY environment variable.")

summary_bp = Blueprint('summary_bp', __name__)

###############################################################################
# generate_claim_summary
###############################################################################
@summary_bp.route('/generate_claim_summary', methods=['POST'])
def generate_claim_summary():
    """Generates a 'Statement in Support of Claim' PDF based on selected conditions."""
    logger.debug("Entered generate_claim_summary endpoint.")
    try:
        request_data = request.json
        user_uuid = request_data.get('userUUID')
        tags = request_data.get('tags')  # [{"tag_id":..., "condition_ids":[...]}]

        if not user_uuid:
            logger.warning("User UUID missing from request.")
            return jsonify({"error": "User UUID is required"}), 400

        logger.info(f"Processing claim summary for userUUID: %s", user_uuid)

        # Use the global session
        session = g.session

        # Fetch user by user_uuid
        user = session.query(Users).filter_by(user_uuid=user_uuid).first()
        if not user:
            logger.warning("No user found for userUUID: %s", user_uuid)
            return jsonify({"error": "User not found"}), 404

        # --- FIX for DetachedInstanceError: store user_id in a local variable ---
        the_user_id = user.user_id
        logger.debug("Found user with user_id=%s", the_user_id)

        # Flatten condition_ids and tag_ids
        condition_ids = [cid for tag in tags for cid in tag['condition_ids']]
        tag_ids = [tag['tag_id'] for tag in tags]

        logger.debug("condition_ids=%s, tag_ids=%s", condition_ids, tag_ids)

        # Query conditions
        conditions = (
            session.query(Conditions, Tag)
            .join(condition_tags, Conditions.condition_id == condition_tags.c.condition_id)
            .join(Tag, condition_tags.c.tag_id == Tag.tag_id)
            .filter(
                Conditions.user_id == the_user_id,
                Tag.tag_id.in_(tag_ids),
                Conditions.condition_id.in_(condition_ids)
            )
            .all()
        )
        logger.info("Retrieved %d condition-tag pairs from the DB.", len(conditions))

        # Group by disability_name
        results = {}
        for cond, tag in conditions:
            disability_name = tag.disability_name
            condition_data = {
                "condition_id": cond.condition_id,
                "file_id": cond.file_id,
                "condition_name": cond.condition_name,
                "date_of_visit": cond.date_of_visit,
                "medical_professionals": cond.medical_professionals,
                "treatments": cond.treatments,
                "findings": cond.findings,
                "comments": cond.comments,
                "in_service": cond.in_service,
                "code": tag.code
            }
            results.setdefault(disability_name, []).append(condition_data)

        logger.debug("Grouped results: %s", results)

        # Generate statement content via LLM
        logger.info("Generating claim response with LLM...")
        claim_summary = generate_claim_response(
            the_user_id,      # use the integer ID
            str(results)      # pass the text content
        )
        logger.debug("LLM raw response:\n%s", claim_summary)

        # Remove newline chars
        claim_summary = claim_summary.replace('\n', ' ')
        logger.debug("Normalized claim_summary by removing newlines.")

        # Download base PDF with credentials
        # If your PDF is stored in the container as exactly "VBA-21-4138-ARE.pdf":
        blob_base_pdf = "VBA-21-4138-ARE.pdf"
        logger.info("Downloading base PDF from Azure container: %s", blob_base_pdf)
        input_pdf_content = download_blob_with_credentials(blob_base_pdf)

        if input_pdf_content is None:
            logger.error("Failed to download the base PDF from Azure (credentials-based).")
            return jsonify({"error": "Failed to download PDF from Azure"}), 500

        logger.debug("Downloaded PDF. Size in bytes: %d", len(input_pdf_content))

        # Load and modify PDF
        pdf_stream = BytesIO(input_pdf_content)
        pdf = fitz.open(stream=pdf_stream, filetype="pdf")
        logger.debug("Loaded PDF with %d pages.", len(pdf))

        page = pdf[0]

        # Insert text in the PDF
        x, y = 32, 460
        max_width = 550
        font_size = 10
        line_spacing = int(font_size * 1.5)
        max_height = 260
        logger.info("Wrapping text onto PDF form fields.")

        try:
            font = fitz.Font("helv")
        except Exception as font_exc:
            logger.warning("Could not load font 'helv': %s. Using default font.", font_exc)
            font = None

        wrap_text(page, claim_summary, x, y, max_width, max_height,
                  font_size, line_spacing, font, pdf)
        logger.debug("Text successfully wrapped onto the PDF.")

        # Save modified PDF
        output_pdf_stream = BytesIO()
        pdf.save(output_pdf_stream)
        pdf.close()
        output_pdf_stream.seek(0)
        logger.debug("PDF modifications complete. Byte size: %d", len(output_pdf_stream.getvalue()))

        # Upload final PDF to Azure
        blob_name = f"{user_uuid}/Unclassified/VBA-21-4138-ARE-{datetime.now().date()}.pdf"
        logger.info("Uploading final PDF to Azure: %s", blob_name)
        uploaded_blob_url = upload_to_azure_blob(
            blob_name,
            None,
            output_pdf_stream.getvalue(),
            content_type="application/pdf"
        )
        if uploaded_blob_url is None:
            logger.error("Failed to upload PDF to Azure.")
            return jsonify({"error": "Failed to upload PDF to Azure"}), 500

        logger.debug("Uploaded PDF to Azure. Blob URL: %s", uploaded_blob_url)

        # Insert file metadata in database
        logger.info("Inserting new file record into DB.")
        new_file = File(
            user_id=the_user_id,  # use 'the_user_id' instead of user.user_id (detached issues)
            file_name=f"Statement_in_Support_of_Claim-{datetime.utcnow()}.pdf",
            file_type='pdf',
            file_url=uploaded_blob_url,
            file_date=datetime.now().date(),
            uploaded_at=datetime.utcnow(),
            file_category='VA Forms'
        )
        session.add(new_file)
        session.flush()  # get file_id
        file_id = new_file.file_id

        logger.info("New file record (file_id=%s) inserted.", file_id)
        logger.debug("Returning success response to client.")

        return jsonify({
            "message": "Summary PDF generated and uploaded to Azure",
            "file_id": file_id
        }), 200

    except Exception as e:
        logger.exception("Exception occurred in generate_claim_summary:")
        return jsonify({"error": "Failed to process request"}), 500


def wrap_text(page, text, x, y, max_width, max_height,
              font_size, line_spacing, font, pdf):
    """Utility function for text wrapping across multiple PDF pages."""
    logger = logging.getLogger(__name__)
    logger.debug("Starting wrap_text utility.")
    cursor_y = y
    words = text.split(' ')
    line = ""

    current_page = page
    current_page_num = 0
    subsequent_page_y = 100

    for word in words:
        test_line = f"{line} {word}".strip()
        if font:
            line_length = font.text_length(test_line, fontsize=font_size)
        else:
            line_length = page.get_textlength(test_line, fontsize=font_size)

        if line_length <= max_width:
            line = test_line
        else:
            if (cursor_y + line_spacing) > (y + max_height):
                # Move to next page if needed
                current_page_num += 1
                if current_page_num < len(pdf):
                    current_page = pdf[current_page_num]
                else:
                    current_page = pdf.new_page()
                cursor_y = subsequent_page_y
                logger.debug("Creating new page #%d at y=%s.", current_page_num, cursor_y)

            current_page.insert_text(
                (x, cursor_y),
                line,
                fontsize=font_size,
                fontname="helv" if font else "Times-Roman",
                color=(0, 0, 0)
            )
            cursor_y += line_spacing
            line = word

    if line:  # Print the last line
        if (cursor_y + line_spacing) > (y + max_height):
            current_page_num += 1
            if current_page_num < len(pdf):
                current_page = pdf[current_page_num]
            else:
                current_page = pdf.new_page()
            cursor_y = subsequent_page_y
            logger.debug("Moving final line to new page #%d at y=%s.", current_page_num, cursor_y)

        current_page.insert_text(
            (x, cursor_y),
            line,
            fontsize=font_size,
            fontname="helv" if font else "Times-Roman",
            color=(0, 0, 0)
        )
    logger.debug("Completed wrap_text utility.")




###############################################################################
# generate_cheat_sheet
###############################################################################
@summary_bp.route('/generate_cheat_sheet', methods=['POST', 'OPTIONS'])
def generate_cheat_sheet():
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        response = jsonify({"message": "CORS preflight successful"})
        response.headers.update({
            "Access-Control-Allow-Origin": Config.CORS_ORIGINS,
            "Access-Control-Allow-Headers": "Content-Type, Authorization, user-uuid",
            "Access-Control-Allow-Methods": "GET, PUT, POST, DELETE, OPTIONS",
            "Access-Control-Allow-Credentials": "true"
        })
        return response, 200

    try:
        request_data = request.json
        user_uuid = request_data.get('userUUID')
        tags = request_data.get('tags')

        if not user_uuid:
            return jsonify({"error": "User UUID is required"}), 400

        print(f"Received POST /generate_cheat_sheet request with userUUID: {user_uuid}")

        session = g.session

        user = session.query(Users).filter_by(user_uuid=user_uuid).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        condition_ids = [cid for tag in tags for cid in tag['condition_ids']]
        tag_ids = [tag['tag_id'] for tag in tags]

        conditions = (session.query(Conditions, Tag)
                              .join(condition_tags, Conditions.condition_id == condition_tags.c.condition_id)
                              .join(Tag, condition_tags.c.tag_id == Tag.tag_id)
                              .filter(Conditions.user_id == user.user_id,
                                      Tag.tag_id.in_(tag_ids),
                                      Conditions.condition_id.in_(condition_ids))
                              .all())

        results = {}
        for cond, tag in conditions:
            disability_name = tag.disability_name
            condition_data = {
                "condition_id": cond.condition_id,
                "file_id": cond.file_id,
                "condition_name": cond.condition_name,
                "date_of_visit": cond.date_of_visit,
                "medical_professionals": cond.medical_professionals,
                "treatments": cond.treatments,
                "findings": cond.findings,
                "comments": cond.comments,
                "in_service": cond.in_service,
                "code": tag.code
            }
            results.setdefault(disability_name, []).append(condition_data)

        cheat_sheet = generate_cheat_sheet_response(str(results))
        print(cheat_sheet)

        # The global teardown_request will handle commit/rollback
        return cheat_sheet, 200

    except Exception as e:
        print("Error in generating cheat sheet:", e)
        return jsonify({"error": "Failed to process request"}), 500


###############################################################################
# generate_nexus_summary (NEW)
###############################################################################
@summary_bp.route('/generate_nexus_summary', methods=['POST', 'OPTIONS'])
def generate_nexus_summary():
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        response = jsonify({"message": "CORS preflight successful"})
        response.headers.update({
            "Access-Control-Allow-Origin": Config.CORS_ORIGINS,
            "Access-Control-Allow-Headers": "Content-Type, Authorization, user-uuid",
            "Access-Control-Allow-Methods": "GET, PUT, POST, DELETE, OPTIONS",
            "Access-Control-Allow-Credentials": "true"
        })
        return response, 200

    try:
        data = request.json
        user_uuid = data.get('userUUID')
        nexus_tags_id = data.get('nexus_tags_id')
        conditions_data = data.get('conditions', []) 

        if not user_uuid or not nexus_tags_id:
            return jsonify({"error": "userUUID and nexus_tags_id are required"}), 400

        session = g.session

        # Validate the user
        user = session.query(Users).filter_by(user_uuid=user_uuid).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Optional: Confirm these conditions belong to this user
        condition_ids = [c["condition_id"] for c in conditions_data]
        db_conditions = (session.query(Conditions)
                                 .filter(Conditions.user_id == user.user_id,
                                         Conditions.condition_id.in_(condition_ids))
                                 .all())
        # You can compare lengths or data if you want to ensure all exist for the user

        # Generate summary text with your LLM helper
        claim_summary = generate_claim_response(str(conditions_data))

        # [Optional] Insert a row into your new "NexusSummary" table
        # e.g.:
        # new_summary = NexusSummary(
        #     nexus_tags_id=nexus_tags_id,
        #     summary_text=claim_summary,
        #     condition_ids=condition_ids,
        #     needs_update=False
        # )
        # session.add(new_summary)
        # session.flush()

        # Return the summary or do more PDF logic if desired
        return jsonify({"summary": claim_summary}), 200

    except Exception as e:
        print("Error in generating nexus summary:", e)
        return jsonify({"error": "Failed to process"}), 500

