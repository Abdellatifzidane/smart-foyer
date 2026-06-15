"""
Tests OCR (non-régression) sur les images réelles de Photos/
============================================================
Vérifie que la pipeline OCR :
  - extrait un nombre raisonnable de lignes avec une bonne confiance,
  - que le prétraitement conservateur ne DÉTRUIT pas le contenu (au moins
    autant de signal qu'en brut),
  - que le filtrage de bruit n'élimine pas tout.

Le modèle PaddleOCR est chargé une seule fois (fixture module).
Lancement : pytest -q ocr/test_ocr.py -s
"""

from __future__ import annotations

import glob

import pytest

from ocr.paddle_ocr import ReceiptOCR


PHOTOS = sorted(glob.glob("Photos/*.png"))


@pytest.fixture(scope="module")
def ocr() -> ReceiptOCR:
    return ReceiptOCR(lang="fr")


@pytest.mark.skipif(not PHOTOS, reason="Aucune image dans Photos/")
def test_ocr_extracts_text(ocr: ReceiptOCR):
    # On prend les images les plus "riches" (vrais contenus, pas une icône).
    results = []
    for img in PHOTOS:
        res = ocr.extract(img, preprocess=True)
        results.append((img, len(res.lines), res.avg_confidence))
        print(f"{img.split('/')[-1][:12]}  lines={len(res.lines):3d}  conf={res.avg_confidence:.3f}")

    rich = [r for r in results if r[1] >= 8]
    assert rich, "Aucune image n'a produit de texte exploitable"
    # Les images riches doivent avoir une confiance correcte
    for img, n, conf in rich:
        assert conf >= 0.5, f"Confiance trop basse sur {img}: {conf:.2f}"


@pytest.mark.skipif(not PHOTOS, reason="Aucune image dans Photos/")
def test_preprocess_does_not_destroy_content(ocr: ReceiptOCR):
    """Le prétraitement ne doit pas faire perdre de contenu vs l'image brute."""
    # Image la plus riche
    best = max(PHOTOS, key=lambda p: len(ocr.extract(p, preprocess=False).lines))
    raw = ocr.extract(best, preprocess=False)
    pre = ocr.extract(best, preprocess=True)
    print(f"{best.split('/')[-1][:12]}  brut={len(raw.lines)}  prétraité={len(pre.lines)}")
    # Au moins 80 % du signal conservé (tolérance au filtrage de bruit)
    assert len(pre.lines) >= 0.8 * len(raw.lines)


@pytest.mark.skipif(not PHOTOS, reason="Aucune image dans Photos/")
def test_layout_merges_columns(ocr: ReceiptOCR):
    """Le texte layout-aware doit fusionner des colonnes (présence d'un
    séparateur multi-espaces sur au moins une ligne d'une image riche)."""
    best = max(PHOTOS, key=lambda p: len(ocr.extract(p, preprocess=True).lines))
    text = ocr.extract(best, preprocess=True).text
    assert any("   " in line for line in text.splitlines()), \
        "Aucune colonne fusionnée détectée (reconstruction layout défaillante)"
