# Research Context & Citation

> Last updated: 2026-04-24
>
> This page frames PARSE as research software: why it exists, what scholarly workflow it supports, and how to cite it responsibly.

## What research problem PARSE was built for

PARSE was developed for a **Southern Kurdish dialect phylogenetics thesis** at the **University of Bamberg**.

The current repository README describes the target workflow as one involving:

- long field recordings
- concept-based wordlists
- multi-speaker datasets
- iterative transcription and timing correction
- cross-speaker cognate review
- borrowing adjudication
- export into downstream comparative / phylogenetic pipelines

In other words, PARSE is not just an annotation UI. It is an attempt to keep the entire path from raw or processed field recordings to comparative export-ready datasets inside one research workstation.

## Research motivation

The underlying motivation is practical and methodological.

### 1. Long recordings are hard to annotate consistently

Elicitation sessions may run for hours. Target lexical items are often embedded inside prompts, repetitions, repairs, and commentary. Even when a recording has already been partially processed, locating the exact lexical spans again can still be slow.

### 2. Annotation and comparison are usually fragmented across tools

Traditional workflows often split:

- waveform review
- transcription
- speaker-specific annotation
- comparative review
- borrowing analysis
- export preparation

across separate applications and ad hoc scripts.

PARSE's dual-mode architecture is explicitly designed to reduce that fragmentation.

### 3. Historical-comparative work needs reviewed structure, not just transcripts

The thesis use case is not satisfied by speech-to-text alone. It needs:

- trustworthy timestamps
- explicit segment review
- cross-speaker concept alignment
- cognate grouping decisions
- borrowing-aware comparison
- export formats that downstream tools can use

That is why PARSE combines Annotate mode, Compare mode, CLEF, and export tooling inside one system.

## Current research framing of the project

The current README positions PARSE as:

- **browser-based**
- **dual-mode**
- **fieldwork-first**
- **AI-assisted**
- **research software rather than production software**

That framing is important. PARSE is still in active development, and thesis-critical features are landing quickly. Anyone using it in research should therefore document the specific version, provider configuration, and export path used in a given analysis.

## Where PARSE fits in the workflow

At a high level, PARSE bridges these stages:

```text
Field recordings / processed speaker artifacts
        ↓
Per-speaker annotation and timing review
        ↓
Cross-speaker comparison and cognate adjudication
        ↓
Borrowing-oriented contact evidence via CLEF
        ↓
LingPy TSV / NEXUS export
        ↓
Downstream comparative and phylogenetic analysis
```

The current README specifically mentions downstream use with:

- **LingPy**
- **LexStat**
- **BEAST 2**

## Related software and external components

PARSE sits in an ecosystem of existing libraries, models, and downstream tools.

The current README explicitly calls out these as major external components materially shaping PARSE's runtime behavior or outputs:

- `razhan/whisper-base-sdh`
- `facebook/wav2vec2-xlsr-53-espeak-cv-ft`
- Silero VAD
- faster-whisper
- CTranslate2
- WaveSurfer.js
- React
- Vite
- Tailwind CSS
- Lucide

These are not "related work" in the sense of a full literature review, but they are the primary technical dependencies and adjacent toolchain pieces the repository itself foregrounds.

For the full dependency/citation table, see [AI Integration](./ai-integration.md).

## Citation instructions

### Repository citation

If you use PARSE in academic work, cite it as **research software**.

The repository includes a machine-readable [`CITATION.cff`](../CITATION.cff) file, and GitHub's **Cite this repository** button will generate standard citation formats automatically.

The current README gives this suggested citation:

> Ardelean, L. M. (2026). *PARSE: Phonetic Analysis & Review Source Explorer* [Computer software]. University of Bamberg. https://github.com/ArdeleanLucas/PARSE

### BibTeX

```bibtex
@software{ardelean_parse_2026,
  author  = {Ardelean, Lucas M.},
  title   = {{PARSE}: Phonetic Analysis \& Review Source Explorer},
  year    = {2026},
  url     = {https://github.com/ArdeleanLucas/PARSE},
  note    = {Research software for Southern Kurdish dialect phylogenetics}
}
```

### CITATION.cff summary

The current `CITATION.cff` describes PARSE as:

- software
- authored by **Lucas M. Ardelean**
- licensed under **MIT**
- focused on computational linguistics, phonetics, annotation, cognate detection, phylogenetics, Southern Kurdish, fieldwork, and speech-to-text

It also includes an abstract summarizing PARSE as a browser-based dual-mode research workstation combining waveform review, tiered annotation, AI-assisted STT, cognate adjudication, and CLEF.

## What else should be cited in a serious methods section?

The current README makes a useful methodological point: the major external models and repositories that materially shape PARSE output should also be cited or acknowledged when they are used in a given run.

In practice that means documenting:

- the PARSE version / commit
- the configured STT / ORTH / chat providers
- any local or remote models used (for example Razhan, wav2vec2, Whisper-family backends)
- any contact-language evidence sources materially used in CLEF
- the downstream export target and later analysis environment

If proprietary API services such as OpenAI or xAI are enabled, they should be acknowledged in methods sections as services used in the workflow, even though they are not source repositories in the same way as the open-weight models and libraries listed in the README.

## Thesis context

The README currently states that the working dataset covers multiple speakers of Southern Kurdish varieties with an **85-item Oxford Iranian wordlist**, targeting downstream Bayesian phylogenetic analysis in **BEAST 2**.

That context matters because it explains several design choices in PARSE:

- concept-based organization rather than free-form transcript-first design
- strong emphasis on timestamps and repeated lexical items
- comparative review as a first-class mode
- borrowing adjudication via contact-language evidence
- export pathways tailored to later comparative analysis

## Recommended citation practice

When publishing work that used PARSE, the most defensible citation bundle is:

1. **Cite PARSE itself** via [`CITATION.cff`](../CITATION.cff)
2. **Cite the associated thesis** once publicly available
3. **Acknowledge major enabled models/providers** used in the actual workflow
4. **Document export and downstream analysis tools** used after PARSE

## Related docs

- Project landing page: [README](../README.md)
- Setup and configuration: [Getting Started](./getting-started.md)
- Models, providers, and tool surface: [AI Integration](./ai-integration.md)
- System design and data model: [Architecture](./architecture.md)
