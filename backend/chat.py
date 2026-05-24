"""
RAG conversational agent.
=========================
Turns a free-form user question into a grounded answer based on the
receipts stored in data/receipts/. The agent never invents data: it only
uses the context built from the user's actual history.

How it works:
  1. Load all stored receipts.
  2. Compute aggregate stats (totals, by enseigne, by month).
  3. Inject a compact text representation of that data as context.
  4. Send the (system + context + question) prompt to Groq.
  5. Return the LLM answer.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq


load_dotenv(override=True)


# ─── Configuration ────────────────────────────────────────────────────
DEFAULT_MODEL = "llama-3.3-70b-versatile"
MAX_RECEIPTS_IN_CONTEXT = 25  # keep the prompt small for fast responses


_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to your environment or to a .env "
                "file at the project root."
            )
        _client = Groq(api_key=key)
    return _client


SYSTEM_PROMPT = """Tu es SmartFoyer Conseiller, un assistant financier qui aide l'utilisateur a comprendre et optimiser ses depenses de courses alimentaires.

Tu reponds en francais, de maniere concise (3-6 phrases maximum), claire, et amicale.

Tu as access UNIQUEMENT aux donnees fournies dans la section CONTEXTE ci-dessous. Reponds en te basant strictement sur ces donnees.

REGLES :
- Cite des montants et enseignes precis quand c'est utile.
- Si la donnee demandee n'est pas dans le contexte, dis-le honnetement ("Je n'ai pas cette information dans ton historique").
- Ne donne JAMAIS de chiffres inventes ou approximatifs si ils ne sont pas dans le contexte.
- Quand l'utilisateur demande des conseils, base-toi sur les patterns reels que tu vois dans ses donnees."""


def _load_receipts(receipts_dir: Path) -> list[dict]:
    """Read every stored receipt, newest first."""
    if not receipts_dir.exists():
        return []
    receipts = []
    for path in receipts_dir.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                receipts.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue
    receipts.sort(key=lambda r: r.get("scanned_at", ""), reverse=True)
    return receipts


def _aggregate(receipts: list[dict]) -> dict:
    """Compute the aggregate stats used in the context."""
    by_enseigne: dict[str, dict] = defaultdict(lambda: {"total": 0.0, "n": 0})
    by_month: dict[str, float] = defaultdict(float)
    item_frequency: dict[str, int] = defaultdict(int)
    total_spent = 0.0
    total_savings = 0.0

    for r in receipts:
        receipt = r.get("receipt") or {}
        total = float(receipt.get("total") or 0)
        total_spent += total
        total_savings += float(r.get("total_savings") or 0)

        ens = (receipt.get("enseigne") or "Inconnu").strip()
        by_enseigne[ens]["total"] += total
        by_enseigne[ens]["n"] += 1

        month = (r.get("scanned_at") or "")[:7]  # YYYY-MM
        if month:
            by_month[month] += total

        for item in receipt.get("items") or []:
            name = (item.get("name") or "").strip()
            if name:
                item_frequency[name] += 1

    return {
        "n_receipts": len(receipts),
        "total_spent": round(total_spent, 2),
        "total_savings": round(total_savings, 2),
        "by_enseigne": {k: {"total": round(v["total"], 2), "n": v["n"]}
                        for k, v in by_enseigne.items()},
        "by_month": {k: round(v, 2) for k, v in sorted(by_month.items())},
        "top_items": sorted(item_frequency.items(), key=lambda x: -x[1])[:8],
    }


def _build_context(receipts_dir: Path) -> str:
    """Compose the text block fed to the LLM as factual context."""
    receipts = _load_receipts(receipts_dir)
    if not receipts:
        return "L'utilisateur n'a encore scanne aucun ticket."

    stats = _aggregate(receipts)

    lines = []
    lines.append("=== STATISTIQUES GLOBALES ===")
    lines.append(f"Aujourd'hui : {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(f"Nombre de tickets    : {stats['n_receipts']}")
    lines.append(f"Total depense        : {stats['total_spent']:.2f} EUR")
    lines.append(f"Economies cumulees   : {stats['total_savings']:.2f} EUR")
    lines.append("")

    lines.append("=== DEPENSES PAR ENSEIGNE ===")
    sorted_ens = sorted(stats["by_enseigne"].items(),
                        key=lambda x: -x[1]["total"])
    for ens, info in sorted_ens:
        avg = info["total"] / info["n"] if info["n"] else 0
        lines.append(f"  {ens:<14}  {info['total']:>7.2f} EUR  "
                     f"({info['n']} tickets, moyenne {avg:.2f} EUR)")
    lines.append("")

    lines.append("=== DEPENSES PAR MOIS ===")
    for month, total in stats["by_month"].items():
        lines.append(f"  {month}  {total:>7.2f} EUR")
    lines.append("")

    if stats["top_items"]:
        lines.append("=== PRODUITS LES PLUS ACHETES ===")
        for name, freq in stats["top_items"]:
            lines.append(f"  {freq}x  {name[:60]}")
        lines.append("")

    lines.append(f"=== {min(len(receipts), MAX_RECEIPTS_IN_CONTEXT)} DERNIERS TICKETS ===")
    for r in receipts[:MAX_RECEIPTS_IN_CONTEXT]:
        receipt = r.get("receipt") or {}
        ens = receipt.get("enseigne") or "?"
        date = receipt.get("date") or (r.get("scanned_at", "")[:10])
        total = float(receipt.get("total") or 0)
        n = len(receipt.get("items") or [])
        lines.append(f"  {date}  {ens:<14}  {total:>7.2f} EUR  ({n} produits)")

    return "\n".join(lines)


def answer(question: str,
           receipts_dir: Path,
           history: list[dict] | None = None,
           model: str = DEFAULT_MODEL) -> str:
    """Generate an answer to `question` grounded in the stored receipts.

    Args:
        question: the user's natural-language question (French).
        receipts_dir: where to read the user's receipts from.
        history: optional prior turns [{"role": "user"|"assistant", "content": "..."}]
        model: Groq model name.

    Returns:
        The assistant's reply (plain text).
    """
    context = _build_context(receipts_dir)

    messages: list[dict] = [
        {"role": "system",
         "content": f"{SYSTEM_PROMPT}\n\n=== CONTEXTE ===\n{context}"},
    ]
    if history:
        # keep the last ~8 turns to limit prompt size
        messages.extend(history[-8:])
    messages.append({"role": "user", "content": question})

    response = _get_client().chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.2,  # a tiny bit of variety but stays factual
    )
    return (response.choices[0].message.content or "").strip()
