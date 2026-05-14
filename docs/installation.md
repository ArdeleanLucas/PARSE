# Installation

This page is the compact setup checklist. For the expanded walkthrough and troubleshooting notes, see [Getting Started](getting-started.md).

## Requirements
- Linux or WSL shell for the default launcher workflow.
- Node.js 18+.
- Python 3.10–3.12.
- A Python environment with `python/requirements.txt` installed.
- CUDA-capable GPU recommended for thesis-scale local STT, ORTH, and wav2vec2 IPA/alignment work.

## Clone and install

```bash
git clone https://github.com/ArdeleanLucas/PARSE.git
cd PARSE
npm install
python3 -m venv .venv
source .venv/bin/activate
pip install -r python/requirements.txt
```

On Debian/Ubuntu systems with PEP 668 restrictions, prefer a virtual environment. If you intentionally install outside a venv, use your distribution's recommended `pip --user` or `--break-system-packages` workflow.

## Configure local AI settings

```bash
cp config/ai_config.example.json config/ai_config.json
```

Edit `config/ai_config.json` for your model paths, provider choices, and preferred devices. Machine-local secrets and model paths should stay out of git.

## Launch

```bash
./scripts/parse-run.sh
```

The launcher starts the Python API and Vite frontend, checks health, and prints the URLs for Annotate and Compare.

## Next steps
- Run the [first full pipeline guide](getting-started/first-pipeline.md).
- Review [configuration options](reference/configuration.md).
- For long field recordings, read [Processing long recordings](user-guides/processing-long-recordings.md).
