# BND visual refresh code trace

Stack base: `fix/lexeme-save-tier-count-and-bnd-refresh` / PR #180.

## Four-row trace table

| Reported element | Data source | Selector / DOM evidence | Render site | Invalidation verdict |
| --- | --- | --- | --- | --- |
| Beige WaveSurfer selected region | `conceptInterval` derived from `findAnnotationForConcept(record, concept)`, then `addRegion(conceptInterval.start, conceptInterval.end)` | Shadow DOM `[part~="region"]`, e.g. `part="region r-6207.706"`, `left="68.0799%"` | `src/components/annotate/annotate-views/AnnotateView.tsx:97-104`, `219-226`; region DOM is produced by WaveSurfer Regions plugin via `addRegion` | ✓ `conceptInterval?.start/end` are dependencies at `AnnotateView.tsx:226`, so save-time record replacement invalidates the effect and recreates the region. |
| `ortho_words` BND `|` markers | `record.tiers.ortho_words.intervals`; save path calls `applyLexemeRetime` then `rescaleAssociatedIntervals(record, "ortho_words", ...)` | `[aria-label^="BND "]`, e.g. `BND 6207.75s`, title `6207.749–6207.771 s · manually adjusted` | `src/stores/annotation/actions.ts:174-187`, `382-399`; virtualized render in `src/components/annotate/TranscriptionLanes.tsx:532-550`; buttons in `src/components/annotate/TranscriptionLaneRow.tsx:187-220` | ✗ before this PR when initial WaveSurfer scroll was already at the concept: `getWrapper().scrollLeft` stayed `0` while the real viewport `[part~="scroll"]` was `2482858`, so the virtualized BND slice rendered the start of the file instead of the selected region. Fixed at `TranscriptionLanes.tsx:181-188` by reading `wrapper.parentElement.scrollLeft`. |
| editStart/editEnd local-state inputs | Local React state initialized from `conceptInterval.start/end`; region drag and save paths call `setEditStart/setEditEnd` | Numeric inputs captured after save: `6207.706`, `6208.901` | `src/components/annotate/annotate-views/AnnotateView.tsx:101-114`, `160-176` | ✓ save-time record replacement changes `conceptInterval` and reruns the reset effect at `AnnotateView.tsx:108-114`; region-commit path also updates the local state at `172-174`. |
| Transcription lane scroll synchronization | `scrollLeft`, `viewportWidth`, `pxPerSec`, `duration`; virtualized `visibleStartSec/visibleEndSec` gate | Deep shadow DOM capture: `[part~="scroll"] scrollLeft=2482862`, `[part~="wrapper"] scrollLeft=0`; BND buttons visible after fix | `src/components/annotate/TranscriptionLanes.tsx:170-223`, `532-550` | ✗ root cause. Initial `readState()` used wrapper scroll offset, not the WaveSurfer scroll viewport. Scroll-event updates were correct, but hard reload/open-at-concept can render before a WaveSurfer scroll event reaches the lane component. |

## Browser evidence

- [After-fix lanes screenshot](./bnd-visual-refresh-code-trace-after-lanes.png)
- [After-save screenshot](./bnd-visual-refresh-code-trace-after-save.png)

## `ortho_words` before/after interval capture

Before save around `Fail01` / `forehead`:

```json
[
  {"start":6207.740,"end":6207.762,"text":"여기","manual":true},
  {"start":6207.762,"end":6207.916,"text":"ێ","manual":true},
  {"start":6207.916,"end":6208.005,"text":"ە","manual":true},
  {"start":6208.005,"end":6208.005,"text":"پۋ","manual":true},
  {"start":6208.005,"end":6208.892,"text":"ۋەو","manual":true},
  {"start":6208.170,"end":6208.170,"text":"دۋ","manual":true},
  {"start":6208.170,"end":6208.236,"text":"ێ","manual":true},
  {"start":6208.236,"end":6208.236,"text":"ۋ","manual":true},
  {"start":6208.236,"end":6208.241,"text":"ە","manual":true},
  {"start":6208.241,"end":6208.283,"text":"ە","manual":true},
  {"start":6208.283,"end":6208.288,"text":"ە","manual":true},
  {"start":6208.288,"end":6208.303,"text":"ۋ","manual":true},
  {"start":6208.334,"end":6208.892,"text":"قە","manual":true}
]
```

After save (+0.009s retime):

```json
[
  {"start":6207.749,"end":6207.771,"text":"여기","manual":true},
  {"start":6207.771,"end":6207.925,"text":"ێ","manual":true},
  {"start":6207.925,"end":6208.014,"text":"ە","manual":true},
  {"start":6208.014,"end":6208.014,"text":"پۋ","manual":true},
  {"start":6208.014,"end":6208.901,"text":"ۋەو","manual":true},
  {"start":6208.179,"end":6208.179,"text":"دۋ","manual":true},
  {"start":6208.179,"end":6208.245,"text":"ێ","manual":true},
  {"start":6208.245,"end":6208.245,"text":"ۋ","manual":true},
  {"start":6208.245,"end":6208.250,"text":"ە","manual":true},
  {"start":6208.250,"end":6208.292,"text":"ە","manual":true},
  {"start":6208.292,"end":6208.297,"text":"ە","manual":true},
  {"start":6208.297,"end":6208.312,"text":"ۋ","manual":true},
  {"start":6208.343,"end":6208.901,"text":"قە","manual":true}
]
```

## `[part~="region"]` and scroll DOM capture

Before save:

```json
{
  "regions":[{"part":"region r-6207.697","left":"68.0798%","outer":"<div part=\"region r-6207.697\" ...>"}],
  "scroll":[{"part":"scroll","scrollLeft":2482858,"clientWidth":669,"scrollWidth":3647305},{"part":"wrapper","scrollLeft":0,"clientWidth":3647305,"scrollWidth":3647305}]
}
```

After save:

```json
{
  "regions":[{"part":"region r-6207.706","left":"68.0799%","outer":"<div part=\"region r-6207.706\" ...>"}],
  "scroll":[{"part":"scroll","scrollLeft":2482862,"clientWidth":669,"scrollWidth":3647305},{"part":"wrapper","scrollLeft":0,"clientWidth":3647305,"scrollWidth":3647305}]
}
```

## Concept interval ref-change debug log

```json
{
  "beforeRefLog":{"conceptInterval":{"text":"forehead","start":6207.697,"end":6208.892},"editInputsBeforeClick":{"start":"6207.706","end":"6208.901"}},
  "conceptIntervalRefChange":{"before":{"start":6207.697,"end":6208.892},"after":{"start":6207.706,"end":6208.901},"changed":true,"editInputsAfterSave":["6207.706","6208.901"]},
  "saved":["Saved (4 tiers updated)."]
}
```
