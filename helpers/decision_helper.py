import os
from openai import OpenAI
from pydantic import ValidationError
from dotenv import load_dotenv
from models.decision_models import BvaDecisionStructuredSummary
from helpers.llm_wrappers import call_openai_chat_parse
from decimal import Decimal 

# Load environment variables from a .env file
load_dotenv()

# Set up the OpenAI API key to interact with the GPT models
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),  # Ensure this is set correctly
)
if not client:
    raise ValueError("Please set the VA_AUTOMATION_API_KEY environment variable.")

def summarize_decision(document_text: str, user_id: int) -> BvaDecisionStructuredSummary:
    """
    Summarize a BVA decision text into a BvaDecisionStructuredSummary,
    ensuring all fields are present by using the Pydantic model.
    Logs usage data and updates user credits via the call_openai_chat_parse wrapper.
    """
    # Define the system prompt
    system_prompt = '''
    You are an assistant specialized in extracting structured information from Board of Veterans' Appeals (BVA) decision texts. Your task is to accurately identify and extract specific details from the provided legal decision text and present them in a JSON format that aligns precisely with the BvaDecisionStructuredSummary model.

    Important: Provide a concise explanation in each field. Use title case for all names

    For any field where no information is found, fill in the value with the string "no Field Name found" for example no date found in the date field.
    Ensure that all fields are present and correctly formatted.
    Use ISO 8601 format for dates (YYYY-MM-DD). Use a list format for multiple items where applicable. Use bold for emphasis where needed. Make sure its structured and easy to read.
    '''

    # Define your cost constants for prompt and completion tokens
    # (These may be different from your main app usage costs if needed)
    cost_per_prompt_token = Decimal("0.0000025")       # e.g., $2.50 per 1M tokens
    cost_per_completion_token = Decimal("0.00001")     # e.g., $10.00 per 1M tokens

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": document_text},
    ]

    try:
        # 1) Call the wrapper for parse-based completion
        response = call_openai_chat_parse(
            user_id=user_id,
            model="gpt-4o-2024-08-06",
            messages=messages,
            response_format=BvaDecisionStructuredSummary,
            temperature=0.2,
            cost_per_prompt_token=cost_per_prompt_token,
            cost_per_completion_token=cost_per_completion_token,
        )

        # 2) Extract the parsed content from the response
        information = response.choices[0].message.parsed
        return information

    except ValidationError as ve:
        print(f"Validation error: {ve}")
        return None
    except Exception as ex:
        print(f"An unexpected error occurred: {ex}")
        return None
