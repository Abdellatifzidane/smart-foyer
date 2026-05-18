"""
Prompt template for receipt extraction
======================================
To add a new field:
  1. Add it to the SCHEMA description below.
  2. Add a matching field in ner/models.py with a default value.

The LLM is instructed to return strict JSON, with empty values
when a field cannot be confidently extracted.
"""

SYSTEM_PROMPT = """You are an expert French grocery receipt parser. You extract structured data from raw OCR text.

Output ONLY valid JSON. No prose, no explanation, no markdown.
If a value is missing or uncertain, return "" or 0. Do NOT invent data.

KEY RULES:
1. Prices use European format: "1,29" or "1.29" -> convert to 1.29.
2. The receipt total is the FINAL AMOUNT PAID by the customer (after discounts, before change).
3. Subtotals (Total Alimentaire, Total Non Aliment, Total Hygiene, Total TVA, etc.) are NOT the final total.
4. Long numbers (10+ digits) are barcodes / store IDs / SIRET / phone numbers - they are NEVER prices or totals.
5. Items are products you BUY. Section labels and accounting lines are NOT items, namely:
   - "Total Alimentaire", "Total Non Aliment", "Total Hygiene", "Sous-total"
   - "TVA", "TVA 5,5%", "TVA 20%", "Total TVA"
   - "Titres Restaurants", "Cartes Bancaires", "Especes", "CB Sans Contact"
   - "Nombre d'articles", "A Rendre", "Rendu", "Monnaie"
6. Receipts are often printed in two columns: product name on the left, price on the right.
   Match each product to the price on the SAME line."""


# Schema description - kept aligned with ner/models.py
SCHEMA = """{
  "enseigne": "Store name (Carrefour, Monoprix, Lidl, Intermarche, Franprix, Leclerc, Auchan...). String.",
  "date":     "Receipt date as YYYY-MM-DD if possible, otherwise as printed. String.",
  "total":    "Final amount paid by the customer. Look for 'TOTAL A PAYER', 'MONTANT DU', 'TOTAL', 'NET A PAYER'. Number, NOT a barcode. Use dot as decimal separator.",
  "items": [
    {
      "name":     "Product name as printed (real product, not a section label). String.",
      "price":    "Price for this line in euros. Number, dot decimal. Use 0 if no price is visible on the same line.",
      "quantity": "Quantity bought. Number. Default 1 if not specified."
    }
  ]
}"""


HEURISTICS = """How to find the TOTAL reliably:
- Search for keywords: TOTAL A PAYER, NET A PAYER, MONTANT DU, TOTAL DU, MONTANT TOTAL.
- The total is typically between 5 and 500 euros for a grocery receipt. Anything above 1000 is suspicious - probably a barcode misread as a number.
- The total is NEVER a 10+ digit number.
- If multiple plausible totals are visible, prefer the one labelled "TOTAL A PAYER" or "NET A PAYER".

How to find ITEMS reliably:
- A real item has BOTH a product name AND a price on the same line (or very close).
- Skip any line whose label starts with "TOTAL", "TVA", "SOUS-TOTAL", "CB", "ESPECES", "TITRES", "NOMBRE", "RENDU".
- Skip the store header (address, phone, SIRET, date)."""


def build_user_prompt(ocr_text: str) -> str:
    """Build the user prompt with the OCR text embedded."""
    return f"""Extract the receipt data as JSON following this schema:

{SCHEMA}

{HEURISTICS}

OCR text of the receipt (may have noise and misread characters):
\"\"\"
{ocr_text}
\"\"\"

Return ONLY the JSON object."""
