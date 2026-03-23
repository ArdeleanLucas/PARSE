# Review — `js/parse.js`

## Overall

The file has a sensible top-level structure: clear module registration, explicit destroy logic, HTML escaping for header text, and a mostly sound fullscreen reparent/restore approach. I did **not** find a `[CRITICAL]` issue in this file.

The main problems are two blocking integration risks:
1. singleton context switches do **not** emit the documented cleanup event, and
2. persisted `se-decisions` state can be silently skipped depending on shell load order.

## Findings

### [MAJOR] Context switches bypass `se:panel-close`, breaking the cleanup contract
**Lines:** 442-457

`INTERFACES.md` defines `se:panel-close` as the cleanup signal that other modules listen to. But when a new `se:panel-open` arrives while the panel is already open, this file calls `_closePanel()` directly and then `_openPanel(detail)`.

That means the most important singleton handoff path is **silent** from the rest of the system's point of view. Modules like the waveform, transcript, suggestions, and region manager may keep stale listeners, stale regions, in-flight fetches, or audio state if they rely on `se:panel-close` for teardown.

Why this matters:
- the project plan explicitly relies on singleton orchestration to avoid overlapping heavy UI state,
- `INTERFACES.md` documents `se:panel-close` as the cross-module cleanup event,
- this code makes cleanup correctness depend on every downstream module also being able to self-heal on repeated `se:panel-open` events.

**Suggested fix:** when switching contexts, emit `se:panel-close` first and only open the new context after teardown completes (for example by queueing the pending open, or by centralizing teardown in one shared transition method that preserves the event contract).

### [MAJOR] Persisted assignments are skipped whenever `SE.decisions` is preloaded with any non-empty object
**Lines:** 699-706

`init()` only reads `localStorage['se-decisions']` if `SE.decisions` is missing or empty:

```js
if (!SE.decisions || Object.keys(SE.decisions).length === 0) {
  const rawDec = localStorage.getItem('se-decisions');
  ...
}
```

In the documented architecture, the shell may already preload a decisions JSON object on page load. If that object is non-empty but does **not** contain the latest locally persisted `source_regions`, this module skips local storage entirely.

Result: “assignments survive page reload” becomes integration-order dependent and can silently fail.

This directly conflicts with the project plan / definition of done expectation that source-region assignments persist and survive reloads.

**Suggested fix:** always read the persisted `se-decisions` payload and deep-merge `source_regions` into the in-memory `SE.decisions` object, instead of treating any non-empty shell-provided object as authoritative.

### [MINOR] Badge insertion logic can create duplicate badges and invalid table DOM
**Lines:** 592-614, 617-640

`_updateFormRowIndicator()` first appends a badge to any generic element matching `[data-concept-id][data-speaker]`, then separately appends a badge near matching buttons.

In layouts where both the row and the button carry those attributes—which the comments explicitly anticipate—you can end up with duplicate badges. Also, appending a `<span>` directly to a `<tr>` is invalid table markup and may render unpredictably.

**Suggested fix:** pick one canonical anchor near the 🔍 button, or dedupe candidate containers before inserting anything. Avoid appending badges directly to row-level table elements.

### [MINOR] Fullscreen toggles are accepted even when the panel is closed
**Lines:** 271-287, 472-483

`_onFullscreenToggle()` has no `_isOpen` guard. A stray `se:fullscreen-toggle` event can move the hidden panel into the fullscreen overlay and unhide the overlay, leaving fullscreen state out of sync with actual panel visibility.

This is easy to avoid defensively, and it would make the module less brittle when other fullscreen-related code lands.

**Suggested fix:** ignore fullscreen toggle events unless the panel is currently open (or at least unless a valid current context exists).

### [MINOR] The module ignores its `containerEl` contract and relies on document-global selectors
**Lines:** 89-99, 675-681, 592-607

`init(containerEl)` stores the container but almost every lookup is done with document-global IDs / selectors. That makes the module tightly coupled to one exact page shape and undermines the init-contract pattern described in `INTERFACES.md`.

This is mostly a maintainability/testability problem, but it also increases the chance of accidental collisions if the host page grows more complex.

**Suggested fix:** scope lookups to the provided container wherever possible, or clearly separate panel-internal lookups from deliberate host-page integration hooks.

### [NIT] The 1..82 navigation fallback is a hard-coded magic number
**Lines:** 345-349

If neither suggestions nor decisions are available, navigation falls back to a hard-coded `1..82` concept list. That works for the current thesis dataset, but it bakes domain-specific cardinality into the orchestrator.

**Suggested fix:** derive the concept list from shared data/config instead of hard-coding the count here.

## Positives

- `_escHtml()` is applied to dynamic header text, so the `innerHTML` path is not obviously XSS-prone.
- `_inlineParent` + `_inlineNextSib` is the right basic strategy for fullscreen reparent/restore without losing original DOM order.
- `destroy()` does remove global listeners and restores inline DOM state, which is a good sign for lifecycle hygiene.
