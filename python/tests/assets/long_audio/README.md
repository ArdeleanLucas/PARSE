# PARSE long-audio real-WAV regression asset

This directory is reserved for the MC-384-O real-WAV STT chunking regression fixture.

## Current status

No redistributable audio slice is committed in this PR. Lucas still needs to select and approve a real Kurdish field-recording slice for public-repo distribution.

The regression code supports Plan B download-on-demand:

```bash
PARSE_RUN_LONG_AUDIO=1 \
PARSE_LONG_AUDIO_URL="https://example.invalid/parse_long_audio_001.wav" \
PYTHONPATH=python python3 -m pytest -q -m long_audio --run-long-audio
```

The downloaded file is cached at `/tmp/parse-long-audio/parse_long_audio_001.wav` and is not committed.

## Required metadata when an asset is approved

When Lucas approves a redistributable slice, place it here as:

- `parse_long_audio_001.wav`

Then replace this status block with:

- Source recording / slice: `<speaker-code> <start-time>–<end-time>`
- Duration: `<seconds>`
- Language: `<code>`
- Sample rate: `<Hz>`
- Channels: `<mono/stereo>`
- File size: `<MB>`
- Permission: `Lucas Ardelean grants permission to redistribute this slice under <chosen license> for testing purposes, <date>.`

Asset discipline: keep the committed file under 100 MB hard limit, ideally under 50 MB.
