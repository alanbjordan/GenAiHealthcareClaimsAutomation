import os
from openai import OpenAI
from pydantic import ValidationError
from dotenv import load_dotenv
from models.decision_models import *

# Load environment variables from a .env file
load_dotenv()

# Set up the OpenAI API key to interact with the GPT models
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),  # Ensure this is set correctly
)
if not client:
    raise ValueError("Please set the VA_AUTOMATION_API_KEY environment variable.")

# Define the system prompt
system_prompt = '''
You are an assistant specialized in extracting structured information from Board of Veterans' Appeals (BVA) decision texts. Your task is to accurately identify and extract specific details from the provided legal decision text and present them in a JSON format that aligns precisely with the BvaDecisionStructuredSummary model.

Important: Provide a concise explanation in each field. Use title case for all names

For any field where no information is found, fill in the value with the string "no Field Name found" for example no date found in the date field.
Ensure that all fields are present and correctly formatted.
Use ISO 8601 format for dates (YYYY-MM-DD).
'''

def summarize_decision(document_text):
    """
    Summarize a BVA decision text into a BvaDecisionStructuredSummary,
    ensuring all fields are present by using required fields in the Pydantic model.
    """
    try:
        # Request the model to output JSON matching the Pydantic model
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-2024-08-06",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": document_text},
            ],
            response_format=BvaDecisionStructuredSummary,
            temperature=0.2,
        )

        # The API should return a JSON string matching the schema
        information = completion.choices[0].message.parsed
        return information

    except ValidationError as ve:
        print(f"Validation error: {ve}")
        return None
    except Exception as ex:
        print(f"An unexpected error occurred: {ex}")
        return None

