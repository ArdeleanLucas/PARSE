# Best practices for fieldwork

PARSE is built for careful linguistic review, not blind batch transcription. These practices keep recordings, annotations, and downstream comparative data auditable.

## Keep source data immutable
- Store original WAV/CSV files outside the git checkout when possible.
- Use `PARSE_WORKSPACE_ROOT` for runtime workspace state.
- Keep backups before large re-imports or destructive reruns.

## Work in reviewable passes
1. Import the speaker and verify basic metadata.
2. Check waveform/peaks before trusting generated boundaries.
3. Run STT/ORTH on a representative sample before a full batch.
4. Review lexical timing before IPA or cognate work.
5. Export a small subset before signing off a corpus-wide export.

## Treat automation as evidence, not authority
- ORTH and IPA output are starting points for human review.
- BND windows are weak hints unless they are reconciled with lexical evidence.
- If IPA coverage shrinks sharply, inspect upstream STT/ORTH coverage before accepting overwrite output.

## Make long recordings observable
- Keep default long-file chunking enabled for normal fieldwork.
- Lower chunk duration for fragile recordings rather than disabling chunking.
- Use job logs and per-chunk status to decide which span needs attention.

## Document local machine choices
Record local deviations such as CPU fallback, custom model paths, and workspace roots in your project notes. The shared repo should stay machine-neutral.

Related: [Processing long recordings](processing-long-recordings.md), [Environment variables](../reference/environment-variables.md), and [Configuration options](../reference/configuration.md).
