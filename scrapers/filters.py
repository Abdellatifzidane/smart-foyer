"""
Shared product filters used by every scraper.

The goal of `is_food_product` is to keep the catalog focused on grocery items
so the matching step does not propose absurd alternatives (chaussures, valises,
meubles, etc.) for a food product on a receipt.

To extend the filter, just add a keyword to NON_FOOD_KEYWORDS below.
The match is a substring check on the lowercased product name.
"""

NON_FOOD_KEYWORDS = {
    # ── vêtements / accessoires ──
    "chaussure", "chaussures", "basket", "sandale", "chausson",
    "veste", "manteau", "pull", "sweat", "t-shirt", "t shirt", "tee-shirt",
    "pantalon", "jean", "jeans", "robe", "jupe", "short", "chemise", "blouse",
    "chapeau", "casquette", "visiere", "visière", "echarpe", "écharpe",
    "gants", "ceinture", "cravate", "chaussettes", "collant", "lingerie",
    "pyjama", "peignoir", "maillot", "soutien-gorge", "boxer", "slip",
    "doudoune", "polaire", "blouson", "anorak", "parka", "trench",
    "tunique", "combinaison", "salopette", "bermuda", "bonnet",
    # ── bagages et rangement ──
    "valise", "bagage", "sac de voyage", "sac a dos", "sac à dos",
    "coffre", "coffret", "rangement", "boite de rangement", "boîte de rangement",
    "desserte", "armoire",
    # ── maison / literie ──
    "couette", "oreiller", "couvre lit", "plaid", "drap", "parure de lit",
    "rideau", "rideaux", "tapis", "carpette",
    "meuble", "chaise", "fauteuil", "etagere", "étagère",
    "matelas", "sommier", "canape", "canapé",
    "coussin", "panier", "corbeille", "porte-manteau",
    # ── décoration ──
    "bougie", "encens", "decoration", "décoration", "cadre photo",
    "vase", "miroir", "horloge", "lampe", "luminaire", "guirlande",
    # ── cuisine / vaisselle / électroménager ──
    "plat a four", "plat à four", "moule a", "moule à",
    "casserole", "poele", "poêle", "couteau", "couteaux", "fourchette",
    "assiette", "assiettes", "tasse", "saladier", "couvert", "couverts",
    "machine a coudre", "machine à coudre", "robot menager", "robot ménager",
    "aspirateur", "fer a repasser", "fer à repasser", "bouilloire",
    "grille pain", "cafetiere", "cafetière", "blender", "mixeur",
    "moulin a", "moulin à", "plastifieuse",
    "barbecue", "rechaud", "réchaud", "plancha",
    # ── salle de bain / plomberie ──
    "mitigeur", "robinet", "lavabo", "douchette", "pommeau",
    # ── high-tech / electronique ──
    "barre de son", "enceinte", "ecouteurs", "écouteurs", "televiseur",
    "téléviseur", "tablette tactile", "smartphone", "chargeur",
    "haltere", "haltère", "tapis de course",
    # ── jardin / plein air ──
    "parterre", "jardiniere", "jardinière", "serre de jardin",
    # ── jardin / bricolage / extérieur ──
    "outil", "tournevis", "marteau", "scie", "perceuse",
    "echelle", "échelle", "tuyau", "tondeuse",
    "tente", "transat", "parasol", "hamac", "balancelle",
    # ── jouets / enfant / loisirs ──
    "jouet", "jouets", "poupee", "poupée", "peluche",
    "poussette", "biberon", "lit bebe", "lit bébé", "siege auto", "siège auto",
    "trottinette", "velo", "vélo",
    "pistolet", "piste a billes", "piste à billes", "billes", "puzzle",
    "trampoline", "piscine", "gonflable", "deguisement", "déguisement",
    "cerf-volant", "cerf volant", "drone", "circuit voiture", "figurine",
    "jeu de societe", "jeu de société", "coloriage", "pataugeoire",
    # ── papeterie / informatique ──
    "stylo", "cahier", "classeur", "agenda", "feutre",
    "imprimante", "cartouche", "clavier", "souris", "casque",
    # ── cosmétiques / maquillage ──
    "maquillage", "make up", "make-up", "rouge a levres", "rouge à lèvres",
    "mascara", "fond de teint", "ombre a paupiere", "ombre à paupière",
    "vernis", "fard", "anticerne", "anti-cerne", "blush", "eyeliner",
    "crayon yeux", "poudre libre", "highlighter", "demaquillant", "démaquillant",
    "parfum", "eau de toilette", "eau de parfum", "cologne",
    # ── soin / parapharmacie ──
    "creme visage", "crème visage", "creme anti", "crème anti", "soin visage",
    "soin contour", "serum", "sérum", "lotion", "tonique", "gommage",
    "masque visage", "creme mains", "crème mains", "creme corps", "crème corps",
    "shampoing", "shampooing", "apres-shampoing", "après-shampoing",
    "apres shampoing", "soin cheveux", "laque", "gel coiffant", "cire cheveux",
    "coloration", "teinture", "vitamine", "complement alimentaire",
    "complément alimentaire", "gelule", "gélule", "comprime", "comprimé",
    "pansement", "compresse", "serum physiologique", "spray nasal",
    "creme solaire", "crème solaire", "autobronzant", "epilation", "épilation",
    "cire epil", "cire épil", "rasoir", "mousse a raser", "mousse à raser",
    "deodorant", "déodorant", "anti-transpirant", "antitranspirant",
    "manucure", "pedicure", "pédicure", "lime a ongles", "lime à ongles",
    "coton tige", "coton-tige", "lingette demaquillante",
    # ── divers non-alimentaire ──
    "vetement", "vêtement", "bijou", "montre", "lunettes",
    "set manucure", "trousse",
}


def is_food_product(name: str) -> bool:
    """Return False if the product name contains any non-food keyword."""
    if not name:
        return False
    # Normalize hyphens to spaces so "siège-auto" matches the "siège auto" keyword
    lowered = name.lower().replace("-", " ")
    return not any(kw in lowered for kw in NON_FOOD_KEYWORDS)
