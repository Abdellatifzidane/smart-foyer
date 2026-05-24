"""
Prompt template for receipt extraction
======================================
To add a new field:
  1. Add it to the SCHEMA description below.
  2. Add a matching field in ner/models.py with a default value.

The LLM is instructed to return strict JSON, with empty values
when a field cannot be confidently extracted.
"""

SYSTEM_PROMPT = """You are an expert French grocery receipt parser. You extract structured data from raw OCR text produced by PaddleOCR.

Output ONLY valid JSON. No prose, no explanation, no markdown.
If a value is missing or uncertain, return "" or 0. Do NOT invent data.

KEY RULES:
1. Prices use European format: "1,29", "1.29", " ,35", "0,35" -> convert to a float (1.29, 0.35).
2. The receipt total is the FINAL AMOUNT PAID by the customer (after discounts, before change).
3. Subtotals (Total Alimentaire, Total Non Aliment, Total Hygiene, Total TVA, etc.) are NOT the final total.
4. Long numbers (10+ digits) are barcodes / store IDs / SIRET / phone numbers - they are NEVER prices or totals.
5. Items are products the customer BUYS. Section labels and accounting lines are NOT items, namely:
   - "Total Alimentaire", "Total Non Aliment", "Total Hygiene", "Sous-total", "Total TVA"
   - "TVA", "TVA 5,5%", "TVA 20%"
   - "Titres Restaurants", "Carte", "Cartes Bancaires", "Especes", "CB Sans Contact"
   - "Nombre d'articles", "A Rendre", "Rendu", "Monnaie", "A payer", "TR Eligible"
   - Header lines: address, phone, SIRET, website URL, date, hours, cashier
6. Receipts are usually printed in two columns: product name on the LEFT, price on the RIGHT.
   The OCR text already groups them on the SAME line, separated by spaces (e.g. "Pain complet   0,35 A").
   Match each product to the price on the SAME line. The trailing single letter (A/B/C) is a VAT category tag,
   not part of the name.
7. BE EXHAUSTIVE: extract EVERY product line you see — a typical grocery receipt has 5 to 40 items.
   Do not skip a product just because its name looks unusual or has typos. As long as a line has
   a plausible product label + a price on the same line, include it.
8. Discount lines ("Reduction", "Remise", "X% Lidl Plus", "Bon de réduction") are NEGATIVE adjustments,
   not products. Skip them (do not include them as items).
9. Numbers labelled "Qty", "x2", "2x", or " 2 " followed by a unit price indicate quantity.
   The line total is what counts as `price`; if only the unit price is shown, use that and set quantity."""


# Schema description - kept aligned with ner/models.py
SCHEMA = """{
  "enseigne": "Store name (Carrefour, Monoprix, Lidl, Intermarche, Franprix, Leclerc, Auchan...). Detect from the header logo or address. String.",
  "date":     "Receipt date as YYYY-MM-DD if possible, otherwise as printed (e.g. '23/12/2024'). String.",
  "total":    "Final amount paid by the customer. Look for 'TOTAL A PAYER', 'MONTANT DU', 'TOTAL', 'NET A PAYER'. Number, NOT a barcode. Use dot as decimal separator.",
  "items": [
    {
      "name":     "Product name as printed (real product, not a section label, not a discount). String, trimmed, with the VAT-tag letter removed.",
      "price":    "Price for this line in euros (line total, not unit price). Number, dot decimal. Use 0 if no price is visible on the same line.",
      "quantity": "Quantity bought. Number. Default 1 if not specified."
    }
  ]
}"""


HEURISTICS = """How to find the TOTAL reliably:
- Search for keywords: TOTAL A PAYER, NET A PAYER, MONTANT DU, TOTAL DU, MONTANT TOTAL, A PAYER.
- The total is typically between 2 and 500 euros for a grocery receipt. Anything above 1000 is suspicious - probably a barcode misread as a number.
- The total is NEVER a 10+ digit number.
- If multiple plausible totals are visible, prefer the one labelled "TOTAL A PAYER", "A PAYER" or "NET A PAYER".

How to find ITEMS reliably:
- A real item has BOTH a product name AND a price on the same line.
- Each line you keep should have a price between 0.05 € and 200 €.
- Skip any line whose label starts with "TOTAL", "TVA", "SOUS-TOTAL", "CB", "ESPECES", "TITRES", "NOMBRE", "RENDU", "REDUCTION", "REMISE".
- Skip the store header (address, phone, SIRET, date) and footer (loyalty points, opening hours, thanks message).
- If the name has obvious OCR errors (Chocolat NoL → Chocolat Noel, pein → pain, Mardi → Mardi), KEEP the line — record the name AS PRINTED, do not correct it.

Validation:
- After extracting items, mentally sum their prices and verify the sum is close to the receipt total
  (within ~15% — discounts and rounding can cause small gaps).
- If the sum is far below the total, you probably MISSED some products. Re-scan the OCR text and add them."""


def build_user_prompt(ocr_text: str) -> str:
    """Build the user prompt with the OCR text embedded."""
    return f"""Extract the receipt data as JSON following this schema:

{SCHEMA}

{HEURISTICS}

OCR text of the receipt (may have noise and misread characters; columns are already merged on the same line):
\"\"\"
{ocr_text}
\"\"\"

Return ONLY the JSON object. Be EXHAUSTIVE — extract every product you can see."""
