# llm_wrappers.py

import decimal
from datetime import datetime
from flask import g
from openai import OpenAI
from models.sql_models import Users, OpenAIUsageLog
import os
from database.session import ScopedSession

api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

def call_openai_chat_create(
    user_id: int,
    model: str,
    messages: list,
    temperature: float = 0.7,
    **kwargs
):
    """
    Wrapper for client.chat.completions.create(...) that logs usage in openai_usage_logs
    and updates the user's cost/credits.
    """
    db_session = ScopedSession()
    try:
        # 1) Retrieve user
        user = db_session.query(Users).filter_by(user_id=user_id).first()
        if not user:
            raise ValueError(f"User not found (user_id={user_id}).")

        # 2) Call the OpenAI ChatCompletion endpoint
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            **kwargs
        )

        # 3) Extract usage
        usage_obj = getattr(response, "usage", None)
        if usage_obj:
            prompt_tokens = usage_obj.prompt_tokens
            completion_tokens = usage_obj.completion_tokens
            total_tokens = usage_obj.total_tokens
        else:
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0

        # 4) Calculate cost
        cost_per_prompt_token = decimal.Decimal("0.0000025")   # Example: $2.50 per 1M
        cost_per_completion_token = decimal.Decimal("0.00001") # Example: $10.00 per 1M

        prompt_cost = prompt_tokens * cost_per_prompt_token
        completion_cost = completion_tokens * cost_per_completion_token
        total_cost = prompt_cost + completion_cost

        # 5) Insert usage log
        usage_log = OpenAIUsageLog(
            user_id=user_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost=total_cost,
            created_at=datetime.utcnow()
        )
        db_session.add(usage_log)

        # 6) Update user credits
        user.credits_remaining -= total_tokens

        db_session.commit()

        return response

    except Exception as e:
        db_session.rollback()
        raise
    finally:
        db_session.close()

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
      3) Logs usage info in openai_usage_logs
      4) Updates user credits/cost
      5) Returns the raw response
    """
    db_session = ScopedSession()
    try:
        # 1) Retrieve user
        user = db_session.query(Users).filter_by(user_id=user_id).first()
        if not user:
            raise ValueError(f"User not found (user_id={user_id}).")

        # 2) Make the embeddings call
        response = client.embeddings.create(
            input=input_text,
            model=model,
            **kwargs
        )

        # 3) Extract usage
        usage_obj = getattr(response, "usage", None)
        if usage_obj:
            prompt_tokens = usage_obj.prompt_tokens
            total_tokens = usage_obj.total_tokens
        else:
            prompt_tokens = 0
            total_tokens = 0

        # 4) Calculate cost
        cost_for_this_call = total_tokens * cost_per_token

        # 5) Insert usage log
        usage_log = OpenAIUsageLog(
            user_id=user_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=0,
            total_tokens=total_tokens,
            cost=cost_for_this_call,
            created_at=datetime.utcnow()
        )
        db_session.add(usage_log)

        # 6) Update user credits
        user.credits_remaining -= total_tokens

        db_session.commit()
        return response

    except Exception as e:
        db_session.rollback()
        raise
    finally:
        db_session.close()

def call_openai_chat_parse(
    user_id: int,
    model: str,
    messages: list,
    response_format,
    cost_per_prompt_token: decimal.Decimal,
    cost_per_completion_token: decimal.Decimal,
    **kwargs
):
    """
    A wrapper for client.beta.chat.completions.parse(...)
    Logs usage in openai_usage_logs and updates user’s credits or balance.
    """
    db_session = ScopedSession()
    try:
        # 1) Retrieve user
        user = db_session.query(Users).filter_by(user_id=user_id).first()
        if not user:
            raise ValueError(f"User not found (user_id={user_id}).")

        # 2) Make the parse call
        response = client.beta.chat.completions.parse(
            model=model,
            messages=messages,
            response_format=response_format,
            **kwargs
        )

        # 3) Extract usage
        usage_obj = getattr(response, "usage", None)
        if usage_obj:
            prompt_tokens = usage_obj.prompt_tokens
            completion_tokens = usage_obj.completion_tokens
            total_tokens = usage_obj.total_tokens
        else:
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0

        # 4) Calculate cost
        prompt_cost = prompt_tokens * cost_per_prompt_token
        completion_cost = completion_tokens * cost_per_completion_token
        total_cost = prompt_cost + completion_cost

        # 5) Insert usage log
        usage_log = OpenAIUsageLog(
            user_id=user_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost=total_cost,
            created_at=datetime.utcnow()
        )
        db_session.add(usage_log)

        # 6) Update user’s credits
        user.credits_remaining -= total_tokens

        db_session.commit()
        return response

    except Exception as e:
        db_session.rollback()
        raise
    finally:
        db_session.close()