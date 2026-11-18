"""Rule-based + versioned-dictionary Indonesian ingredient text normalizer (FR-A1)."""

from __future__ import annotations

import csv
import html
import re
import unicodedata
from pathlib import Path

_UNITS = (
    "sendok makan",
    "sendok teh",
    "sdm",
    "sdt",
    "gram",
    "gr",
    "kg",
    "g",
    "ons",
    "liter",
    "ltr",
    "ml",
    "l",
    "buah",
    "bh",
    "butir",
    "btr",
    "siung",
    "sg",
    "lembar",
    "lmbr",
    "lbr",
    "batang",
    "btg",
    "ikat",
    "ikt",
    "ekor",
    "potong",
    "ptg",
    "keping",
    "kpg",
    "lonjor",
    "bungkus",
    "bks",
    "sachet",
    "sct",
    "pcs",
    "kotak",
    "papan",
    "cup",
    "ruas jari",
    "seruas jari",
    "seruas",
    "ruas",
    "jari",
    "jempol",
    "ibu jari",
    "seujung",
    "sejumput",
    "sedikit",
    "segenggam",
    "beberapa",
    "bbrp",
    "bagian",
    "genggam",
    "jumput",
    "cm",
    "gelas",
    "gls",
    "cangkir",
    "tangkai",
    "tgk",
    "biji",
    "helai",
    "kuntum",
    "pucuk",
    "bonggol",
    "sisir",
    "kaleng",
    "klg",
    "botol",
    "btl",
    "mangkok",
    "piring",
    "cc",
    "sd",
)

_UNIT_PATTERN = r"(?:" + "|".join(sorted(_UNITS, key=len, reverse=True)) + r")\.?"

_LEADING_QTY_RE = re.compile(
    rf"^\s*(?:(?:kurang\s+lebih|sekitar|kira-kira|secukupnya|sesuai\s+selera)\s+)?"
    rf"(?:[0-9]+(?:\s*[,./-]\s*[0-9]+)*\s*)?"
    rf"(?:{_UNIT_PATTERN}\b\s*)*",
    flags=re.IGNORECASE,
)

_PAREN_RE = re.compile(r"\([^)]*\)")

_NOISE_PHRASES_RE = re.compile(
    r"\b(?:"
    r"secukupnya|sesuai selera|selera|opsional|optional|tidak pakai|skip|"
    r"(?:untuk|utk)\s+(?:menumis|menggoreng|goreng|rebus|merebus|taburan|olesan|baluran|"
    r"pelengkap|sambal|bumbu|kuah|marinasi|celupan|pencelup)|"
    r"uk\.?\s*sedang|uk\.?\s*kecil|uk\.?\s*besar|ukuran sedang|ukuran kecil|ukuran besar|"
    r"cuci bersih|kupas bersih|potong dadu|potong kecil|potong-potong|potong2|dipotong|"
    r"iris serong|iris tipis|iris-iris|iris2|diiris tipis|diiris|"
    r"cincang halus|dicincang|haluskan|dihaluskan|"
    r"uleg kasar|ulek kasar|memarkan|geprek|digeprek|dimemarkan|"
    r"kocok lepas|dikocok lepas|diseduh|dilarutkan|direbus|digoreng|disangrai|"
    r"sisir halus|bumbu iris|bumbu cemplung|bumbu halus|bahan pelengkap|"
    r"rose brand|bango|sasa|kara|kobe|indofood|abc|bimoli|filma|sania|blue band"
    r")\b",
    flags=re.IGNORECASE,
)

_ACTION_ONLY_TOKENS = {
    "haluskan",
    "dihaluskan",
    "iris",
    "irisan",
    "iris tipis",
    "iris serong",
    "iris2",
    "iris-iris",
    "cincang",
    "potong",
    "potong2",
    "potong-potong",
    "dadu",
    "korek api",
    "serong",
    "belah",
    "rebus",
    "goreng",
    "sangrai",
    "bakar",
    "serut",
    "kupas",
    "cuci",
    "bersihkan",
    "tiriskan",
    "memarkan",
    "geprek",
    "parut",
    "sisir",
    "rajang",
    "tumis",
    "suwir",
    "secukupnya",
    "sesuai selera",
    "opsional",
    "pelengkap",
    "tambahan",
    "isian",
    "taburan",
    "bumbu",
    "bumbu halus",
    "bumbu iris",
    "bumbu cemplung",
    "bahan",
    "bahan pelengkap",
    "bahan-bahan",
    "kecil",
    "kecil2",
    "sedang",
    "besar",
    "tipis",
    "tipis2",
    "halus",
    "kasar",
    "memanjang",
    "merah",
    "putih",
    "hijau",
    "lalu",
    "jadi",
    "yang",
    "yg",
    "saya",
    "dulu",
    "biarkan",
    "dapur",
    "lainnya",
    "menumis",
    "amp",
}

_TRAILING_MODIFIERS = (
    "bubuk",
    "halus",
    "kasar",
    "instan",
    "instant",
    "segar",
    "kering",
    "mentah",
    "matang",
    "kecil",
    "sedang",
    "besar",
    "utuh",
    "iris",
    "cincang",
    "kupas",
    "geprek",
    "memar",
    "parut",
    "sisir",
    "rajang",
    "sangrai",
    "rebus",
    "kukus",
    "bakar",
    "panggang",
    "tumis",
    "tumbuk",
    "ulek",
    "uleg",
    "memanjang",
    "sobek",
    "sobek2",
    "di",
    "yg",
    "yang",
    "sudah",
    "goreng",
    "kekentalan",
    "kemasan",
)

_TOKEN_NORMALIZATIONS = {
    "cabe": "cabai",
    "kriting": "keriting",
    "bwg": "bawang",
    "bwng": "bawang",
    "bw": "bawang",
    "saos": "saus",
    "telor": "telur",
    "sere": "serai",
    "sereh": "serai",
    "margarine": "margarin",
    "jinten": "jintan",
    "cengkeh": "cengkih",
    "bombai": "bombay",
    "bombang": "bombay",
    "trigu": "terigu",
    "meizena": "maizena",
    "orens": "merah",
    "orange": "merah",
    "santen": "santan",
    "gulmer": "gula merah",
    "gulpas": "gula pasir",
    "bawput": "bawang putih",
    "bawah": "bawang",
    "ijo": "hijau",
}


def load_synonym_map(path: Path) -> dict[str, str]:
    """Load canonical ingredient synonym dictionary from CSV."""
    if not path.is_file():
        raise FileNotFoundError(f"Synonym map not found: {path}")
    mapping: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            var = row["variant"].strip().lower()
            can = row["canonical"].strip().lower()
            if var and can:
                mapping[var] = can
    return mapping


def _clean_single_fragment(fragment: str, synonyms: dict[str, str]) -> str | None:
    """Normalize a single ingredient fragment into canonical form or None if noise."""
    text = html.unescape(fragment)
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[^a-z0-9\s/.,&-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .,-/&")
    if not text:
        return None

    for _ in range(3):
        stripped = _LEADING_QTY_RE.sub("", text).strip(" .,-/&")
        if stripped == text:
            break
        text = stripped

    text = _NOISE_PHRASES_RE.sub(" ", text)
    # Remove glued number+unit like "65ml", "200gr", "1kg".
    text = re.sub(
        rf"\b[0-9]+(?:\s*[,./-]\s*[0-9]+)*\s*(?:{_UNIT_PATTERN})?\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(rf"\b{_UNIT_PATTERN}\b", " ", text, flags=re.IGNORECASE)
    text = text.replace(".", " ")
    text = re.sub(r"\s+", " ", text).strip(" .,-/&")

    if not text or text in _ACTION_ONLY_TOKENS:
        return None

    # Normalize common Indonesian culinary spelling abbreviations per token.
    norm_tokens = [_TOKEN_NORMALIZATIONS.get(tok, tok) for tok in text.split()]
    # Strip leading action tokens like "iris bawang bombay" or "goreng kacang tanah".
    while len(norm_tokens) > 1 and norm_tokens[0] in _ACTION_ONLY_TOKENS:
        norm_tokens.pop(0)
    text = " ".join(norm_tokens)

    if text in synonyms:
        return synonyms[text]

    words = text.split()
    while len(words) > 1 and words[-1] in _TRAILING_MODIFIERS:
        candidate = " ".join(words[:-1])
        if candidate in synonyms:
            return synonyms[candidate]
        words.pop()
    reduced = " ".join(words)
    if reduced in synonyms:
        return synonyms[reduced]

    # Canonicalize a few frequent word-order variants after normalization.
    if reduced in {"cabai keriting merah", "cabai merah panjang"}:
        return "cabai merah keriting"
    if reduced in {"cabai besar merah", "cabai merah tanjung"}:
        return "cabai merah besar"
    if reduced in {"cabai merah rawit"}:
        return "cabai rawit merah"

    if reduced in _ACTION_ONLY_TOKENS or len(reduced) < 2 or len(words) > 5:
        return None
    return reduced


def normalize_ingredient_line(raw_line: str, synonyms: dict[str, str]) -> list[str]:
    """Normalize a raw recipe ingredient string into 0 or more canonical ingredients.

    Handles HTML entities, parentheticals, multi-ingredient lines separated by `,`, `/`, or `&`,
    quantities/units, preparation verbs, and synonym mapping.
    """
    if not raw_line or not isinstance(raw_line, str):
        return []

    text = html.unescape(raw_line)
    text = _PAREN_RE.sub(" ", text)
    # Split space-only paired staples like "garam gula" / "gula garam".
    text = re.sub(r"\b(garam)\s+(gula(?:\s+pasir)?)\b", r"\1, \2", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(gula(?:\s+pasir)?)\s+(garam)\b", r"\1, \2", text, flags=re.IGNORECASE)
    parts = re.split(r"[,;/&]|\s+\bdan\b\s+|\s+\batau\b\s+", text, flags=re.IGNORECASE)
    results: list[str] = []
    seen: set[str] = set()
    for part in parts:
        cleaned = _clean_single_fragment(part, synonyms)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            results.append(cleaned)
    return results
