"""
Prétraitement d'image avant OCR
===============================
PaddleOCR fait déjà beaucoup (redressement, orientation). On ajoute ici un
prétraitement **conservateur**, pensé pour les vraies photos de tickets
thermiques (texte petit, papier froissé, faible contraste) SANS dégrader les
images déjà nettes :

  1. Respect de l'orientation EXIF (photos de téléphone).
  2. Upscale des images trop petites (le texte minuscule devient lisible) et
     downscale des images énormes (RAM).
  3. Niveaux de gris + autocontraste léger + accentuation douce (unsharp).

Pas de binarisation agressive : PaddleOCR est entraîné sur des images
naturelles, un seuillage dur lui ferait plus de mal que de bien.
"""

from __future__ import annotations

from PIL import Image, ImageFilter, ImageOps


# Bornes de taille (côté le plus long).
MIN_SIDE = 1100   # en-dessous, on agrandit (petit ticket photographié de loin)
MAX_SIDE = 2200   # au-dessus, on réduit (limite RAM)


def preprocess_for_ocr(
    image: Image.Image,
    min_side: int = MIN_SIDE,
    max_side: int = MAX_SIDE,
) -> Image.Image:
    """Renvoie une copie prétraitée (RGB) prête pour PaddleOCR."""
    im = ImageOps.exif_transpose(image)  # honore la rotation EXIF
    im = im.convert("RGB")

    w, h = im.size
    side = max(w, h)
    if side > 0 and side < min_side:
        scale = min_side / side
        im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    elif side > max_side:
        scale = max_side / side
        im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)

    # Niveaux de gris + autocontraste léger (cutoff faible pour ne pas écraser)
    gray = ImageOps.grayscale(im)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    # Accentuation douce : rend les caractères plus nets sans halo
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1.2, percent=80, threshold=2))

    # PaddleOCR attend 3 canaux
    return gray.convert("RGB")


def preprocess_file(src_path: str, dst_path: str) -> str:
    """Prétraite un fichier image et écrit le résultat en JPEG. Renvoie dst."""
    with Image.open(src_path) as im:
        out = preprocess_for_ocr(im)
    out.save(dst_path, "JPEG", quality=92)
    return dst_path
