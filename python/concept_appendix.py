"""concept_appendix.py — Render a per-concept markdown appendix from a PARSE workspace.

Produces a language/survey-neutral markdown document: each tag-filtered concept is
listed with its per-survey source items and the per-speaker IPA / orthographic forms,
optionally annotated with the cognate-set decisions made in PARSE compare mode.

The per-speaker forms, tag filtering and clarifier-sibling collapse are reused verbatim
from :func:`export_review_data.build_review_data` (the same pipeline that produced the
legacy ``sk_survey_concept_appendix.md``). The cognate layer this module adds on top is
resolved straight from ``parse-enrichments.json`` with ``manual_overrides`` taking
precedence over the auto-computed blocks — mirroring ``export_tools.build_nexus_text`` and
``server_routes/exports._api_get_export_nexus`` — so the export reflects the user's actual
compare-mode decisions, not just the auto cognate compute.

Cognate cell vocabulary (per speaker, per concept):

* a letter (``A``/``B``/``C`` …) — the form's cognate set
* ``·`` — a form was recorded but left ungrouped (no cognate decision for it yet)
* ``?`` — the speaker has no form for the concept, or was excluded from the set. ``?`` is
  BEAST2's non-penalized missing state, so excluded speakers do not bias downstream compute.
* a trailing ``⟳`` — the form was flagged as a borrowing.

Per-concept verdict words: ``split`` · ``accepted`` · ``merge`` · ``—`` (no decision yet).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from concept_canonical import strip_clarifier
from concept_source_item import read_concepts_csv_rows, row_value
from export_review_data import DEFAULT_TAG_ID, ENRICHMENTS_FILENAME, build_review_data

UNGROUPED = "·"
MISSING = "?"
BORROW = "⟳"  # ⟳

_DECISION_WORDS = {"accepted": "accepted", "split": "split", "merge": "merge"}


def _is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _gloss_key(label: str) -> str:
    """Collapse key matching ``build_review_data``'s clarifier-sibling grouping."""
    base = strip_clarifier(str(label or "")).casefold().strip()
    return base or str(label or "").strip().casefold()


def _id_sort_key(concept_id: str) -> Tuple[int, Any]:
    text = str(concept_id or "").strip()
    try:
        return (0, int(text))
    except (TypeError, ValueError):
        return (1, text)


def _has_form(form: Mapping[str, Any]) -> bool:
    ipa = str(form.get("ipa") or "").strip()
    ortho = str(form.get("ortho") or "").strip()
    if ipa and ipa != "?":
        return True
    return bool(ortho)


def _load_enrichments_raw(workspace: Path) -> Dict[str, Any]:
    path = workspace / ENRICHMENTS_FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _resolved_block(enrichments: Mapping[str, Any], key: str) -> Dict[str, Any]:
    """Merge ``manual_overrides[key]`` over root ``[key]``, per concept id (override wins)."""
    overrides = enrichments.get("manual_overrides")
    overrides = overrides if _is_mapping(overrides) else {}
    override_block = overrides.get(key) if _is_mapping(overrides.get(key)) else {}
    auto_block = enrichments.get(key) if _is_mapping(enrichments.get(key)) else {}
    merged: Dict[str, Any] = {}
    for concept_id in list(auto_block.keys()) + list(override_block.keys()):
        cid = str(concept_id)
        if cid in override_block:
            merged[cid] = override_block[cid]
        else:
            merged[cid] = auto_block[concept_id]
    return merged


class _CognateResolver:
    """Resolves per-(concept, speaker) cognate state across a concept's underlying ids."""

    def __init__(self, enrichments: Mapping[str, Any]) -> None:
        self.sets = _resolved_block(enrichments, "cognate_sets")
        self.decisions = _resolved_block(enrichments, "cognate_decisions")
        self.borrowing = _resolved_block(enrichments, "borrowing_flags")
        self.speaker_flags = _resolved_block(enrichments, "speaker_flags")

    def is_excluded(self, ids: Sequence[str], speaker: str) -> bool:
        for cid in ids:
            flags = self.speaker_flags.get(cid)
            if _is_mapping(flags) and flags.get(speaker) is True:
                return True
        return False

    def is_borrowed(self, ids: Sequence[str], speaker: str) -> bool:
        for cid in ids:
            flags = self.borrowing.get(cid)
            if _is_mapping(flags) and speaker in flags:
                value = flags.get(speaker)
                if isinstance(value, str):
                    if value.strip() and value.strip().lower() not in {"native", "no", "0"}:
                        return True
                elif value:
                    return True
        return False

    def letter(self, ids: Sequence[str], speaker: str, *, has_form: bool) -> str:
        """First-letter-wins across the concept's ids (matches useExport.speakerCognateId).

        Returns ``?`` when excluded or formless, the set letter when assigned, ``·`` when a
        form exists but sits in no set.
        """
        if self.is_excluded(ids, speaker):
            return MISSING
        for cid in ids:
            groups = self.sets.get(cid)
            if not _is_mapping(groups):
                continue
            for letter in sorted(groups.keys()):
                members = groups.get(letter)
                if isinstance(members, list) and speaker in {str(m) for m in members}:
                    return str(letter)
        return UNGROUPED if has_form else MISSING

    def verdict(self, ids: Sequence[str]) -> str:
        for cid in ids:
            entry = self.decisions.get(cid)
            if _is_mapping(entry):
                word = _DECISION_WORDS.get(str(entry.get("decision") or ""))
                if word:
                    return word
        return "—"  # —


def _group_concept_rows_by_gloss(concepts_csv: Path) -> Dict[str, Dict[str, Any]]:
    """Map gloss-key -> {"ids": [csv id…], "surveys": [(survey, item)…]} from concepts.csv."""
    groups: Dict[str, Dict[str, Any]] = {}
    if not concepts_csv.exists():
        return groups
    for row in read_concepts_csv_rows(concepts_csv):
        label = row_value(row, "concept_en") or row_value(row, "label")
        key = _gloss_key(label)
        if not key:
            continue
        concept_id = str(row_value(row, "id") or "").strip()
        survey = str(row_value(row, "source_survey") or "").strip()
        item = str(row_value(row, "source_item") or "").strip()
        bucket = groups.setdefault(key, {"ids": [], "surveys": []})
        if concept_id and concept_id not in bucket["ids"]:
            bucket["ids"].append(concept_id)
        if survey:
            bucket["surveys"].append((survey, item))
    for bucket in groups.values():
        bucket["ids"].sort(key=_id_sort_key)
    return groups


def _survey_source_line(surveys: Sequence[Tuple[str, str]]) -> str:
    """Render ``**KLQ:** 1.1 · **JBIL:** 32`` from a concept's (survey, item) pairs."""
    by_survey: "Dict[str, List[str]]" = {}
    order: List[str] = []
    for survey, item in surveys:
        if survey not in by_survey:
            by_survey[survey] = []
            order.append(survey)
        if item and item not in by_survey[survey]:
            by_survey[survey].append(item)
    parts: List[str] = []
    for survey in order:
        items = by_survey[survey]
        value = "; ".join(items) if items else "—"
        parts.append("**{0}:** {1}".format(survey, value))
    return "  ·  ".join(parts)


def _escape_cell(text: str) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ").strip()


def build_concept_appendix_markdown(
    *,
    workspace: Path,
    tag_id: str = DEFAULT_TAG_ID,
    include_cognates: bool = True,
    contact_config: Optional[Path] = None,
    speaker_filter: Optional[Iterable[str]] = None,
    concept_ids: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Build the concept-appendix markdown document.

    When ``concept_ids`` is given (e.g. the caller's currently-filtered concept menu),
    the export covers exactly those concepts instead of the whole ``tag_id`` set.

    Returns ``{"markdown": str, "concepts": int, "speakers": int}``.
    """
    workspace = Path(workspace)
    review_data, _clip_plan = build_review_data(
        workspace=workspace,
        tag_id=tag_id,
        contact_config=contact_config,
        speaker_filter=speaker_filter,
        concept_ids=concept_ids,
    )
    metadata = review_data.get("metadata", {}) if isinstance(review_data, Mapping) else {}
    concepts = review_data.get("concepts", []) if isinstance(review_data, Mapping) else []
    speakers: List[str] = [str(s) for s in metadata.get("speakers", []) if str(s).strip()]
    generated = str(metadata.get("generated") or "").split("T", 1)[0]

    gloss_groups = _group_concept_rows_by_gloss(workspace / "concepts.csv")
    resolver = _CognateResolver(_load_enrichments_raw(workspace)) if include_cognates else None

    lines: List[str] = []
    lines.append("# Concept Appendix — per-speaker forms" + (" & cognate decisions" if include_cognates else ""))
    lines.append("")
    suffix = "(`{0}` tag)".format(tag_id) if tag_id else ""
    lines.append("_Generated {0} from the PARSE workspace {1}._".format(generated or "", suffix).strip())
    lines.append("")
    intro = (
        "Each concept is listed with its source item number in each elicitation survey and the "
        "IPA and orthographic forms recorded for every studied speaker"
    )
    intro += ", plus the cognate-set decisions made in PARSE compare mode." if include_cognates else "."
    intro += " Forms are matched to concepts by the annotation's time-aligned concept windows."
    lines.append(intro)
    lines.append("")
    lines.append("**Speakers ({0}).** {1}.".format(len(speakers), ", ".join(speakers) if speakers else "—"))

    # Distinct surveys across displayed concepts (neutral — derived, not hardcoded).
    survey_order: List[str] = []
    for entry in concepts:
        group = gloss_groups.get(_gloss_key(str(entry.get("concept_en") or "")), {})
        for survey, _item in group.get("surveys", []):
            if survey not in survey_order:
                survey_order.append(survey)
    if survey_order:
        lines.append("")
        lines.append("**Surveys.** {0}.".format("  ·  ".join(survey_order)))

    if include_cognates:
        lines.append("")
        lines.append(
            "**Cognate column.** Cog letters (A, B, C …) are each form's cognate set. "
            "`{0}` = recorded but ungrouped; `{1}` = no form, or speaker excluded from the set "
            "(non-penalized in compute); `{2}` = borrowing. Per-concept verdict: "
            "split / accepted / merge / —.".format(UNGROUPED, MISSING, BORROW)
        )

    # ---- cognate matrix (concepts as rows) ----
    if include_cognates and speakers:
        lines.append("")
        lines.append("## Cognate matrix")
        lines.append("")
        header = ["# · Concept", *speakers, "Verdict"]
        lines.append("| " + " | ".join(_escape_cell(h) for h in header) + " |")
        lines.append("|" + "---|" * len(header))

    matrix_rows: List[str] = []

    # ---- per-concept sections ----
    section_lines: List[str] = []
    for index, entry in enumerate(concepts, start=1):
        gloss = str(entry.get("concept_en") or "").strip() or "concept"
        group = gloss_groups.get(_gloss_key(gloss), {"ids": [], "surveys": []})
        ids: List[str] = list(group.get("ids", []))
        forms = entry.get("forms", []) if isinstance(entry.get("forms"), list) else []
        form_by_speaker: Dict[str, Mapping[str, Any]] = {
            str(f.get("speaker")): f for f in forms if isinstance(f, Mapping) and f.get("speaker")
        }

        section_lines.append("")
        section_lines.append("### {0} · {1}".format(index, gloss))
        survey_line = _survey_source_line(group.get("surveys", []))
        if survey_line:
            section_lines.append(survey_line)

        if include_cognates and resolver is not None:
            section_lines.append("**Cognate:** {0}".format(resolver.verdict(ids)))

        # forms table — only speakers who actually produced the concept (legacy parity)
        header_cells = ["Speaker", "IPA", "ORTH"] + (["Cog"] if include_cognates else [])
        section_lines.append("")
        section_lines.append("| " + " | ".join(header_cells) + " |")
        section_lines.append("|" + "---|" * len(header_cells))

        sets: "Dict[str, List[str]]" = {}
        excluded: List[str] = []
        for speaker in speakers:
            form = form_by_speaker.get(speaker)
            if form is None or not _has_form(form):
                continue
            row_cells = [_escape_cell(speaker), _escape_cell(form.get("ipa")), _escape_cell(form.get("ortho"))]
            if include_cognates and resolver is not None:
                letter = resolver.letter(ids, speaker, has_form=True)
                borrowed = resolver.is_borrowed(ids, speaker)
                cog_cell = letter + ((" " + BORROW) if borrowed else "")
                row_cells.append(cog_cell)
                if letter == MISSING:
                    excluded.append(speaker)
                elif letter != UNGROUPED:
                    sets.setdefault(letter, []).append(speaker + ((" " + BORROW) if borrowed else ""))
            section_lines.append("| " + " | ".join(row_cells) + " |")

        if include_cognates and resolver is not None:
            set_parts = [
                "{0} = {{{1}}}".format(letter, ", ".join(sets[letter]))
                for letter in sorted(sets.keys())
            ]
            if excluded:
                set_parts.append("excluded: " + ", ".join(excluded))
            if set_parts:
                section_lines.append("")
                section_lines.append("**Sets:** " + "  ·  ".join(set_parts))

        # matrix row for this concept
        if include_cognates and resolver is not None and speakers:
            cells = ["{0} · {1}".format(index, gloss)]
            for speaker in speakers:
                form = form_by_speaker.get(speaker)
                has = form is not None and _has_form(form)
                cells.append(resolver.letter(ids, speaker, has_form=has))
            cells.append(resolver.verdict(ids))
            matrix_rows.append("| " + " | ".join(_escape_cell(c) for c in cells) + " |")

    if include_cognates and speakers:
        lines.extend(matrix_rows)

    lines.extend(section_lines)
    lines.append("")

    return {
        "markdown": "\n".join(lines),
        "concepts": len(concepts),
        "speakers": len(speakers),
    }


__all__ = ["build_concept_appendix_markdown"]
