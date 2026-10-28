
import os
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from shared.token_usage import log_token_usage


T = TypeVar("T", bound=BaseModel)


def generate_json(
    contents,
    response_model: type[T],
    model: str,
    system_instruction: str | None = None,
    enforce_schema: bool = True,
) -> T:

    with genai.Client(
        api_key=os.getenv("GEMINI_API_KEY"),
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(
                attempts=4,
                initial_delay=1,
                max_delay=20,
            )
        ),
    ) as client:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=response_model if enforce_schema else None,
                temperature=0,
            ),
        )

    log_token_usage(response.usage_metadata)

    if not response.text:
        raise ValueError("Gemini returned an empty response")

    return response_model.model_validate_json(response.text)
