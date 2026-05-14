# How long-file processing works

PARSE treats a long recording like a field notebook that is too large to review in one sitting: it keeps the original timeline, works through manageable sections, and tells you which sections are safe to review.

The important idea is simple:

```text
one long speaker recording
  -> split heavy STT/ORTH work into time slices
  -> protect the model work in a child process
  -> merge good output back onto the same speaker timeline
  -> show which spans are complete, partial, failed, or cancelled
```

You still review one speaker in Annotate mode. Chunking is only how PARSE makes the machine work safer and easier to diagnose.

## In plain language

| Term | What it means for a user |
|---|---|
| Chunk | A time slice of the same recording, such as 00:10:00-00:20:00. |
| Subprocess isolation | PARSE puts risky model work in a protected child process so a crash is less likely to take down the server. |
| Partial result | Some slices succeeded and some did not. Keep the useful evidence, then focus on the failed spans. |
| Coverage | How much of the recording or interval inventory actually has usable output, not just whether a tier exists. |

## What gets chunked

- **Full-file STT** chunks long recordings before speech-to-text.
- **Full-mode ORTH** chunks the rough transcription pass, then aligns once over the merged output.
- **IPA** follows the existing intervals. It does not split a whole WAV by duration, but it warns when an overwrite would cover much less audio than before.

Short concept-window or edited-only reruns stay fast and bounded. They are meant for fixing one word, one prompt, or one suspicious interval after the broader run.

## What users see

During a healthy long run, the UI should move from general startup to visible chunk progress:

```text
starting job -> loading model -> STT chunk 1/18 -> STT chunk 2/18 -> ... -> report
```

After the run, look at three things before trusting the output:

1. **Result category:** success, partial, cancelled, empty, or error.
2. **Chunk table:** if present, which spans failed and why.
3. **Annotation coverage:** whether the generated tiers cover the part of the recording you care about.

A green technical result is not the same as linguistic sign-off. It only means PARSE produced output that is ready for human review.

## When the result is partial

Partial is not automatically bad. It means PARSE preserved what worked and pointed at what did not.

| If you see... | Do this first |
|---|---|
| One failed chunk | Open that time span in Annotate; decide whether to rerun the stage or repair only the affected intervals. |
| Many failed chunks with the same error | Check device, memory, model config, and chunk size before rerunning. |
| Good STT but poor ORTH in one prompt | Use concept-window or per-lexeme reruns rather than reprocessing the full file. |
| IPA coverage shrank | Inspect STT/ORTH intervals before accepting IPA overwrite output. |

## Why this matters for fieldwork

Long recordings often contain silence, overlapping speech, noisy rooms, repeated prompts, or scanner/provider edge cases. Without chunking, one bad section can make the whole stage look mysterious. With chunking, the report can say: "this ten-minute span failed; these other spans are available for review."

That makes PARSE more useful in the field: you can keep moving, keep notes, and come back to the exact weak span instead of restarting a multi-hour job blindly.

Related: [Compute architecture](compute.md), [Chunking and subprocess isolation](chunking.md), [Processing long recordings](../user-guides/processing-long-recordings.md), and [Job result schema](../reference/job-results.md).
