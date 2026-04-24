"""Bundled SIL/ISO 639-3 catalog for the CLEF configure modal.

Kept as a static list so fresh workspaces can populate the picker without
an external dependency. Codes use ISO 639-3 (3-letter) form; the legacy
2-letter codes already present in sil_contact_languages.json (ar, fa, tr)
are included as aliases so mixed configs keep working.

Ordering is "common contact languages first" -- the UI shows the full list
searchably, but showing e.g. English before Bikol is the sensible default
for the thesis corpus this feature was built for.

How to extend
-------------

Two ways:

1. **Edit this file** and add ``{"code": "xxx", "name": "...", "family": "..."}``
   entries to ``SIL_CATALOG``. Good for permanent additions you want to ship
   to other PARSE users.
2. **Per-workspace extras** (no code change, no rebuild): create
   ``<workspace>/config/sil_catalog_extra.json`` containing either a list
   in the same shape, or ``{"languages": [...]}``. The server merges these
   over the bundled list at request time so users can keep private entries
   out of the repo. See ``_api_get_clef_catalog`` in ``python/server.py``.

A future "Import from Ethnologue" or Glottolog integration would drop into
the same shape: ``[{"code": ..., "name": ..., "family": ...}]``.
"""

from typing import Dict, List

# (code, name, family). Keep under ~150 entries -- this is a starter list,
# not an exhaustive Ethnologue dump. Users can add custom codes through the
# modal's free-text input.
SIL_CATALOG: List[Dict[str, str]] = [
    # Middle East / Near East (primary thesis contact languages)
    {"code": "ar", "name": "Arabic", "family": "Semitic"},
    {"code": "fa", "name": "Persian (Farsi)", "family": "Iranian"},
    {"code": "ckb", "name": "Central Kurdish (Sorani)", "family": "Iranian"},
    {"code": "kmr", "name": "Northern Kurdish (Kurmanji)", "family": "Iranian"},
    {"code": "sdh", "name": "Southern Kurdish", "family": "Iranian"},
    {"code": "hac", "name": "Gurani (Hawrami)", "family": "Iranian"},
    {"code": "zza", "name": "Zazaki", "family": "Iranian"},
    {"code": "lki", "name": "Laki", "family": "Iranian"},
    {"code": "tr", "name": "Turkish", "family": "Turkic"},
    {"code": "aze", "name": "Azerbaijani", "family": "Turkic"},
    {"code": "heb", "name": "Hebrew", "family": "Semitic"},
    {"code": "syr", "name": "Syriac", "family": "Semitic"},
    {"code": "arc", "name": "Aramaic", "family": "Semitic"},
    {"code": "urd", "name": "Urdu", "family": "Indo-Aryan"},

    # Western European
    {"code": "eng", "name": "English", "family": "Germanic"},
    {"code": "deu", "name": "German", "family": "Germanic"},
    {"code": "nld", "name": "Dutch", "family": "Germanic"},
    {"code": "swe", "name": "Swedish", "family": "Germanic"},
    {"code": "nor", "name": "Norwegian", "family": "Germanic"},
    {"code": "dan", "name": "Danish", "family": "Germanic"},
    {"code": "isl", "name": "Icelandic", "family": "Germanic"},
    {"code": "fra", "name": "French", "family": "Romance"},
    {"code": "spa", "name": "Spanish", "family": "Romance"},
    {"code": "por", "name": "Portuguese", "family": "Romance"},
    {"code": "ita", "name": "Italian", "family": "Romance"},
    {"code": "ron", "name": "Romanian", "family": "Romance"},
    {"code": "cat", "name": "Catalan", "family": "Romance"},
    {"code": "lat", "name": "Latin", "family": "Romance"},
    {"code": "ell", "name": "Greek (Modern)", "family": "Hellenic"},
    {"code": "grc", "name": "Greek (Ancient)", "family": "Hellenic"},

    # Slavic
    {"code": "rus", "name": "Russian", "family": "Slavic"},
    {"code": "ukr", "name": "Ukrainian", "family": "Slavic"},
    {"code": "pol", "name": "Polish", "family": "Slavic"},
    {"code": "ces", "name": "Czech", "family": "Slavic"},
    {"code": "slk", "name": "Slovak", "family": "Slavic"},
    {"code": "bul", "name": "Bulgarian", "family": "Slavic"},
    {"code": "hrv", "name": "Croatian", "family": "Slavic"},
    {"code": "srp", "name": "Serbian", "family": "Slavic"},
    {"code": "slv", "name": "Slovenian", "family": "Slavic"},

    # Other European
    {"code": "hun", "name": "Hungarian", "family": "Uralic"},
    {"code": "fin", "name": "Finnish", "family": "Uralic"},
    {"code": "est", "name": "Estonian", "family": "Uralic"},
    {"code": "lit", "name": "Lithuanian", "family": "Baltic"},
    {"code": "lav", "name": "Latvian", "family": "Baltic"},
    {"code": "eus", "name": "Basque", "family": "Isolate"},
    {"code": "sqi", "name": "Albanian", "family": "Albanian"},
    {"code": "hye", "name": "Armenian", "family": "Armenian"},
    {"code": "kat", "name": "Georgian", "family": "Kartvelian"},

    # South Asian
    {"code": "hin", "name": "Hindi", "family": "Indo-Aryan"},
    {"code": "ben", "name": "Bengali", "family": "Indo-Aryan"},
    {"code": "pan", "name": "Punjabi", "family": "Indo-Aryan"},
    {"code": "guj", "name": "Gujarati", "family": "Indo-Aryan"},
    {"code": "mar", "name": "Marathi", "family": "Indo-Aryan"},
    {"code": "nep", "name": "Nepali", "family": "Indo-Aryan"},
    {"code": "sin", "name": "Sinhala", "family": "Indo-Aryan"},
    {"code": "tam", "name": "Tamil", "family": "Dravidian"},
    {"code": "tel", "name": "Telugu", "family": "Dravidian"},
    {"code": "mal", "name": "Malayalam", "family": "Dravidian"},
    {"code": "kan", "name": "Kannada", "family": "Dravidian"},
    {"code": "san", "name": "Sanskrit", "family": "Indo-Aryan"},
    {"code": "pus", "name": "Pashto", "family": "Iranian"},
    {"code": "bal", "name": "Balochi", "family": "Iranian"},

    # East Asian
    {"code": "cmn", "name": "Mandarin Chinese", "family": "Sino-Tibetan"},
    {"code": "yue", "name": "Cantonese", "family": "Sino-Tibetan"},
    {"code": "jpn", "name": "Japanese", "family": "Japonic"},
    {"code": "kor", "name": "Korean", "family": "Koreanic"},
    {"code": "mon", "name": "Mongolian", "family": "Mongolic"},
    {"code": "bod", "name": "Tibetan", "family": "Sino-Tibetan"},

    # Southeast Asian
    {"code": "vie", "name": "Vietnamese", "family": "Austroasiatic"},
    {"code": "tha", "name": "Thai", "family": "Kra-Dai"},
    {"code": "lao", "name": "Lao", "family": "Kra-Dai"},
    {"code": "mya", "name": "Burmese", "family": "Sino-Tibetan"},
    {"code": "khm", "name": "Khmer", "family": "Austroasiatic"},
    {"code": "ind", "name": "Indonesian", "family": "Austronesian"},
    {"code": "msa", "name": "Malay", "family": "Austronesian"},
    {"code": "fil", "name": "Filipino/Tagalog", "family": "Austronesian"},

    # African
    {"code": "swa", "name": "Swahili", "family": "Bantu"},
    {"code": "amh", "name": "Amharic", "family": "Semitic"},
    {"code": "tir", "name": "Tigrinya", "family": "Semitic"},
    {"code": "som", "name": "Somali", "family": "Cushitic"},
    {"code": "orm", "name": "Oromo", "family": "Cushitic"},
    {"code": "hau", "name": "Hausa", "family": "Chadic"},
    {"code": "yor", "name": "Yoruba", "family": "Niger-Congo"},
    {"code": "ibo", "name": "Igbo", "family": "Niger-Congo"},
    {"code": "zul", "name": "Zulu", "family": "Bantu"},
    {"code": "xho", "name": "Xhosa", "family": "Bantu"},
    {"code": "afr", "name": "Afrikaans", "family": "Germanic"},
    {"code": "ber", "name": "Berber (Tamazight)", "family": "Berber"},

    # Turkic & Central Asian
    {"code": "uig", "name": "Uyghur", "family": "Turkic"},
    {"code": "uzb", "name": "Uzbek", "family": "Turkic"},
    {"code": "kaz", "name": "Kazakh", "family": "Turkic"},
    {"code": "kir", "name": "Kyrgyz", "family": "Turkic"},
    {"code": "tuk", "name": "Turkmen", "family": "Turkic"},
    {"code": "tat", "name": "Tatar", "family": "Turkic"},
    {"code": "tgk", "name": "Tajik", "family": "Iranian"},

    # Americas
    {"code": "que", "name": "Quechua", "family": "Quechuan"},
    {"code": "aym", "name": "Aymara", "family": "Aymaran"},
    {"code": "grn", "name": "Guarani", "family": "Tupian"},
    {"code": "nah", "name": "Nahuatl", "family": "Uto-Aztecan"},

    # Pacific
    {"code": "mri", "name": "Maori", "family": "Austronesian"},
    {"code": "haw", "name": "Hawaiian", "family": "Austronesian"},
    {"code": "smo", "name": "Samoan", "family": "Austronesian"},
    {"code": "fij", "name": "Fijian", "family": "Austronesian"},

    # Constructed / auxiliary
    {"code": "epo", "name": "Esperanto", "family": "Constructed"},
]
