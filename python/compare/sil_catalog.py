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
   out of the repo. See the CLEF route wiring in ``python/server.py`` (thin HTTP orchestrator) and ``python/server_routes/clef.py``.

A future "Import from Ethnologue" or Glottolog integration would drop into
the same shape: ``[{"code": ..., "name": ..., "family": ...}]``.
"""

from typing import Dict, List

# (code, name, family, script). Keep under ~150 entries -- this is a starter
# list, not an exhaustive Ethnologue dump. Users can add custom codes
# through the modal's free-text input.
#
# ``script`` is the ISO 15924 code (Arab, Latn, Hebr, Cyrl, Grek, Deva, ...)
# the Reference Forms panel uses to route bare strings deterministically
# script vs IPA, instead of guessing from Unicode blocks. When omitted the
# UI falls back to the Unicode-block heuristic. Prefer the *modern dominant*
# script: Tajik is Cyrl in 2026 even though pre-Soviet Tajik was Arab.
SIL_CATALOG: List[Dict[str, str]] = [
    # Middle East / Near East (primary thesis contact languages)
    {"code": "ar", "name": "Arabic", "family": "Semitic", "script": "Arab"},
    {"code": "fa", "name": "Persian (Farsi)", "family": "Iranian", "script": "Arab"},
    {"code": "ckb", "name": "Central Kurdish (Sorani)", "family": "Iranian", "script": "Arab"},
    {"code": "kmr", "name": "Northern Kurdish (Kurmanji)", "family": "Iranian", "script": "Latn"},
    {"code": "sdh", "name": "Southern Kurdish", "family": "Iranian", "script": "Arab"},
    {"code": "hac", "name": "Gurani (Hawrami)", "family": "Iranian", "script": "Arab"},
    {"code": "zza", "name": "Zazaki", "family": "Iranian", "script": "Latn"},
    {"code": "lki", "name": "Laki", "family": "Iranian", "script": "Arab"},
    {"code": "tr", "name": "Turkish", "family": "Turkic", "script": "Latn"},
    {"code": "aze", "name": "Azerbaijani", "family": "Turkic", "script": "Latn"},
    {"code": "heb", "name": "Hebrew", "family": "Semitic", "script": "Hebr"},
    {"code": "syr", "name": "Syriac", "family": "Semitic", "script": "Syrc"},
    {"code": "arc", "name": "Aramaic", "family": "Semitic", "script": "Syrc"},
    {"code": "urd", "name": "Urdu", "family": "Indo-Aryan", "script": "Arab"},

    # Western European
    {"code": "eng", "name": "English", "family": "Germanic", "script": "Latn"},
    {"code": "deu", "name": "German", "family": "Germanic", "script": "Latn"},
    {"code": "nld", "name": "Dutch", "family": "Germanic", "script": "Latn"},
    {"code": "swe", "name": "Swedish", "family": "Germanic", "script": "Latn"},
    {"code": "nor", "name": "Norwegian", "family": "Germanic", "script": "Latn"},
    {"code": "dan", "name": "Danish", "family": "Germanic", "script": "Latn"},
    {"code": "isl", "name": "Icelandic", "family": "Germanic", "script": "Latn"},
    {"code": "fra", "name": "French", "family": "Romance", "script": "Latn"},
    {"code": "spa", "name": "Spanish", "family": "Romance", "script": "Latn"},
    {"code": "por", "name": "Portuguese", "family": "Romance", "script": "Latn"},
    {"code": "ita", "name": "Italian", "family": "Romance", "script": "Latn"},
    {"code": "ron", "name": "Romanian", "family": "Romance", "script": "Latn"},
    {"code": "cat", "name": "Catalan", "family": "Romance", "script": "Latn"},
    {"code": "lat", "name": "Latin", "family": "Romance", "script": "Latn"},
    {"code": "ell", "name": "Greek (Modern)", "family": "Hellenic", "script": "Grek"},
    {"code": "grc", "name": "Greek (Ancient)", "family": "Hellenic", "script": "Grek"},

    # Slavic
    {"code": "rus", "name": "Russian", "family": "Slavic", "script": "Cyrl"},
    {"code": "ukr", "name": "Ukrainian", "family": "Slavic", "script": "Cyrl"},
    {"code": "pol", "name": "Polish", "family": "Slavic", "script": "Latn"},
    {"code": "ces", "name": "Czech", "family": "Slavic", "script": "Latn"},
    {"code": "slk", "name": "Slovak", "family": "Slavic", "script": "Latn"},
    {"code": "bul", "name": "Bulgarian", "family": "Slavic", "script": "Cyrl"},
    {"code": "hrv", "name": "Croatian", "family": "Slavic", "script": "Latn"},
    {"code": "srp", "name": "Serbian", "family": "Slavic", "script": "Cyrl"},
    {"code": "slv", "name": "Slovenian", "family": "Slavic", "script": "Latn"},

    # Other European
    {"code": "hun", "name": "Hungarian", "family": "Uralic", "script": "Latn"},
    {"code": "fin", "name": "Finnish", "family": "Uralic", "script": "Latn"},
    {"code": "est", "name": "Estonian", "family": "Uralic", "script": "Latn"},
    {"code": "lit", "name": "Lithuanian", "family": "Baltic", "script": "Latn"},
    {"code": "lav", "name": "Latvian", "family": "Baltic", "script": "Latn"},
    {"code": "eus", "name": "Basque", "family": "Isolate", "script": "Latn"},
    {"code": "sqi", "name": "Albanian", "family": "Albanian", "script": "Latn"},
    {"code": "hye", "name": "Armenian", "family": "Armenian", "script": "Armn"},
    {"code": "kat", "name": "Georgian", "family": "Kartvelian", "script": "Geor"},

    # South Asian
    {"code": "hin", "name": "Hindi", "family": "Indo-Aryan", "script": "Deva"},
    {"code": "ben", "name": "Bengali", "family": "Indo-Aryan", "script": "Beng"},
    {"code": "pan", "name": "Punjabi", "family": "Indo-Aryan", "script": "Guru"},
    {"code": "guj", "name": "Gujarati", "family": "Indo-Aryan", "script": "Gujr"},
    {"code": "mar", "name": "Marathi", "family": "Indo-Aryan", "script": "Deva"},
    {"code": "nep", "name": "Nepali", "family": "Indo-Aryan", "script": "Deva"},
    {"code": "sin", "name": "Sinhala", "family": "Indo-Aryan", "script": "Sinh"},
    {"code": "tam", "name": "Tamil", "family": "Dravidian", "script": "Taml"},
    {"code": "tel", "name": "Telugu", "family": "Dravidian", "script": "Telu"},
    {"code": "mal", "name": "Malayalam", "family": "Dravidian", "script": "Mlym"},
    {"code": "kan", "name": "Kannada", "family": "Dravidian", "script": "Knda"},
    {"code": "san", "name": "Sanskrit", "family": "Indo-Aryan", "script": "Deva"},
    {"code": "pus", "name": "Pashto", "family": "Iranian", "script": "Arab"},
    {"code": "bal", "name": "Balochi", "family": "Iranian", "script": "Arab"},

    # East Asian
    {"code": "cmn", "name": "Mandarin Chinese", "family": "Sino-Tibetan", "script": "Hans"},
    {"code": "yue", "name": "Cantonese", "family": "Sino-Tibetan", "script": "Hant"},
    {"code": "jpn", "name": "Japanese", "family": "Japonic", "script": "Jpan"},
    {"code": "kor", "name": "Korean", "family": "Koreanic", "script": "Hang"},
    {"code": "mon", "name": "Mongolian", "family": "Mongolic", "script": "Cyrl"},
    {"code": "bod", "name": "Tibetan", "family": "Sino-Tibetan", "script": "Tibt"},

    # Southeast Asian
    {"code": "vie", "name": "Vietnamese", "family": "Austroasiatic", "script": "Latn"},
    {"code": "tha", "name": "Thai", "family": "Kra-Dai", "script": "Thai"},
    {"code": "lao", "name": "Lao", "family": "Kra-Dai", "script": "Laoo"},
    {"code": "mya", "name": "Burmese", "family": "Sino-Tibetan", "script": "Mymr"},
    {"code": "khm", "name": "Khmer", "family": "Austroasiatic", "script": "Khmr"},
    {"code": "ind", "name": "Indonesian", "family": "Austronesian", "script": "Latn"},
    {"code": "msa", "name": "Malay", "family": "Austronesian", "script": "Latn"},
    {"code": "fil", "name": "Filipino/Tagalog", "family": "Austronesian", "script": "Latn"},

    # African
    {"code": "swa", "name": "Swahili", "family": "Bantu", "script": "Latn"},
    {"code": "amh", "name": "Amharic", "family": "Semitic", "script": "Ethi"},
    {"code": "tir", "name": "Tigrinya", "family": "Semitic", "script": "Ethi"},
    {"code": "som", "name": "Somali", "family": "Cushitic", "script": "Latn"},
    {"code": "orm", "name": "Oromo", "family": "Cushitic", "script": "Latn"},
    {"code": "hau", "name": "Hausa", "family": "Chadic", "script": "Latn"},
    {"code": "yor", "name": "Yoruba", "family": "Niger-Congo", "script": "Latn"},
    {"code": "ibo", "name": "Igbo", "family": "Niger-Congo", "script": "Latn"},
    {"code": "zul", "name": "Zulu", "family": "Bantu", "script": "Latn"},
    {"code": "xho", "name": "Xhosa", "family": "Bantu", "script": "Latn"},
    {"code": "afr", "name": "Afrikaans", "family": "Germanic", "script": "Latn"},
    {"code": "ber", "name": "Berber (Tamazight)", "family": "Berber", "script": "Latn"},

    # Turkic & Central Asian
    {"code": "uig", "name": "Uyghur", "family": "Turkic", "script": "Arab"},
    {"code": "uzb", "name": "Uzbek", "family": "Turkic", "script": "Latn"},
    {"code": "kaz", "name": "Kazakh", "family": "Turkic", "script": "Cyrl"},
    {"code": "kir", "name": "Kyrgyz", "family": "Turkic", "script": "Cyrl"},
    {"code": "tuk", "name": "Turkmen", "family": "Turkic", "script": "Latn"},
    {"code": "tat", "name": "Tatar", "family": "Turkic", "script": "Cyrl"},
    {"code": "tgk", "name": "Tajik", "family": "Iranian", "script": "Cyrl"},

    # Americas
    {"code": "que", "name": "Quechua", "family": "Quechuan", "script": "Latn"},
    {"code": "aym", "name": "Aymara", "family": "Aymaran", "script": "Latn"},
    {"code": "grn", "name": "Guarani", "family": "Tupian", "script": "Latn"},
    {"code": "nah", "name": "Nahuatl", "family": "Uto-Aztecan", "script": "Latn"},

    # Pacific
    {"code": "mri", "name": "Maori", "family": "Austronesian", "script": "Latn"},
    {"code": "haw", "name": "Hawaiian", "family": "Austronesian", "script": "Latn"},
    {"code": "smo", "name": "Samoan", "family": "Austronesian", "script": "Latn"},
    {"code": "fij", "name": "Fijian", "family": "Austronesian", "script": "Latn"},

    # Constructed / auxiliary
    {"code": "epo", "name": "Esperanto", "family": "Constructed", "script": "Latn"},
]
