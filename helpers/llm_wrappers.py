import decimal
from datetime import datetime
from flask import g
from openai import OpenAI
from models.sql_models import Users, OpenAIUsageLog
import os

api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

def call_openai_chat_create(
    user_id: int,
    model: str,
    messages: list,
    temperature: float,
    **kwargs
):
    """
    Wrapper for client.chat.completions.create(...) that logs usage in openai_usage_logs
    and updates the user's cost/credits.

    For gpt-4o, default cost:
      - prompt tokens: $2.50 / 1M => 0.0000025 each
      - completion tokens: $10.00 / 1M => 0.00001 each

    :param user_id: The user’s ID (int)
    :param model:   Model name (e.g. "gpt-4o")
    :param messages:List of messages for ChatCompletion
    :param temperature: Float temperature (defaults to 0.7)
    :param **kwargs: Additional arguments like max_tokens, etc.
    :return: The raw OpenAI response object.
    """
    db_session = g.session  # from flask.g
    user = db_session.query(Users).filter_by(user_id=user_id).first()
    if not user:
        raise ValueError(f"User not found (user_id={user_id}).")

    # 1) Actually call OpenAI
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        **kwargs
    )

    # 2) Extract usage
    usage_obj = getattr(response, "usage", None)
    if usage_obj:
        prompt_tokens = usage_obj.prompt_tokens
        completion_tokens = usage_obj.completion_tokens
        total_tokens = usage_obj.total_tokens
    else:
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

    # 3) Calculate cost based on separate rates
    # For gpt-4o:
    cost_per_prompt_token = decimal.Decimal("0.0000025")   # $2.50 per 1M
    cost_per_completion_token = decimal.Decimal("0.00001") # $10.00 per 1M

    # Multiply each token count by its rate
    prompt_cost = prompt_tokens * cost_per_prompt_token
    completion_cost = completion_tokens * cost_per_completion_token
    total_cost = prompt_cost + completion_cost

    # 4) Insert usage log
    usage_log = OpenAIUsageLog(
        user_id=user_id,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost=total_cost,  # store total cost
        created_at=datetime.utcnow()
    )
    db_session.add(usage_log)

    # 5) Update user’s credits
    user.credits_remaining -= total_tokens

    db_session.commit()

    return response


def call_openai_embeddings(
    user_id: int,
    input_text: str,
    model: str,
    cost_per_token: decimal.Decimal, 
    **kwargs
):
    """
    A wrapper for client.embeddings.create(...) that:
      1) Looks up the user
      2) Calls the OpenAI embeddings endpoint
      3) Logs usage info in 'openai_usage_logs'
      4) Updates user credits/cost
      5) Returns the raw response

    :param user_id: The user’s ID
    :param input_text: The text to embed
    :param model: The embeddings model (e.g. "text-embedding-3-small")
    :param cost_per_token: Rate in USD per token (adjust for your model's pricing)
    :param **kwargs: Additional arguments (if needed)
    :return: The raw OpenAI response object (including usage info)
    """
    db_session = g.session
    user = db_session.query(Users).filter_by(user_id=user_id).first()
    if not user:
        raise ValueError(f"User not found (user_id={user_id}).")

    # 1) Make the embeddings call
    response = client.embeddings.create(
        input=input_text,
        model=model,
        **kwargs
    )

    # 2) Extract usage
    usage_obj = getattr(response, "usage", None)
    if usage_obj:
        prompt_tokens = usage_obj.prompt_tokens
        total_tokens = usage_obj.total_tokens
    else:
        prompt_tokens = 0
        total_tokens = 0

    # 3) Calculate cost
    # For embeddings, you'll need the correct rate for your model
    # e.g. If it's $0.0001 per 1K tokens => cost_per_token=0.0000001
    cost_for_this_call = total_tokens * cost_per_token

    # 4) Insert usage log
    usage_log = OpenAIUsageLog(
        user_id=user_id,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=0,  # embeddings typically have no completion_tokens
        total_tokens=total_tokens,
        cost=cost_for_this_call,
        created_at=datetime.utcnow()
    )
    db_session.add(usage_log)

    # 5) Update user’s credits
    user.credits_remaining -= total_tokens

    db_session.commit()

    return response