"""Language checks for job ads, without extra dependencies.

ad_language(text)        -> "de", "en" or "" (unknown / mixed / too short)
requires(text, language) -> True if the ad asks for fluency in `language`
                            ("fluent German", "Deutsch C1", "verhandlungssicheres
                            Deutsch"...), but not when it is only a plus.

Profile options (config.yaml):
  skip_ad_languages: [de]      # drop ads written in German (bilingual ads are kept)
  skip_if_requires: [German]   # drop ads that require fluent German
"""
from __future__ import annotations

import re

# very common words that are (nearly) exclusive to each language
_STOP = {
    "de": set("und der die das mit für wir sie ist ein eine einen auf von zu den dem im bei oder nicht auch "
              "unsere unser deine dein du ihr ihre sowie wird werden als über nach haben bist".split()),
    "en": set("and the with for we you is a an of to in our your are on or will be as at from this that "
              "have has who what about".split()),
}
_WORD = re.compile(r"[a-zäöüß]+")


def ad_language(text: str, min_words: int = 40) -> str:
    """Dominant language of the ad text, or "" if unclear.

    "de" only when German clearly dominates (ads with an English version too are
    not German-only); short texts (titles, teasers) return ""."""
    words = _WORD.findall((text or "").lower())
    if len(words) < min_words:
        return ""
    de = sum(w in _STOP["de"] for w in words)
    en = sum(w in _STOP["en"] for w in words)
    if de >= 10 and de >= 3 * en:
        return "de"
    if en >= 10 and en >= 3 * de:
        return "en"
    return ""


_LANG_DE_NAMES = {"german": "deutsch", "english": "englisch", "french": "französisch", "spanish": "spanisch"}
_PLUS = re.compile(r"\b(plus|bonus|nice[- ]to[- ]have|advantage|advantageous|preferred|beneficial|helpful|"
                   r"desirable|appreciated|welcome|not required|von vorteil|wünschenswert|"
                   r"ein plus|willkommen|gerne gesehen|keine voraussetzung)\b", re.IGNORECASE)


def _patterns(language: str):
    en = re.escape(language.lower())
    de = re.escape(_LANG_DE_NAMES.get(language.lower(), language.lower()))
    level = r"(?:c1|c2|b2|native|fluent|fluency|business[- ]fluent|proficient|proficiency|excellent|very good|strong)"
    return [
        # English phrasing
        re.compile(rf"\b{level}\b[^.\n]{{0,40}}\b{en}\b", re.IGNORECASE),        # "fluent in German", "excellent written and spoken German"
        re.compile(rf"\b{en}\b[^.\n]{{0,20}}\(?\b{level}\b", re.IGNORECASE),      # "German (C1)", "German: fluent"
        re.compile(rf"\b{en}[- ]speaking\b", re.IGNORECASE),                     # "German-speaking"
        # German phrasing
        re.compile(rf"\b(fließend|verhandlungssicher\w*|sehr gut\w*|exzellent\w*|ausgezeichnet\w*|"
                   rf"muttersprach\w*)\b[^.\n]{{0,30}}\b{de}\w*", re.IGNORECASE),  # "verhandlungssicheres Deutsch"
        re.compile(rf"\b{de}\w*\b[^.\n]{{0,25}}\b(c1|c2|fließend|verhandlungssicher\w*|muttersprach\w*)\b",
                   re.IGNORECASE),                                              # "Deutsch (C1)", "Deutschkenntnisse fließend"
    ]


def requires(text: str, language: str) -> bool:
    for pattern in _patterns(language):
        for m in pattern.finditer(text or ""):
            # sentence around the match: "Fluent German is a plus" is not a requirement
            start = max((text or "").rfind(".", 0, m.start()), (text or "").rfind("\n", 0, m.start())) + 1
            end_dot = [i for i in ((text or "").find(".", m.end()), (text or "").find("\n", m.end())) if i != -1]
            end = min(end_dot) if end_dot else len(text)
            if not _PLUS.search(text[start:end]):
                return True
    return False
