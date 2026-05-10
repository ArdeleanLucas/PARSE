# Models

This section holds per-model reference docs for the AI models PARSE uses across its compute pipelines (STT, ORTH, IPA, alignment, chat). Each doc covers:

- **Identity** — HuggingFace repo / API endpoint, base model, license.
- **Where it's used in PARSE** — which compute paths and provider class load it.
- **Configuration** — the relevant `config/ai_config.json` block and what each knob does.
- **Tuning guide** — concrete recommendations for which knob to turn for which symptom.
- **Empirical evidence** — language-scoped sections (e.g. "Southern Kurdish — 2026-05-07"). Each empirical section dates its findings so a future maintainer can tell which results have been re-validated against current code.
- **Known limitations** — failure modes that no amount of tuning will fix.
- **References** — papers, model cards, and the PARSE PRs that touched the path.

For the high-level mapping of "task → provider", see [`ai-integration.md`](../ai-integration.md). For the canonical incident-and-fix log of model-related regressions, see the per-incident docs in this directory or in [`debugging/`](../debugging/).

## Conventions

- One markdown file per model. File name matches the HF repo or the canonical short name (e.g. `razhan-whisper-base-sdh.md`, `wav2vec2-xlsr-53-espeak-cv-ft.md`).
- Empirical-evidence sections are named `Empirical evidence — <Language> — <YYYY-MM-DD>`. New empirical work is **appended** as a new dated subsection, not overwriting the previous one — older findings remain so future readers can see how behavior evolved across model or code changes.
- A finding remains the canonical recommendation for that language until a newer dated subsection supersedes it. Cite the dated subsection in PR bodies and incident docs.
- Settings rationale tables should reference the empirical subsection that justifies each chosen value. If a setting changes, add a new empirical subsection rather than rewriting the old rationale.

## Index

| Model | Task | Languages | Doc |
|---|---|---|---|
| `razhan/whisper-base-sdh` | ORTH (orthographic transcription) | Southern Kurdish (`sd` / `sdh` → `fa` mapping) | [`razhan-whisper-base-sdh.md`](razhan-whisper-base-sdh.md) |
| `facebook/wav2vec2-xlsr-53-espeak-cv-ft` | IPA (phoneme transcription) + Tier-2 forced alignment | Multilingual (single-language model — language input is inert at acoustic decode; espeak-ng G2P uses language for forced-align targets only) | [`wav2vec2-xlsr-53-espeak-cv-ft.md`](wav2vec2-xlsr-53-espeak-cv-ft.md) |

## Adding a new model doc

1. Create `docs/models/<short-name>.md`. Match the section structure of an existing doc.
2. Add a row to the index table above.
3. If the model is referenced in `config/ai_config.json` or in a provider class, link from `docs/ai-integration.md` so the high-level config doc points readers here for the deep-dive.
4. Open the empirical-evidence section even if you have no data yet — note which language and what experiments are pending. Future agents can fill it in as evidence accumulates.
