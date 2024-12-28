# helpers/azure_helpers.py
import os
import logging
from azure.storage.blob import BlobServiceClient, ContentSettings, generate_blob_sas, BlobSasPermissions, BlobClient
from datetime import datetime, timedelta
import mimetypes
import time
import logging

# ============        AZURE BLOB STORAGE SETUP        ============
# =============================================
# This section handles the setup of Azure Blob Storage for file uploads
# =============================================
# Load environment variables for Azure
account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
container_name = os.getenv("AZURE_CONTAINER_NAME")
account_key = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
connection_string = os.getenv("AZURE_CONNECTION_STRING")
print("AZURE_CONNECTION_STRING:", os.getenv("AZURE_CONNECTION_STRING"))


# Initialize BlobServiceClient using the connection string
blob_service_client = BlobServiceClient.from_connection_string(os.getenv("AZURE_CONNECTION_STRING"))
# ============  TESTING  ============
# =============================================
# =============================================
# =============================================
# =============================================
# =============================================
# =============================================
# ============  TESTING  ============
# =============================================
# =============================================
# =============================================
# =============================================
# =============================================
# =============================================

# helpers/azure_helpers.py

def download_file_from_azure(blob_url):
    try:
        # Extract blob name from URL
        blob_name = extract_blob_name(blob_url)
        container_name = os.getenv("AZURE_CONTAINER_NAME")
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        downloader = blob_client.download_blob()
        file_content = downloader.readall()
        logging.info(f"File '{blob_name}' successfully downloaded from Azure Blob Storage.")
        return file_content
    except Exception as e:
        logging.error(f"Error downloading file '{blob_url}' from Azure: {e}")
        return None

def extract_blob_name(blob_url):
    """Extracts the blob name from the Azure Blob Storage URL."""
    # Assuming blob_url format: "https://<account_name>.blob.core.windows.net/<container_name>/<blob_name>"
    parts = blob_url.split('/')
    container_name = os.getenv("AZURE_CONTAINER_NAME")
    container_index = parts.index(container_name)
    blob_name = '/'.join(parts[container_index + 1:])
    return blob_name

# ============  TESTING  ============
# =============================================
# =============================================
# =============================================
# =============================================
# =============================================
# =============================================
# ============  TESTING  ============
# =============================================
# =============================================
# =============================================
# =============================================
# =============================================
# =============================================

# Upload a file to Azure Blob Storage
def upload_file_to_azure(file_path, blob_name):
    try:
        container_name = os.getenv("AZURE_CONTAINER_NAME")
        account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")

        container_client = blob_service_client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(blob_name)

        # Determine the MIME type of the file
        content_type, _ = mimetypes.guess_type(file_path)
        if content_type is None:
            content_type = 'application/octet-stream'  # Default to binary if the type can't be determined

        # Upload the file with dynamic content type
        with open(file_path, "rb") as data:
            blob_client.upload_blob(
                data,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type)
            )

        blob_url = f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}"
        logging.info(f"File '{file_path}' successfully uploaded to blob '{blob_name}'. Blob URL: {blob_url}")

        return blob_url
    except Exception as e:
        logging.error(f"Error uploading file '{file_path}' to Azure: {e}")
        return None

def upload_in_memory_file_to_azure(file_data, blob_name, content_type=None):
    try:
        container_name = os.getenv("AZURE_CONTAINER_NAME")
        account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")

        container_client = blob_service_client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(blob_name)

        # Guess the content type if not provided
        if content_type is None:
            content_type, _ = mimetypes.guess_type(blob_name)
            if content_type is None:
                content_type = 'application/octet-stream'

        # Upload the in-memory file
        blob_client.upload_blob(
            file_data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type)
        )

        blob_url = f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}"
        logging.info(f"In-memory file successfully uploaded to blob '{blob_name}'. Blob URL: {blob_url}")

        return blob_url
    except Exception as e:
        logging.error(f"Error uploading in-memory file to Azure: {e}")
        return None
    
import os
import logging
import mimetypes
from azure.storage.blob import ContentSettings, BlobServiceClient
from azure.storage.blob import generate_blob_sas, BlobSasPermissions
from datetime import datetime, timedelta
from io import BytesIO

# Initialize BlobServiceClient once, globally or within a setup function
blob_service_client = BlobServiceClient(
    account_url=f"https://{os.getenv('AZURE_STORAGE_ACCOUNT_NAME')}.blob.core.windows.net/",
    credential=os.getenv('AZURE_STORAGE_ACCOUNT_KEY')
)

def upload_to_azure_blob(blob_name, file_path=None, file_data=None, content_type=None):
    """
    Uploads a file to Azure Blob Storage. Can handle both local file paths and in-memory bytes.

    :param blob_name: The name of the blob (including any virtual directories).
    :param file_path: Path to the local file to upload. Use this if uploading from the filesystem.
    :param file_data: In-memory file data as bytes. Use this if uploading from memory.
    :param content_type: Optional MIME type. If not provided, it will be guessed based on the blob_name.
    :return: The URL of the uploaded blob or None if there was an error.
    """
    try:
        container_name = os.getenv("AZURE_CONTAINER_NAME")
        account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")

        if not container_name or not account_name:
            logging.error("AZURE_CONTAINER_NAME or AZURE_STORAGE_ACCOUNT_NAME environment variables are not set.")
            return None

        container_client = blob_service_client.get_container_client(container_name)
        
        # Ensure the container exists
        if not container_client.exists():
            logging.info(f"Container '{container_name}' does not exist. Creating it.")
            container_client.create_container()

        blob_client = container_client.get_blob_client(blob_name)

        # Determine content type
        if content_type is None:
            content_type, _ = mimetypes.guess_type(blob_name)
            if content_type is None:
                content_type = 'application/octet-stream'  # Default MIME type

        # Upload logic based on provided parameters
        if file_path:
            if not os.path.isfile(file_path):
                logging.error(f"File path '{file_path}' does not exist or is not a file.")
                return None
            with open(file_path, "rb") as data:
                blob_client.upload_blob(
                    data,
                    overwrite=True,
                    content_settings=ContentSettings(content_type=content_type)
                )
        elif file_data:
            if not isinstance(file_data, (bytes, bytearray, BytesIO)):
                logging.error("file_data must be bytes, bytearray, or BytesIO.")
                return None
            blob_client.upload_blob(
                file_data,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type)
            )
        else:
            logging.error("Either file_path or file_data must be provided.")
            return None

        blob_url = f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}"
        logging.info(f"File successfully uploaded to blob '{blob_name}'. Blob URL: {blob_url}")

        return blob_url

    except Exception as e:
        logging.error(f"Error uploading to Azure Blob Storage: {e}")
        return None


# Generate a SAS URL for a given blob name
def generate_sas_url(blob_name):
    start_time = time.time()
    try:
        container_name = os.getenv("AZURE_CONTAINER_NAME")
        account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
        account_key = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")

        #print(f"Generating SAS URL for blob: {blob_name}")

        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container_name,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(hours=1)
        )
        sas_url = f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"

        elapsed_time = time.time() - start_time
        #print(f"SAS URL generated for blob '{blob_name}' in {elapsed_time:.4f} seconds")
        
        return sas_url
    except Exception as e:
        print(f"Error generating SAS URL for blob '{blob_name}': {e}")
        return None
    

def download_public_file_from_azure(blob_url):
    """
    Downloads a file directly from Azure Blob Storage without any additional encoding or security checks.
    
    :param blob_url: The full URL of the blob to download.
    :return: The content of the file as bytes, or None if there's an error.
    """
    try:
        # Initialize the BlobClient directly from the URL
        blob_client = BlobClient.from_blob_url(blob_url)
        
        # Download the blob content
        downloader = blob_client.download_blob()
        file_content = downloader.readall()
        
        logging.info(f"File successfully downloaded from Azure Blob Storage at '{blob_url}'.")
        return file_content
    except Exception as e:
        logging.error(f"Error downloading file from Azure Blob Storage at '{blob_url}': {e}")
        return None
    
