# helpers/upload_logic.py

import os
import tempfile
import logging
from PyPDF2 import PdfReader
from werkzeug.utils import secure_filename

def can_user_afford_files(user, uploaded_files, cost_per_page=1000):
    """
    Checks if a user has enough credits to process all pages in the uploaded files.
    Returns a tuple:
       (bool is_affordable, int total_pages, int total_required_credits)

    - Saves each file to a temp location (just to count pages).
    - For PDF files, we count len(pdf_reader.pages).
    - For images, we assume 1 page each (example).
    - For videos, audio, etc., either skip them or treat them as 1 page (your choice).
    """
    total_pages = 0

    for file in uploaded_files:
        if not file or file.filename == '':
            raise ValueError("No selected file in the upload")

        file_ext = os.path.splitext(file.filename)[1].lower()

        temp_path = os.path.join(tempfile.gettempdir(), secure_filename(file.filename))
        file.save(temp_path)

        pages_for_this_file = 0

        try:
            if file_ext == '.pdf':
                reader = PdfReader(temp_path)
                pages_for_this_file = len(reader.pages)
            elif file_ext in ['.jpg', '.jpeg', '.png']:
                pages_for_this_file = 1
            elif file_ext in ['.mp4', '.mov', '.mp3']:
                # If you want each video or audio file to count as 1 page:
                pages_for_this_file = 1
            else:
                # Unknown type => decide your logic
                pages_for_this_file = 1
        except Exception as e:
            logging.error(f"Failed to determine pages for {file.filename}: {e}")
            # You could raise or ignore. We'll raise here.
            raise

        total_pages += pages_for_this_file

        # Optionally remove the temp file as soon as you’re done counting
        try:
            os.remove(temp_path)
        except OSError as ex:
            logging.warning(f"Failed to remove temp file {temp_path}: {ex}")

    total_required = total_pages * cost_per_page
    is_affordable = (user.credits_remaining >= total_required)

    return is_affordable, total_pages, total_required
