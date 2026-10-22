import json
import logging
import os
import re
import time
from typing import Any, Dict, Optional
import requests

logger = logging.getLogger(__name__)

def query_llm_json(prompt: str, config: Optional[Dict[str, Any]] = None) -> Any:
    """
    Central LLM call function with structured JSON output, timeouts,
    429 rate limit backoff, and quota exhaustion handling.
    No other module may call an LLM API directly.
    """
    cfg = config or {}
    provider = cfg.get("LLM_PROVIDER") or os.environ.get("LLM_PROVIDER", "gemini").lower()

    if provider == "groq":
        raise ValueError("Groq provider is not configured. Please switch LLM_PROVIDER to 'gemini'.")
    elif provider != "gemini":
        raise ValueError(f"Unsupported LLM provider '{provider}'. Supported providers: 'gemini', 'groq'.")

    api_key = cfg.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured in the environment.")

    model = cfg.get("GEMINI_MODEL") or os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-lite").strip()
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1,
        }
    }

    headers = {"Content-Type": "application/json"}
    max_retries = 2
    timeout = 25  # Well below Gunicorn 120s limit

    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)

            # Check for Rate Limit (HTTP 429)
            if resp.status_code == 429:
                if attempt < max_retries:
                    retry_after = resp.headers.get("Retry-After")
                    sleep_time = int(retry_after) if retry_after and retry_after.isdigit() else (2 ** (attempt + 1))
                    logger.warning(f"Gemini API rate limit hit (429). Retrying in {sleep_time}s (attempt {attempt + 1}/{max_retries})...")
                    time.sleep(sleep_time)
                    continue
                else:
                    raise RuntimeError("Gemini API rate limit hit (429). Please wait a moment and try again.")

            # Check for quota exhaustion or bad request
            if resp.status_code == 403 or "RESOURCE_EXHAUSTED" in resp.text:
                raise RuntimeError("Google Gemini daily quota exhausted or unauthorized. Please check your API Studio quota.")

            resp.raise_for_status()
            data = resp.json()

            # Extract generated content
            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError("Gemini returned no candidates in response.")

            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts or "text" not in parts[0]:
                raise RuntimeError("Gemini response missing text part.")

            raw_text = parts[0]["text"].strip()

            # Clean markdown code fences if model returned ```json ... ```
            clean_json = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.MULTILINE)
            clean_json = re.sub(r"\s*```$", "", clean_json, flags=re.MULTILINE).strip()

            return json.loads(clean_json)

        except requests.exceptions.Timeout:
            if attempt < max_retries:
                logger.warning(f"Gemini API timeout after {timeout}s. Retrying...")
                time.sleep(1)
                continue
            raise RuntimeError("Gemini API request timed out after multiple attempts.")
        except json.JSONDecodeError as je:
            logger.error(f"Failed to parse LLM JSON response: {je}. Raw output: {raw_text[:200]}")
            raise RuntimeError(f"Model failed to return valid JSON: {str(je)}")
        except requests.exceptions.RequestException as re_err:
            if attempt < max_retries and getattr(re_err.response, 'status_code', None) == 429:
                time.sleep(2)
                continue
            logger.error(f"Gemini API request error: {re_err}")
            raise RuntimeError(f"Error communicating with Gemini API: {str(re_err)}")
