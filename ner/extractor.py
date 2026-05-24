"""
NER extractor using Groq
========================
Sends OCR text to a Groq-hosted LLM and parses the JSON response
into a Receipt object.

Prerequisites:
  - GROQ_API_KEY set in the environment (or in a .env file at the project root).

Usage:
  from ner.extractor import GroqExtractor
  extractor = GroqExtractor(model="llama-3.3-70b-versatile")
  receipt = extractor.extract(ocr_text)
  print(receipt.to_json())
"""

from __future__ import annotations

import json
import os
import re

from dotenv import load_dotenv
from groq import Groq

from ner.models import Receipt
from ner.prompt import SYSTEM_PROMPT, build_user_prompt


load_dotenv(override=True)


DEFAULT_MODEL = "llama-3.3-70b-versatile"


class GroqExtractor:
    """Wraps a Groq chat call for structured receipt extraction."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        temperature: float = 0.0,
    ):
        """
        Args:
            model: Groq model name (e.g. "llama-3.3-70b-versatile", "llama-3.1-8b-instant").
            api_key: Groq API key. Defaults to the GROQ_API_KEY environment variable.
            temperature: 0.0 for deterministic extraction.
        """
        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to your environment or to a .env "
                "file at the project root."
            )
        self.model = model
        self.temperature = temperature
        self.client = Groq(api_key=key)

    def extract(self, ocr_text: str) -> Receipt:
        """Run NER extraction on raw OCR text and return a Receipt."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(ocr_text)},
            ],
            response_format={"type": "json_object"},
            temperature=self.temperature,
        )

        raw = response.choices[0].message.content or ""
        data = _parse_json(raw)
        return Receipt.from_dict(data)


# Back-compat alias so older imports keep working.
OllamaExtractor = GroqExtractor


def _parse_json(raw: str) -> dict:
    """Parse the model output, tolerating stray text around the JSON block."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return {}
