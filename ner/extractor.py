"""
NER extractor using a local LLM (Ollama)
========================================
Sends OCR text to a local Ollama model and parses the JSON response
into a Receipt object.

Prerequisites:
  - Ollama installed and running locally (default: http://localhost:11434)
  - A model pulled, e.g.:  ollama pull llama3.1:8b

Usage:
  from ner.extractor import OllamaExtractor
  extractor = OllamaExtractor(model="llama3.1:8b")
  receipt = extractor.extract(ocr_text)
  print(receipt.to_json())
"""

from __future__ import annotations

import json
import re

import ollama

from ner.models import Receipt
from ner.prompt import SYSTEM_PROMPT, build_user_prompt


class OllamaExtractor:
    """Wraps an Ollama chat call for structured receipt extraction."""

    def __init__(self, model: str = "llama3.1:8b", host: str | None = None, temperature: float = 0.0):
        """
        Args:
            model: Ollama model name (must be pulled locally).
            host:  Custom Ollama host (default: env OLLAMA_HOST or localhost:11434).
            temperature: 0.0 for deterministic extraction.
        """
        self.model = model
        self.temperature = temperature
        self.client = ollama.Client(host=host) if host else ollama.Client()

    def extract(self, ocr_text: str) -> Receipt:
        """Run NER extraction on raw OCR text and return a Receipt."""
        response = self.client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(ocr_text)},
            ],
            format="json",  # native JSON mode in Ollama
            options={"temperature": self.temperature},
        )

        raw = response["message"]["content"]
        data = _parse_json(raw)
        return Receipt.from_dict(data)


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
