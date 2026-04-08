# Lexibank Dataset Setup

To enable high-quality offline contact language forms, download CLDF datasets into `config/lexibank_data/`.

## Recommended datasets for SK contact languages

| Dataset | ar | fa | ckb | tr | Concepts | Command |
|---------|----|----|-----|-----|----------|---------|
| NorthEuraLex | - | ✓ | - | ✓ | ~1000 | `git clone https://github.com/lexibank/northeuralex config/lexibank_data/northeuralex` |
| IDS | ✓ | ✓ | - | ✓ | ~1300 | `git clone https://github.com/lexibank/ids config/lexibank_data/ids` |
| WOLD | ✓ | ✓ | - | ✓ | ~1800 | `git clone https://github.com/lexibank/wold config/lexibank_data/wold` |

After cloning, the lingpy_wordlist and pycldf providers will find them automatically.
No configuration needed — just trigger a fetch from the Compare mode Contact Lexemes panel.

## pylexibank (optional, highest quality)
```
pip install pylexibank pylexibank-northeuralex pylexibank-ids
```
Once installed, pylexibank datasets are versioned and directly citable in your thesis.
