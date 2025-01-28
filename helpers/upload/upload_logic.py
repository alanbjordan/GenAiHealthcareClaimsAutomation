# helpers/upload_logic.py

import os
import tempfile
import logging
from PyPDF2 import PdfReader
from werkzeug.utils import secure_filename

def can_user_afford_files(user, file_paths, cost_per_page=1000):
    """
    Checks if a user has enough credits to process all pages from the given file paths.
    Returns a tuple:
       (bool is_affordable, int total_pages, int total_required_credits)

    - Each path should point to a saved file on disk.
    - We open the file from disk to count pages.
    """
    total_pages = 0

    for path in file_paths:
        if not os.path.exists(path):
            raise ValueError(f"File not found: {path}")

        file_ext = os.path.splitext(path)[1].lower()
        pages_for_this_file = 0

        try:
            if file_ext == '.pdf':
                reader = PdfReader(path)
                pages_for_this_file = len(reader.pages)
            elif file_ext in ['.jpg', '.jpeg', '.png']:
                pages_for_this_file = 1
            elif file_ext in ['.mp4', '.mov', '.mp3']:
                pages_for_this_file = 1
            else:
                # Unknown type => decide your logic
                pages_for_this_file = 1
        except Exception as e:
            logging.error(f"Failed to determine pages for {path}: {e}")
            raise

        total_pages += pages_for_this_file

    total_required = total_pages * cost_per_page
    is_affordable = (user.credits_remaining >= total_required)

    return is_affordable, total_pages, total_required
