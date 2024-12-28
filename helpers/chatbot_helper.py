# helpers/chatbot_helper.py

import os
import json
import requests
import concurrent.futures
import time
from openai import OpenAI
from pinecone import Pinecone

###############################################################################
# 1. ENV & GLOBAL SETUP
###############################################################################
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENV = "us-east-1"  # or your region

INDEX_NAME_CFR = "38-cfr-index"
INDEX_NAME_M21 = "m21-index"

EMBEDDING_MODEL = "text-embedding-3-small"  # or whichever embedding model you prefer

# Initialize the OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Initialize Pinecone
pc = Pinecone(api_key=PINECONE_API_KEY)
index_cfr = pc.Index(INDEX_NAME_CFR)
index_m21 = pc.Index(INDEX_NAME_M21)

###############################################################################
# 2. QUERY CLEANUP
###############################################################################
def clean_up_query_with_llm(user_query: str) -> str:
    """
    Uses an OpenAI LLM to rewrite the user query in a more standardized,
    formal, or clarified way—removing slang, expanding contractions, etc.
    """
    system_message = (
        "You are a helpful assistant that rewrites user queries for better text embeddings. "
        "Expand or remove contractions, fix grammatical errors, and keep the original meaning. "
        "Be concise and ensure the question is still natural and complete. You will rewrite it "
        "professionally as if talking directly to a VA rater who could answer the question. "
        "Remove sentences not relevant to the question."
    )

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_query},
    ]

    response = client.chat.completions.create(
        model="gpt-4o",  # Ensure you have access to this model or use a supported model
        messages=messages,
        temperature=0
    )
    cleaned_query = response.choices[0].message.content
    return cleaned_query.strip()


###############################################################################
# 3. EMBEDDING
###############################################################################
def get_embedding(text: str) -> list:
    """
    Gets the embedding vector for `text` using your chosen EMBEDDING_MODEL.
    """
    response = client.embeddings.create(
        input=text,
        model=EMBEDDING_MODEL
    )
    return response.data[0].embedding


###############################################################################
# 4. MULTITHREADED SECTION RETRIEVAL FROM AZURE
###############################################################################
# 4A) For 38 CFR => uses "section_number"
def fetch_matches_content(search_results, max_workers=3) -> list:
    """
    Parallel fetch of section text for all Pinecone matches (38 CFR).
    Returns a list of dicts, e.g.:
      [
        {
          "section_number": <str>,
          "matching_text": <str or None>
        },
        ...
      ]
    """
    matches = search_results.get("matches", [])

    def get_section_text(section_number: str, part_number: str) -> str:
        """
        Locally load the correct file based on part_number,
        then find the item whose metadata.section_number == section_number.
        """
        # Decide which local file to load
        if part_number == "3":
            file_path = os.path.join("json", "json/part_3_flattened.json")
        elif part_number == "4":
            file_path = os.path.join("json", "json/part_4_flattened.json")
        else:
            # Fallback or handle other parts as needed
            return None

        if not os.path.exists(file_path):
            return None

        with open(file_path, "r") as f:
            data = json.load(f)  # e.g. [ { "text": "...", "metadata": {...} }, ... ]

        # Find the item(s) with matching section_number
        for item in data:
            meta = item.get("metadata", {})
            if meta.get("section_number") == section_number:
                return item.get("text")
        return None

    # We only need the part_number and section_number from each match’s metadata
    matching_texts = []
    for match in matches:
        metadata = match.get("metadata", {})
        section_num = metadata.get("section_number")
        part_number = metadata.get("part_number")
        if not section_num or not part_number:
            continue

        # We no longer fetch from a URL; instead, load from local JSON
        section_text = get_section_text(section_num, part_number)
        matching_texts.append({
            "section_number": section_num,
            "matching_text": section_text
        })

    return matching_texts

# 4B) For M21 => uses "article_number"
def fetch_matches_content_m21(search_results, max_workers=3) -> list:
    """
    Parallel fetch of article text for all Pinecone matches (M21).
    Returns a list of dicts, e.g.:
      [
        {
          "article_number": <str>,
          "matching_text": <str or None>
        },
        ...
      ]
    """
    matches = search_results.get("matches", [])

    def get_article_text(article_number: str, manual: str) -> str:
        """
        Locally load the correct M21 file based on 'manual',
        then find the item whose metadata.article_number == article_number.
        """
        if manual == "M21-1":
            file_path = os.path.join("json", "json/m21_1_chunked3k.json")
        elif manual == "M21-5":
            file_path = os.path.join("json", "json/m21_5_chunked3k.json")
        else:
            # If there's another manual or fallback
            return None

        if not os.path.exists(file_path):
            return None

        with open(file_path, "r") as f:
            data = json.load(f)

        for item in data:
            meta = item.get("metadata", {})
            if meta.get("article_number") == article_number:
                return item.get("text")

        return None

    matching_texts = []
    for match in matches:
        metadata = match.get("metadata", {})
        article_num = metadata.get("article_number")
        manual_val = metadata.get("manual")  # e.g. "M21-1" or "M21-5"
        if not article_num or not manual_val:
            continue

        article_text = get_article_text(article_num, manual_val)
        matching_texts.append({
            "article_number": article_num,
            "matching_text": article_text
        })

    return matching_texts



###############################################################################
# 5. TWO SEARCH FUNCTIONS (38 CFR and M21)
###############################################################################
def search_cfr_documents(query: str, top_k: int = 3) -> str:
    """
    Searches the 38 CFR Pinecone index.
    1) LLM-based cleanup
    2) Pinecone embedding-based search
    3) Parallel fetch from Azure
    4) Return combined text as a single string
    """
    cleaned_query = clean_up_query_with_llm(query)
    query_emb = get_embedding(cleaned_query)

    # Query Pinecone (CFR index)
    results = index_cfr.query(
        vector=query_emb,
        top_k=top_k,
        include_metadata=True
    )

    # Fetch actual text in parallel (using section_number)
    matching_sections = fetch_matches_content(results, max_workers=3)
    if not matching_sections:
        return "No sections found (CFR)."

    references_str = ""
    for item in matching_sections:
        sec_num = item["section_number"]
        text_snippet = item["matching_text"] or "N/A"
        references_str += f"\n---\nSection {sec_num}:\n{text_snippet}\n"

    return references_str.strip()


def search_m21_documents(query: str, top_k: int = 3) -> str:
    """
    Searches the M21-1 Pinecone index.
    1) LLM-based cleanup
    2) Pinecone embedding-based search
    3) Parallel fetch from Azure
    4) Return combined text as a single string
    """
    cleaned_query = clean_up_query_with_llm(query)
    query_emb = get_embedding(cleaned_query)

    # Query Pinecone (M21 index)
    results = index_m21.query(
        vector=query_emb,
        top_k=top_k,
        include_metadata=True
    )

    # Fetch actual text in parallel (using article_number)
    matching_articles = fetch_matches_content_m21(results, max_workers=3)
    if not matching_articles:
        return "No articles found (M21)."

    references_str = ""
    for item in matching_articles:
        article_num = item["article_number"]
        text_snippet = item["matching_text"] or "N/A"
        references_str += f"\n---\nArticle {article_num}:\n{text_snippet}\n"

    return references_str.strip()


###############################################################################
# 6. CREATE A SINGLE, PERSISTENT ASSISTANT
###############################################################################
# NOTE: We add a gentle reminder to avoid repetitive greetings:
assistant_instructions = (
    "You are a virtual assistant that helps veterans understand disability claims with the VA. "
    "You should be able to answer questions about the process, eligibility, supporting evidence, "
    "and required documentation. Provide a helpful response to the user, and include references "
    "from the 38 CFR or other official sources when relevant.\n\n"
    "You have two tools you can call whenever you need official references:\n"
    "1) search_cfr_documents  (for 38 CFR references)\n"
    "2) search_m21_documents  (for M21-1 references)\n\n"
    "If you already know the answer from memory, you can answer directly. If you need references, "
    "call the appropriate tool.\n\n"
    "Avoid repeating the same greeting each time. If the conversation has started, simply answer."
)

assistant = client.beta.assistants.create(
    name="VA Claims Consultant",
    instructions=assistant_instructions,
    tools=[
        {
            "type": "function",
            "function": {
                "name": "search_cfr_documents",
                "description": (
                    "Use this to retrieve official VA references from the 38 CFR. "
                    "Provide the user's question as 'query'. "
                    "This function will clean the query, embed the text, query Pinecone, "
                    "and return the relevant text needed to answer the user's question."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The user's question or prompt that needs official references."
                        },
                        "top_k": {
                            "type": "number",
                            "description": "Number of top matches to retrieve (default=3)."
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_m21_documents",
                "description": (
                    "Use this to retrieve official VA references from M21-1. "
                    "Provide the user's question as 'query'. "
                    "This function will clean the query, embed the text, query Pinecone, "
                    "and return the relevant text needed to answer the user's question."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The user's question or prompt that needs official references."
                        },
                        "top_k": {
                            "type": "number",
                            "description": "Number of top matches to retrieve (default=3)."
                        }
                    },
                    "required": ["query"]
                }
            }
        },
    ],
    model="gpt-4o",
)


###############################################################################
# 7. A SINGLE-TURN HELPER OR MULTI-TURN HELPER
###############################################################################
def continue_conversation(user_input: str, thread_id: str = None) -> dict:
    """
    Use an existing thread_id if provided; else create a new thread.
    Add the user's message, create a run, handle any required tool calls, 
    and return the final assistant message.

    Returns a dict:
    {
        "assistant_message": "...",
        "thread_id": "..."
    }
    """
    # 1) Either create a new thread or stub the existing one
    if not thread_id:
        thread = client.beta.threads.create()
        thread_id = thread.id
        print(f"[LOG] Created NEW thread: {thread_id}")
    else:
        print(f"[LOG] Reusing EXISTING thread: {thread_id}")
        # We don't need to "retrieve" it; just need an object with .id
        thread = type("ThreadStub", (), {})()
        thread.id = thread_id

    # 2) Add the user's message
    user_message = client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_input
    )
    print(f"[LOG] Added user message. ID: {user_message.id}")

    # 3) Create a new Run on the Thread
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant.id
    )
    print(f"[LOG] Created run. ID: {run.id}, status={run.status}")

    # 4) Poll until completed, requires_action, failed, or incomplete
    while True:
        updated_run = client.beta.threads.runs.retrieve(
            thread_id=thread.id, 
            run_id=run.id
        )
        if updated_run.status in ["completed", "requires_action", "failed", "incomplete"]:
            break
        time.sleep(1)

    print(f"[LOG] Polled run => status: {updated_run.status}")

    # 5) If the run requires tool outputs => handle them (the model might call multiple tools)
    while updated_run.status == "requires_action":
        action_data = updated_run.required_action
        if action_data and action_data.submit_tool_outputs:
            tool_calls = action_data.submit_tool_outputs.tool_calls
            tool_outputs = []

            for call in tool_calls:
                function_name = call.function.name
                function_args = call.function.arguments
                print(f"[LOG] Tool call requested: {function_name} with args={function_args}")

                if function_name == "search_cfr_documents":
                    args = json.loads(function_args)
                    query_text = args["query"]
                    top_k_arg = args.get("top_k", 3)
                    result_str = search_cfr_documents(query_text, top_k=top_k_arg)
                    tool_outputs.append({
                        "tool_call_id": call.id,
                        "output": result_str
                    })

                elif function_name == "search_m21_documents":
                    args = json.loads(function_args)
                    query_text = args["query"]
                    top_k_arg = args.get("top_k", 3)
                    result_str = search_m21_documents(query_text, top_k=top_k_arg)
                    tool_outputs.append({
                        "tool_call_id": call.id,
                        "output": result_str
                    })

                else:
                    tool_outputs.append({
                        "tool_call_id": call.id,
                        "output": "No implementation for this tool."
                    })

            # Submit the tool outputs
            client.beta.threads.runs.submit_tool_outputs(
                thread_id=thread.id,
                run_id=updated_run.id,
                tool_outputs=tool_outputs
            )
            print("[LOG] Submitted tool outputs. Polling again...")

            # Poll again to see if run completes or calls more tools
            while True:
                updated_run = client.beta.threads.runs.retrieve(
                    thread_id=thread.id, 
                    run_id=run.id
                )
                if updated_run.status in ["completed", "failed", "incomplete", "requires_action"]:
                    break
                time.sleep(1)

        print(f"[LOG] After tool submission => run status: {updated_run.status}")

    # 6) Now either completed, failed, or incomplete
    if updated_run.status == "completed":
        # Retrieve the final assistant message
        msgs = client.beta.threads.messages.list(thread_id=thread.id)
        assistant_messages = [m for m in msgs.data if m.role == "assistant"]
        if assistant_messages:
            final_text = assistant_messages[0].content[0].text.value
            print(final_text, "final text*******")
            # Force final_text into string form:
            final_text = str(final_text)

            print("[LOG] Final assistant message found.")
            print(final_text)
            return {
                "assistant_message": final_text,
                "thread_id": thread_id
            }
        else:
            return {
                "assistant_message": "No final assistant message found.",
                "thread_id": thread_id
            }

    elif updated_run.status == "failed":
        return {
            "assistant_message": "Run ended with status: failed. The model encountered an error.",
            "thread_id": thread_id
        }

    elif updated_run.status == "incomplete":
        return {
            "assistant_message": "Run ended with status: incomplete. Possibly waiting for more info.",
            "thread_id": thread_id
        }

    else:
        return {
            "assistant_message": f"Run ended with status: {updated_run.status}, no final message produced.",
            "thread_id": thread_id
        }
