# PARSE IPA threading error — findings, proof, and reproducible demonstrations

## Executive summary

The recurring IPA failure is **not** a speaker-data problem and **not** a wav2vec2 decoding problem.
It is a **late PyTorch global-thread-configuration failure** in the lazy IPA aligner loader.

In the current PARSE runtime:

1. `server.py` reaches IPA as the last step of the full pipeline.
2. `_get_ipa_aligner()` lazy-loads the wav2vec2 aligner on first IPA use.
3. Under WSL, `forced_align.resolve_device()` forces the aligner to **CPU**.
4. The CPU branch of `Aligner.load()` calls:
   - `torch.set_num_threads(1)`
   - `torch.set_num_interop_threads(1)`
5. PyTorch rejects that inter-op thread call once the process has already fixed that setting or already started the relevant parallel work.

That is why the error repeats speaker after speaker: the aligner never finishes loading successfully, so PARSE retries the same failing lazy-load path on the next speaker.

---

## Exact traceback

```text
Traceback (most recent call last):
  File "/home/lucas/gh/ardeleanlucas/parse/python/server.py", line 5565, in _compute_full_pipeline
    sub_result = _compute_speaker_ipa(
                 ^^^^^^^^^^^^^^^^^^^^^
  File "/home/lucas/gh/ardeleanlucas/parse/python/server.py", line 4396, in _compute_speaker_ipa
    aligner = _get_ipa_aligner()
              ^^^^^^^^^^^^^^^^^^
  File "/home/lucas/gh/ardeleanlucas/parse/python/server.py", line 4261, in _get_ipa_aligner
    _IPA_ALIGNER = Aligner.load(device=_ipa_device)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/lucas/gh/ardeleanlucas/parse/python/ai/forced_align.py", line 183, in load
    torch.set_num_interop_threads(1)
RuntimeError: Error: cannot set number of interop threads after parallel work has started or set_num_interop_threads called
```

---

## Source-level proof

### 1) The full pipeline reaches IPA last

`python/server.py`:

```python
elif step == "ipa":
    sub_result = _compute_speaker_ipa(
        job_id,
        {"speaker": speaker, "overwrite": overwrites.get("ipa", False)},
    )
```

This means the IPA stage is entered **after** the earlier pipeline activity in the same long-lived server process.

### 2) IPA lazy-loads the aligner inside the server process

`python/server.py`:

```python
def _get_ipa_aligner() -> Any:
    global _IPA_ALIGNER
    if _IPA_ALIGNER is not None:
        return _IPA_ALIGNER
    ...
    _IPA_ALIGNER = Aligner.load(device=_ipa_device)
    return _IPA_ALIGNER
```

So the wav2vec2 aligner is not configured at process startup; it is loaded **on demand**, late in the job lifecycle.

### 3) WSL forces wav2vec2 IPA onto CPU

`python/ai/forced_align.py`:

```python
def resolve_device(requested: Optional[str] = None) -> str:
    if requested == "cpu":
        return "cpu"
    if _is_wsl():
        return "cpu"
    ...
```

Actual command run on this machine:

```bash
$ /usr/bin/python3 - <<'PY'
import sys, pathlib
sys.path.insert(0, str(pathlib.Path('/home/lucas/gh/ardeleanlucas/parse/python')))
import ai.forced_align as fa
print(fa.resolve_device('cuda'))
PY
cpu
```

Even though `config/ai_config.json` requests `"wav2vec2": {"device": "cuda"}`, the current WSL runtime forces this path to CPU.

### 4) The CPU branch calls PyTorch's global thread setters

`python/ai/forced_align.py`:

```python
resolved_device = resolve_device(device)
...
if resolved_device == "cpu":
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
```

That second call is the one raising in the traceback.

---

## Why this is a runtime-order bug, not a data bug

This failure happens **before** any speaker-specific IPA output is produced.
The exception is raised during aligner initialization, not during phoneme decoding of a particular interval.

So the bug is not:
- malformed audio,
- bad timestamps,
- corrupt annotations,
- invalid IPA tokens,
- or a model inference result.

It is a **process-global configuration timing error**.

---

## Reproducible demonstrations

## Demonstration A — the exact PyTorch error appears when the inter-op setting is already frozen

Minimal PyTorch proof:

```bash
$ /usr/bin/python3 - <<'PY'
import torch

torch.set_num_interop_threads(1)
try:
    torch.set_num_interop_threads(1)
except RuntimeError as exc:
    print(type(exc).__name__)
    print(str(exc))
PY
RuntimeError
Error: cannot set number of interop threads after parallel work has started or set_num_interop_threads called
```

This proves that `torch.set_num_interop_threads()` is not a normal per-call option — it is effectively an early/one-shot global setting.

## Demonstration B — the real PARSE code path reproduced the failure before the fix

To avoid downloading the full wav2vec2 stack while still exercising the repository code path, I ran the real `Aligner.load(..., device='cpu')` function with:
- **real** PyTorch from `/usr/bin/python3`, and
- **fake** transformers classes injected via `sys.modules`.

Historical reproducer (run before the fix in this PR):

```python
import pathlib
import sys
import types
import torch

sys.path.insert(0, '/home/lucas/gh/ardeleanlucas/parse/python')

fake_transformers = types.ModuleType('transformers')

class _FakeTokenizer:
    pad_token = '<pad>'
    @classmethod
    def from_pretrained(cls, model_name):
        return cls()
    def get_vocab(self):
        return {'<pad>': 0, 'a': 1}

class _FakeFeatureExtractor:
    @classmethod
    def from_pretrained(cls, model_name):
        return cls()

class _FakeProcessor:
    def __init__(self, feature_extractor=None, tokenizer=None):
        self.feature_extractor = feature_extractor
        self.tokenizer = tokenizer
    @classmethod
    def from_pretrained(cls, model_name):
        return cls(feature_extractor=_FakeFeatureExtractor(), tokenizer=_FakeTokenizer())

class _FakeModel:
    @classmethod
    def from_pretrained(cls, model_name):
        return cls()
    def to(self, device):
        return self
    def eval(self):
        return self

fake_transformers.Wav2Vec2CTCTokenizer = _FakeTokenizer
fake_transformers.Wav2Vec2FeatureExtractor = _FakeFeatureExtractor
fake_transformers.Wav2Vec2Processor = _FakeProcessor
fake_transformers.Wav2Vec2ForCTC = _FakeModel
sys.modules['transformers'] = fake_transformers

from ai.forced_align import Aligner

torch.set_num_interop_threads(1)
Aligner.load(model_name='dummy', device='cpu')
```

Observed output on this machine:

```text
RuntimeError
Error: cannot set number of interop threads after parallel work has started or set_num_interop_threads called
Traceback (most recent call last):
  File "/tmp/parse_ipa_thread_repro.py", line 51, in <module>
    Aligner.load(model_name='dummy', device='cpu')
  File "/home/lucas/gh/worktrees/parse/ipa-threading-proof/python/ai/forced_align.py", line 183, in load
    torch.set_num_interop_threads(1)
RuntimeError: Error: cannot set number of interop threads after parallel work has started or set_num_interop_threads called
```

This is the strongest evidence in the investigation: it reproduced the **same error string** at the **same repository call site** (`forced_align.py` line 183) without needing the full production model load.

---

## Fix implemented in this PR

The bug fix keeps the CPU single-thread preference but stops treating late
PyTorch inter-op configuration as fatal.

New helper in `python/ai/forced_align.py`:

```python
def _configure_torch_cpu_thread_limits(torch_module: Any) -> None:
    global _CPU_THREAD_LIMITS_CONFIGURED
    if _CPU_THREAD_LIMITS_CONFIGURED:
        return

    with _CPU_THREAD_LIMITS_LOCK:
        if _CPU_THREAD_LIMITS_CONFIGURED:
            return

        torch_module.set_num_threads(1)
        try:
            torch_module.set_num_interop_threads(1)
        except RuntimeError as exc:
            if "cannot set number of interop threads" not in str(exc):
                raise
            print(
                "[ALIGN] torch interop threads already configured; continuing with existing setting.",
                file=sys.stderr,
                flush=True,
            )
        _CPU_THREAD_LIMITS_CONFIGURED = True
```

And `Aligner.load()` now does:

```python
if resolved_device == "cpu":
    _configure_torch_cpu_thread_limits(torch)
```

### Why this is the right fix

- It addresses the real root cause: `set_num_interop_threads()` is a one-shot
  global setting, but the aligner was trying to set it inside a late lazy load.
- It preserves the original intent (`set_num_threads(1)` on CPU).
- It makes the late lazy-load path safe in the long-lived threaded server.
- It avoids repeating the same failing `set_num_interop_threads()` call after
  the first successful or already-frozen attempt.

### Post-fix demonstration

After the fix, the same style of subprocess repro succeeds instead of crashing:

```text
[ALIGN] torch interop threads already configured; continuing with existing setting. current=1
ALIGNER_OK cpu
```

---

## Confirmation test added to the repo

File added:

- `python/ai/test_forced_align_threading.py`

What it now confirms:

1. `resolve_device()` forces CPU on WSL.
2. The CPU branch of `Aligner.load()` calls `torch.set_num_threads(1)` and `torch.set_num_interop_threads(1)`.
3. If PyTorch reports that inter-op threads are already frozen, PARSE now treats that condition as benign and still loads the aligner.
4. The real repository code path now succeeds in a subprocess using real PyTorch even when `torch.set_num_interop_threads(1)` has already been called.

Recommended command:

```bash
pytest python/ai/test_forced_align_threading.py -q
```

Observed result on this machine after the fix:

```text
....                                                                     [100%]
4 passed in 1.90s
```

Additional validation run before shipping this branch:

```text
pytest python/ai/test_forced_align.py python/ai/test_forced_align_threading.py -q
..............                                                           [100%]
14 passed in 1.88s

npm run test -- --run
40 passed / 272 tests

./node_modules/.bin/tsc --noEmit
(exit 0)
```

---

## What we can say with high confidence

### Confirmed

- The failure originated in the **lazy aligner loader**, not in speaker-specific IPA decoding.
- Under this runtime, wav2vec2 IPA is on the **CPU** branch.
- That CPU branch calls `torch.set_num_interop_threads(1)`.
- Before this fix, the exact repository code path reproduced the same RuntimeError.
- After this fix, the same code path tolerates the already-frozen inter-op setting and continues loading the aligner.
- The original placement of the raw `set_num_interop_threads(1)` call inside a late lazy loader was unsafe in a long-lived threaded server process.

### Important nuance

PyTorch's message merges two possibilities into one string:

- parallel work has already started, **or**
- `set_num_interop_threads()` was already called.

The reproduction above definitively proves the **one-shot / already-fixed** branch.
The PARSE architecture definitively proves the **late lazy-load** part.
Together, those facts are sufficient to explain why this call site is brittle and why the error repeats across speakers.

---

## Practical conclusion

The pre-fix IPA error meant:

> PARSE was trying to configure PyTorch's global inter-op thread policy too late, inside a lazy-loaded CPU wav2vec2 aligner, after the long-lived server process had already reached a state where PyTorch no longer allowed that setting to change.

This fix changes that late lazy-load path from **fatal** to **tolerant** for the specific already-frozen inter-op-thread condition, while preserving the CPU single-thread preference that motivated the original code.
