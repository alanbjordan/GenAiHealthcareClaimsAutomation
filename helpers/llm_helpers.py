# helpers/llm_helpers.py
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image
import logging
import io
import os
from openai import OpenAI
from models.llm_models import PageClassification
import os
import logging
from openai import OpenAI
from models import *
from models.llm_models import *
import json
from pydantic import ValidationError
from concurrent.futures import ThreadPoolExecutor, as_completed

# ====================================================
# Section: CONFIGURATION
# ====================================================
# Description:  Logging and Openai Setup
# ====================================================

# Set up the OpenAI API key to interact with the GPT models
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),  # This is the default and can be omitted
)
if not client:
    raise ValueError("Please set the VA_AUTOMATION_API_KEY environment variable.")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize OpenAI client
#client = OpenAI(api_key=api_key)

# ============  TESTING  ============

def generate_summary(text_content):
    """Generate a summary of the text content using OpenAI GPT."""
    try:
        report_prompt_text = f"Please provide a concise summary of the following document:\n\n{text_content}"

        # Create the GPT-4 completion using the specified client and response structure
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "assistant", "content": "You are a helpful assistant that summarizes documents."},
                {"role": "user", "content": report_prompt_text}
            ]
        )

        # Extract and return the final report
        summary = response.choices[0].message.content.strip()
        return summary

    except Exception as e:
        logging.error(f"Error generating summary: {str(e)}")
        print(e)
        raise e

# Function to classify diagnosis with GPT
def classify_and_store_diagnosis(pages_text, prompt_text, model="gpt-4o"):
    """
    Processes text for each page, classifies medical conditions, and stores the results immediately in a dictionary.
    
    Args:
        pages_text (dict): Dictionary with page numbers as keys and text as values.
        prompt_text (str): The base prompt text used for classification.
        model (str): The GPT model to be used for classification (default is gpt-4o).
        
    Returns:
        dict: JSON Object containing page numbers and their respective classified diagnoses.
    """
    classified_results = {}

    for page_number, text in pages_text.items():
        try:
            # Construct the prompt for the current page
            prompt = f"{prompt_text} ::: Document Content on Page {page_number}: {text}"

            # Make the OpenAI API call
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful VA claims assistant designed to output JSON."},
                    {"role": "user", "content": prompt}
                ]
            )

            # Store the classification result
            classified_results[page_number] = response.choices[0].message.content.strip()
            logging.info(f"Processed Page {page_number}: {classified_results[page_number]}")

        except Exception as e:
            print(f"Error processing Page {page_number}: {e}")
            classified_results[page_number] = f"Error: {e}"

    return classified_results

# Prompt Text Initialization
classifiy_prompt_text = (
    "Objective: Systematically identify and classify potential disabilities from in-service military treatment records, ensuring that each diagnosis is supported by clear evidence within the records. "
    "Look for Problems, Diagnosis, Or Complaints. Task: Examine the provided in-service or post-service treatment records and classify potential diagnoses or actual diagnoses along with their respective ICD codes and categories. "
)

# Function to generate a report
def generate_report(svc_diag, post_diag):
    report_template = """
    ---
    **Summary of In-Service Diagnoses**
    The in-service medical records document the following diagnoses:
    {in_service_diagnoses}
    
    **Summary of Post-Service Diagnoses**
    The post-service medical records document the following diagnoses:
    {post_service_diagnoses}

    **Recommendations for Disabilities to Claim**
    Based on the analysis, the veteran should consider filing claims for the following disabilities:
    {recommendations}

    **Establishing Nexus Through Medications or Medical Events**
    - **Medications:**
    - Document any medications prescribed during service for the diagnosed conditions.
    - Note any long-term side effects or conditions resulting from medication use.

    - **Medical Events:**
    - Highlight specific incidents (e.g., injury, exposure to trauma) with detailed descriptions.
    - Provide incident reports or buddy statements as evidence.

    ---
    """
    
    # Define the prompt with clear instructions for the AI
    report_prompt_text = (
        "You are a 20-year expert in Veterans Affairs claim consultancy. Below are two datasets, "
        "one containing diagnoses from in-service medical records and another from post-service records. "
        "Please draft a final report analyzing any potential diagnoses from the in-service records that "
        "can be directly connected to current diagnoses documented in the post-service records. "
        f" :::::::::  In-Service Diagnoses:\n{svc_diag} :::::::::  "
        "\n :::::::::  Post-Service Diagnoses:\n"
        f"{post_diag} :::::::::  "
    )
    
    # Create the GPT-4 completion
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "assistant", "content": "You are an expert Veterans Affairs Claim Consultant"},
            {"role": "user", "content": report_prompt_text}
        ]
    )

    # Extract and return the final report
    return response.choices[0].message.content.strip()

# ====================================================
# Section: DETECT DOCUMENT TYPE
# ====================================================
# Description: OpenAI Classification
# ====================================================
def detect_document_type(text):
    completion = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Identify the category of each VA military claims document based on its content and structure"},
            {"role": "user", "content": text},
        ],
        response_format=PageClassification,
    )
    information = completion.choices[0].message.parsed
    return information

def detect_document_types(texts: List[str]) -> PageClassifications:
    """
    Detect document types for a batch of page contents using Structured Outputs.
    Since the context length of OpenAI API is limited, we process the pages in batches of 25.
    """
    batch_size = 25
    batches = [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]
    results = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(process_batch, batch_idx * batch_size, batch)
            for batch_idx, batch in enumerate(batches)
        ]

        for future in as_completed(futures):
            batch_results = future.result()
            results.extend(batch_results)

    # Sort the results by page number to maintain the correct order
    results.sort(key=lambda x: x.page_number)

    # Construct a PageClassifications object from the sorted results
    classifications = PageClassifications(pages=results)
    return classifications

def process_batch(start_idx: int, texts: List[str]) -> List[PageClassification]:
    """
    Process a batch of texts to detect document types.
    
    Args:
        start_idx (int): The starting index of the batch in the overall list.
        texts (List[str]): A list of page contents for the batch.
    
    Returns:
        List[PageClassification]: A list of page classifications for the batch.
    """
    system_prompt = (
        "For each of the following VA military claims documents, identify the category based on its content and structure. "
        "Provide the classification results in a JSON object adhering to the following schema:\n"
        "{\n"
        "  \"pages\": [\n"
        "    {\n"
        "      \"page_number\": <PageNumber>,\n"
        "      \"category\": \"<DocumentType>\",\n"
        "      \"confidence\": <ConfidenceScore>,\n"
        "      \"document_date\": \"<DocumentDate>\"\n"
        "    }\n"
        "  ]\n"
        "}"
    )

    # Construct the user message with page numbers
    documents_text = "\n".join([
        f"Document {start_idx + idx + 1}:\n{text}\n"
        for idx, text in enumerate(texts)
    ])

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": documents_text},
    ]

    try:
        # Call the OpenAI API with Structured Outputs
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-2024-08-06",
            messages=messages,
            response_format=PageClassifications,
        )

        message = completion.choices[0].message

        # Parse the structured response
        classifications = message.parsed  # Instance of PageClassifications
        return classifications.pages  # Return list of PageClassification objects

    except ValidationError as ve:
        logger.error(f"Validation error: {ve}")
        raise RuntimeError("Received data does not conform to the PageClassifications schema.") from ve
    except Exception as e:
        logger.error(f"Error during document type detection: {e}")
        raise RuntimeError(f"Error during document type detection: {e}") from e

# ====================================================
# Section: Document Type Processing and Information Extraction
# ====================================================
# Description: Triggers Informaion Extraction by Type
# ====================================================

def process_document_based_on_type(document_text, document_type):

    system_prompt = '''
    You are an assistant designed to extract record information accurately. 
    For each visit in the clinical record, identify each diagnosis and associate only the relevant medications, treatments, and findings with that specific diagnosis. 
    Ensure that no unrelated medications, treatments, or doctors notes/comments are linked to a diagnosis. Break apart the information to fit its corresponding diagnosis.
    Don't use the active mediations list as it could be from other diagnosis. Focus on prescriptions provided by the current doctor. The output should conform to the provided Pydantic models.
    ISO 8601 Format The Date: YYYY-MM-DD
    '''

    if document_type == DocumentType.Clinical_Records:
        # Extract using ClinicalRecord model
        completion = client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": document_text},
            ],
            response_format=ClinicalRecord,
            temperature=0.2
        )
        information = completion.choices[0].message.parsed
        return information

    elif document_type == DocumentType.DD214:
        # Extract using DD214Record model
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Extract DD214 record information."},
                {"role": "user", "content": document_text},
            ],
            response_format=DD214Record,
        )
        information = completion.choices[0].message.parsed
        
        return information
    
    elif document_type == DocumentType.Military_Personnel_Records:
        # Extract using MilitaryPersonnelRecord model
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Extract Military Personnel Record information."},
                {"role": "user", "content": document_text},
            ],
            response_format=MilitaryPersonnelRecord,
        )
        information = completion.choices[0].message.parsed
        return information

    elif document_type == DocumentType.Legal_Documents:
        # Extract using LegalDocument model
        completion = client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Extract Legal Document information."},
                {"role": "user", "content": document_text},
            ],
            response_format=LegalDocument,
        )
        information = completion.choices[0].message.parsed
        return information

    elif document_type == DocumentType.Decision_Letter:
        # Extract using DecisionLetter model
        completion = client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Extract Decision Letter information."},
                {"role": "user", "content": document_text},
            ],
            response_format=DecisionLetter,
        )
        information = completion.choices[0].message.parsed
        return information

    elif document_type == DocumentType.Notification_Letter:
        # Extract using NotificationLetter model
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Extract Notification Letter information."},
                {"role": "user", "content": document_text},
            ],
            response_format=NotificationLetter,
        )
        information = completion.choices[0].message.parsed
        return information

    elif document_type == DocumentType.Financial_Documents:
        # Extract using FinancialDocument model
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Extract Financial Document information."},
                {"role": "user", "content": document_text},
            ],
            response_format=FinancialDocument,
        )
        information = completion.choices[0].message.parsed
        return information

    elif document_type == DocumentType.Education_Materials:
        # Extract using EducationMaterial model
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Extract Education Material information."},
                {"role": "user", "content": document_text},
            ],
            response_format=EducationMaterial,
        )
        information = completion.choices[0].message.parsed
        return information

    elif document_type == DocumentType.Correspondence:
        # Extract using Correspondence model
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Extract Correspondence information."},
                {"role": "user", "content": document_text},
            ],
            response_format=Correspondence,
        )
        information = completion.choices[0].message.parsed
        return information

    elif document_type == DocumentType.Award_Letter:
        # Extract using AwardLetter model
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Extract Award Letter information."},
                {"role": "user", "content": document_text},
            ],
            response_format=AwardLetter,
        )
        information = completion.choices[0].message.parsed
        return information

    elif document_type == DocumentType.Disability_Application:
        # Extract using DisabilityApplication model
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Extract Disability Application information."},
                {"role": "user", "content": document_text},
            ],
            response_format=DisabilityApplication,
        )
        information = completion.choices[0].message.parsed
        return information

    elif document_type == DocumentType.Unclassified:
        # Extract using UnclassifiedDocument model
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Extract Unclassified Document information."},
                {"role": "user", "content": document_text},
            ],
            response_format=UnclassifiedDocument,
        )
        information = completion.choices[0].message.parsed
        return information

    else:
        print(f"Processing not implemented for document type: {document_type}")
        return None

def generate_embedding(combined_text):
    """
    Generates an embedding vector for the given text using OpenAI's API.
    """
    try:
        response = client.embeddings.create(
            input=combined_text,
            model="text-embedding-3-large"  # Ensure you're using the correct model
        )
        embedding = response.data[0].embedding
        #print("Embedding Generated: ",embedding[0:10])
        return embedding
    except client.Error as e:
        print(f"OpenAI API error: {e}")
        raise

# Generate claim summary based on conditions selected
def generate_claim_response(text_content):
    """Generate a summary of the text content using OpenAI GPT."""
    try:
        assistant_prompt = f"""
        Please do not include a subject heading or a signoff like best, respectfully with a veteran name. Its a statement.
        Write a statement in support of my VA claim, using a first-person perspective. The goal of this statement is to assist VA raters and Compensation & Pension (C&P) examiners in understanding the evidence in my in-service records that support an in-service event or injury. In the statement, please include the following details:
        Clearly outline the in-service event, symptoms, or incident that occurred, based on documented evidence.
        Describe the treatments I received at the time, any medical professionals notes, and findings documented in my service records.
        Explain how these findings and treatments support a connection to my current medical conditions.
        Use language that is factual yet compassionate, highlighting the impact of the service-connected event on my health.
        The tone should be respectful, sincere, and clear, ensuring that my statement helps VA raters and C&P examiners see the link between my service record evidence and my current disability claim. Check the in_service boolean and based on whats in_service or not in_service that should help connect current (no inservice) conditions to in_service conditions. Be sure to mention both if they are availalbe. If only in_service treatment = True is in the text then explain simplily that the veteran still has symptoms and would like a C&P exam. But if in_service:True and in_service: False are in the text do not request C&P exam."""
        # Create the GPT-4 completion using the specified client and response structure
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "assistant", "content": assistant_prompt},
                {"role": "user", "content": text_content}
            ],
            max_tokens=750
        )
        # Extract and return the final report
        summary = response.choices[0].message.content.strip()
        return summary
    except Exception as e:
        print(e)
        raise e

def generate_cheat_sheet_response(text_content):
    """Generate a summary of the text content using OpenAI GPT."""
    try:
        assistant_prompt = f"""
        You are a subject-matter expert in VA disability claims and C&P (Compensation & Pension) exams. Your task is to generate a personalized, last-minute, anxiety-relieving, easy-to-understand guide for a veteran attending a C&P exam. The guide must focus on helping the veteran articulate symptoms and understand how their condition may relate to VA disability ratings. 

        The payload includes specific evidence provided by the veteran, including diagnoses, relevant dates, and detailed information about their symptoms. Use this evidence to make the guide highly relevant and actionable (Provide exact dates, doctors, and diagnosis, and treatments from the evidence). Here are the specific requirements:

        1. **Diagnosis and Evidence Integration**:
           - Incorporate the veteran's evidence into the guide, including:
             - Diagnosed conditions and dates of diagnosis or symptom onset.
             - Any documented medical findings, such as range of motion, pain levels, frequency of episodes, or other measurable criteria.
             - Notes about treatments, medications, or recommendations from healthcare providers.

        2. **Provide Examples and VA Disability Rating Criteria**:
           - Break down the veteran’s conditions and connect them to specific VA disability percentages. For instance:
           
           PTSD:
           - 10%: Mild symptoms with minimal impact on work/social life.
           - 50%: Persistent symptoms like panic attacks or difficulty maintaining relationships.
           - 100%: Total social and occupational impairment.

           Back Pain:
           - 10%: Pain with limited motion but no major incapacitation.
           - 40%: Severe limitation of motion with persistent discomfort.

           *Example*: "Based on the veteran's reported symptoms of daily back pain limiting mobility to 20 degrees flexion and requiring medication for relief, this aligns with the criteria for a 40% rating."

        3. **Tips for Communication**:
           - Provide specific advice to help the veteran clearly communicate their symptoms:
             - Use first-hand examples of how the condition affects daily life.
             - Describe "bad days" without minimizing symptoms.
             - Mention triggers, severity, and frequency of symptoms.

        4. **Encouraging Language**:
           - Add a motivational note to ease the veteran's anxiety:
             - "This is your opportunity to share your experience openly and honestly. Every detail helps the examiner understand your situation."

        5. **Output Requirements**:
           - Use the veteran’s provided evidence and diagnosis to craft a guide that’s clear, straightforward, and free of jargon.
           - Keep the tone empathetic and supportive.
           - Format the output as a concise, bullet-point list for easy reference.

        6. **Dynamic Input and Tailored Guidance**:
           - Tailor the cheat sheet to the conditions and evidence provided by the veteran.
           - Include only the relevant VA disability percentage criteria for the provided conditions.

        Example Output:
        
        C&P Exam Guide for PTSD and Back Pain

        1. General Tips for the Exam:
           - Be prepared to discuss your symptoms in detail.
           - Don’t downplay your challenges—be truthful about how they affect your daily life.

        2. PTSD Symptoms by VA Rating:
           - 10%: Mild anxiety, manageable with minimal effect on daily activities.
           - 30%: Occasional panic attacks, mild difficulty maintaining social/work relationships.
           - 70%: Impairment in most areas (e.g., family, work), frequent panic attacks.
           - 100%: Complete social and occupational impairment, inability to leave the house.

        3. Back Pain Symptoms by VA Rating:
           - 10%: Pain with limited motion but no major incapacitation.
           - 40%: Severe limitation of motion with persistent discomfort.

        4. Using Your Evidence:
           - "Documented pain in your lower back limits motion to 20 degrees and requires daily medication, aligning with a 40% rating."
           - "Medical records mention flare-ups twice per week, significantly impacting mobility."
        
        4b. Explaining Your Evidence:
           - You have the following inservice diagnosis evidence < said evidence >
           - You have the following post service evidence < said evidence >
           - You do not have any post service diagnosis so your goal is to receive a diagnosis today at your exam
           - You do not have any inservice diagnosis so your goal is to explain your inservice treatment causes your current diagnosis.

        5. Encouragement:
           - "Remember: You’re advocating for yourself. Be open and descriptive. Share how these conditions affect your daily life, from work to family responsibilities."

        Use the provided input to tailor the guide to the veteran’s unique conditions and evidence.
        """
        # Create the GPT-4 completion using the specified client and response structure
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "assistant", "content": assistant_prompt},
                {"role": "user", "content": text_content}
            ],
            temperature=0,  # Deterministic output
            top_p=1 
        )
        # Extract and return the final report
        summary = response.choices[0].message.content.strip()
        return summary
    except Exception as e:
        print(e)
        raise e

def structured_summarize_bva_decision_llm(decision_citation, full_text, client=client):
    system_prompt = """
    You are an assistant who analyzes BVA decisions and extracts structured information.
    Given the BVA decision text, identify the claimed conditions and their outcomes 
    (granted, denied, remanded, dismissed), the judge's overall reasoning, and key evidence considered.

    Follow these rules:
    - Always produce output that matches the BvaDecisionStructuredSummary schema.
    - 'decision_citation' should match the citation provided by the user.
    - Extract as many claimed conditions as can be identified, with their outcome and specific reasoning.
    - Include overall reasoning in a concise form, focusing on why the judge ruled this way.
    - Include evidence considered, such as DBQs, medical opinions, service treatment records, lay statements, etc.
    - If some fields are not found, use an empty list or a short placeholder (e.g., "")
    """

    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Decision Citation: {decision_citation}\n\n{full_text}"},
            ],
            response_format=BvaDecisionStructuredSummary,
        )

        information = completion.choices[0].message.parsed
        # Ensure the decision_citation in the structured data matches the input
        return information

    except Exception as e:
        raise e
    

    # Global variable to store progress messages
progress_messages = []

# Global dictionaries to store OCR results and diagnoses
in_service_page_texts = {}
post_service_page_texts = {}
in_service_diagnosis = {}
post_service_diagnosis = {}

def process_files(files, result_dict, file_type):
    """Process each file, performing OCR and storing the results."""
    for file_num, file in enumerate(files, start=1):
        progress_messages.append(f"Processing {file_type} file {file_num}/{len(files)}...")
        if file.content_type == 'application/pdf':
            process_pdf(file, result_dict, file_num, file_type)
        else:
            process_image(file, result_dict, file_num, file_type)

def process_pdf(pdf_file, result_dict, file_num, file_type):
    """Convert PDF to images and perform OCR on each page."""
    try:
        images = convert_from_bytes(pdf_file.read())
        progress_messages.append(f"PDF {file_type} file {file_num}: {len(images)} pages to process...")
        for page_num, image in enumerate(images, start=1):
            text = pytesseract.image_to_string(image)
            result_dict[f"{file_type}_file_{file_num}_page_{page_num}"] = text
            progress_messages.append(f"Processed {file_type} file {file_num}, page {page_num}")
    except Exception as e:
        progress_messages.append(f"Error processing PDF for {file_type}: {str(e)}")
        logging.error(f"Error processing PDF for {file_type}: {str(e)}")

def process_image(image_file, result_dict, file_num, file_type):
    """Perform OCR on image files."""
    try:
        progress_messages.append(f"Processing {file_type} image file {file_num}...")
        image = Image.open(image_file)
        text = pytesseract.image_to_string(image)
        result_dict[f"{file_type}_file_{file_num}"] = text
        progress_messages.append(f"Processed {file_type} image file {file_num}")
    except Exception as e:
        progress_messages.append(f"Error processing image for {file_type}: {str(e)}")
        logging.error(f"Error processing image for {file_type}: {str(e)}")