# summary_routes.py

from config import Config
from flask import Blueprint, request, jsonify
from helpers.azure_helpers import download_public_file_from_azure, upload_to_azure_blob, generate_sas_url, extract_blob_name
from helpers.llm_helpers import generate_claim_response, generate_cheat_sheet_response
from models.sql_models import Users, Conditions, Tag, condition_tags, File
import fitz  # PyMuPDF
from io import BytesIO
import time
from datetime import datetime
import os
from database.session import ScopedSession

summary_bp = Blueprint('summary_bp', __name__)
session = ScopedSession()

@summary_bp.route('/generate_claim_summary', methods=['POST', 'OPTIONS'])
def generate_claim_summary():
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
        # Process POST request
        request_data = request.json
        user_uuid = request_data.get('userUUID')
        tags = request_data.get('tags')  # Expected: [{"tag_id": ..., "condition_ids": [...]}]

        if not user_uuid:
            return jsonify({"error": "User UUID is required"}), 400

        print(f"Received POST /generate_claim_summary request with userUUID: {user_uuid}")

        # Fetch user by user_uuid
        user = session.query(Users).filter_by(user_uuid=user_uuid).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Flatten condition_ids and tag_ids
        condition_ids = [condition_id for tag in tags for condition_id in tag['condition_ids']]
        tag_ids = [tag['tag_id'] for tag in tags]

        # Query conditions filtered by user_id and the given tags and condition_ids
        conditions = session.query(Conditions, Tag).join(
            condition_tags, Conditions.condition_id == condition_tags.c.condition_id
        ).join(
            Tag, condition_tags.c.tag_id == Tag.tag_id
        ).filter(
            Conditions.user_id == user.user_id,
            Tag.tag_id.in_(tag_ids),
            Conditions.condition_id.in_(condition_ids)
        ).all()

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

        # Generate summary via LLM
        claim_summary = generate_claim_response(str(results))
        print(claim_summary)

        # Remove newline chars
        claim_summary = claim_summary.replace('\n', ' ')

        # Download the base PDF from a public URL
        input_pdf_url = "https://vetdoxstorage.blob.core.windows.net/user-uploads/VBA-21-4138-ARE.pdf?sp=r..."
        input_pdf_content = download_public_file_from_azure(input_pdf_url)
        if input_pdf_content is None:
            return jsonify({"error": "Failed to download PDF from Azure"}), 500

        # Load the PDF and overlay text
        pdf_stream = BytesIO(input_pdf_content)
        pdf = fitz.open("pdf", pdf_stream)
        page = pdf[0]

        # Insert text in the PDF
        x, y = 32, 460
        max_width = 550
        font_size = 10
        line_spacing = int(font_size * 1.5)
        font = fitz.Font("helv")
        max_height = 260

        wrap_text(page, claim_summary, x, y, max_width, max_height, font_size, line_spacing, font, pdf)

        # Save modified PDF
        output_pdf_stream = BytesIO()
        pdf.save(output_pdf_stream)
        pdf.close()
        output_pdf_stream.seek(0)

        # Upload in-memory PDF
        blob_name = f"{user_uuid}/Unclassified/VBA-21-4138-ARE-{datetime.now().date()}.pdf"
        uploaded_blob_url = upload_to_azure_blob(blob_name, None, output_pdf_stream.getvalue(), content_type="application/pdf")
        
        if uploaded_blob_url is None:
            return jsonify({"error": "Failed to upload PDF to Azure"}), 500

        print("Generated SAS URL for the document:", uploaded_blob_url)

        # Insert file metadata in database
        new_file = File(
            user_id=user.user_id,
            file_name=f'Statement_in_Support_of_Claim-{datetime.utcnow()}.pdf',
            file_type='pdf',
            file_url=uploaded_blob_url,
            file_date=datetime.now().date(),
            uploaded_at=datetime.utcnow(),
            file_category='VA Forms'
        )

        session.add(new_file)
        session.flush()  # get file_id
        file_id = new_file.file_id
        print(f"Inserted new file record with file_id={file_id}")
        print("Stored url in Database")
        session.commit()

        return jsonify({"message": "Summary PDF generated and uploaded to Azure", "file_id": file_id}), 200

    except Exception as e:
        print("Error in generating summary:", e)
        return jsonify({"error": "Failed to process request"}), 500

def wrap_text(page, text, x, y, max_width, max_height, font_size, line_spacing, font, pdf):
    cursor_y = y
    words = text.split(' ')
    line = ""

    current_page = page
    current_page_num = 0

    first_page_y = y
    subsequent_page_y = 100

    for word in words:
        test_line = f"{line} {word}".strip()
        line_length = font.text_length(test_line, fontsize=font_size)
        
        if line_length <= max_width:
            line = test_line
        else:
            if cursor_y + line_spacing > y + max_height:
                # Move to next page if needed
                current_page_num += 1
                if current_page_num < len(pdf):
                    current_page = pdf[current_page_num]
                else:
                    current_page = pdf.new_page()
                cursor_y = subsequent_page_y

            current_page.insert_text((x, cursor_y), line, fontsize=font_size, fontname="helv", color=(0, 0, 0))
            cursor_y += line_spacing
            line = word

    if line:
        if cursor_y + line_spacing > y + max_height:
            # Next page if needed
            current_page_num += 1
            if current_page_num < len(pdf):
                current_page = pdf[current_page_num]
            else:
                current_page = pdf.new_page()
            cursor_y = subsequent_page_y

        current_page.insert_text((x, cursor_y), line, fontsize=font_size, fontname="helv", color=(0, 0, 0))

@summary_bp.route('/generate_cheat_sheet', methods=['POST', 'OPTIONS'])
def generate_cheat_sheet():
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

        user = session.query(Users).filter_by(user_uuid=user_uuid).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        condition_ids = [condition_id for tag in tags for condition_id in tag['condition_ids']]
        tag_ids = [tag['tag_id'] for tag in tags]

        conditions = session.query(Conditions, Tag).join(
            condition_tags, Conditions.condition_id == condition_tags.c.condition_id
        ).join(
            Tag, condition_tags.c.tag_id == Tag.tag_id
        ).filter(
            Conditions.user_id == user.user_id,
            Tag.tag_id.in_(tag_ids),
            Conditions.condition_id.in_(condition_ids)
        ).all()

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

        return cheat_sheet, 200

    except Exception as e:
        print("Error in generating cheat sheet:", e)
        return jsonify({"error": "Failed to process request"}), 500
