#!/usr/bin/env python3
"""Generate orthographic transcriptions for PARSE coarse transcripts using razhan/whisper-base-sdh."""
import json, os, sys, csv, argparse, time

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--speaker', help='Speaker ID (e.g. Kalh01)')
    parser.add_argument('--all', action='store_true', help='Process all speakers')
    parser.add_argument('--thesis-dir', default='/mnt/c/Users/Lucas/Thesis', help='Thesis directory')
    args = parser.parse_args()

    from faster_whisper import WhisperModel

    model_candidates = [
        "razhan/whisper-base-sdh",
        os.path.expanduser("~/.cache/ctranslate2/razhan-whisper-base-sdh-fp16"),
    ]

    model = None
    model_source = None
    model_device = None
    last_error = None

    # Try CUDA first, fall back to CPU. The installed working model is cached as
    # a local CTranslate2 conversion, so try both the HF repo id and the local path.
    for model_name in model_candidates:
        try:
            model = WhisperModel(model_name, device="cuda", compute_type="float16")
            model_source = model_name
            model_device = "cuda"
            print(f"Using CUDA ({model_name})")
            break
        except Exception as e:
            last_error = e

    if model is None:
        for model_name in model_candidates:
            try:
                model = WhisperModel(model_name, device="cpu", compute_type="int8")
                model_source = model_name
                model_device = "cpu"
                print(f"Using CPU ({model_name})")
                break
            except Exception as e:
                last_error = e

    if model is None:
        raise last_error

    transcript_dir = os.path.join(args.thesis_dir, 'coarse_transcripts')
    processed_dir = os.path.join(args.thesis_dir, 'Audio_Processed')

    if args.all:
        # Find all speakers with segment directories
        speakers = []
        for d in os.listdir(processed_dir):
            if d.endswith('_process'):
                spk = d.replace('_process', '')
                seg_dir = os.path.join(processed_dir, d, 'segments')
                transcript_file = os.path.join(transcript_dir, f'{spk}.json')
                if os.path.isdir(seg_dir) and os.path.isfile(transcript_file):
                    speakers.append(spk)
        print(f"Found {len(speakers)} speakers: {speakers}")
    elif args.speaker:
        speakers = [args.speaker]
    else:
        print("Specify --speaker or --all")
        sys.exit(1)

    for spk in speakers:
        print(f"\n{'='*60}")
        print(f"Processing {spk}...")
        
        # Load coarse transcript
        transcript_path = os.path.join(transcript_dir, f'{spk}.json')
        with open(transcript_path) as f:
            transcript = json.load(f)
        
        segments = transcript['segments']
        print(f"  {len(segments)} segments in transcript")
        
        # Load transcription CSV to map IPA → segment filename
        process_dir = os.path.join(processed_dir, f'{spk}_process')
        csv_path = os.path.join(process_dir, f'{spk}_transcriptions.csv')
        seg_dir = os.path.join(process_dir, 'segments')
        
        # Build IPA → WAV path lookup from CSV
        ipa_to_wav = {}
        if os.path.isfile(csv_path):
            with open(csv_path, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ipa = row.get('ipa', '').strip()
                    lexeme_id = row.get('lexeme_id', '').strip()
                    # WAV filename from lexeme_id
                    wav_name = f"{lexeme_id}.wav"
                    wav_path = os.path.join(seg_dir, wav_name)
                    if ipa and os.path.isfile(wav_path):
                        if ipa not in ipa_to_wav:
                            ipa_to_wav[ipa] = []
                        ipa_to_wav[ipa].append(wav_path)
            print(f"  {len(ipa_to_wav)} unique IPA forms mapped to WAV files")
        
        # Also build a list of ALL segment WAVs for direct transcription
        all_wavs = sorted([os.path.join(seg_dir, f) for f in os.listdir(seg_dir) if f.endswith('.wav')]) if os.path.isdir(seg_dir) else []
        print(f"  {len(all_wavs)} segment WAV files found")
        
        # Strategy: transcribe ALL segment WAVs and build filename→ortho lookup
        wav_to_ortho = {}
        t0 = time.time()
        for i, wav_path in enumerate(all_wavs):
            try:
                try:
                    segs_out, info = model.transcribe(wav_path, language="sd", beam_size=5)
                    texts = [s.text for s in segs_out]
                except Exception as e:
                    if model_device == "cuda":
                        print(f"  CUDA inference failed, switching to CPU: {e}")
                        model = WhisperModel(model_source, device="cpu", compute_type="int8")
                        model_device = "cpu"
                        segs_out, info = model.transcribe(wav_path, language="sd", beam_size=5)
                        texts = [s.text for s in segs_out]
                    else:
                        raise

                ortho = " ".join(texts).strip()
                wav_to_ortho[os.path.basename(wav_path)] = ortho
            except Exception as e:
                wav_to_ortho[os.path.basename(wav_path)] = ""
                print(f"  WARNING: Failed on {os.path.basename(wav_path)}: {e}")
            
            if (i + 1) % 50 == 0:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed
                print(f"  {i+1}/{len(all_wavs)} done ({rate:.1f} files/sec)")
        
        elapsed = time.time() - t0
        print(f"  Transcribed {len(all_wavs)} files in {elapsed:.1f}s")
        
        # Now map ortho back to transcript segments via CSV
        # CSV rows are in same order as transcript segments (both 543 entries)
        if os.path.isfile(csv_path):
            csv_rows = []
            with open(csv_path, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    csv_rows.append(row)
            
            if len(csv_rows) == len(segments):
                # Direct 1:1 mapping
                for i, (seg, row) in enumerate(zip(segments, csv_rows)):
                    lexeme_id = row.get('lexeme_id', '').strip()
                    wav_name = f"{lexeme_id}.wav"
                    seg['ortho'] = wav_to_ortho.get(wav_name, '')
                print(f"  Mapped {len(segments)} ortho values (1:1 CSV-transcript alignment)")
            else:
                print(f"  WARNING: CSV has {len(csv_rows)} rows but transcript has {len(segments)} segments")
                # Fall back: match by IPA text
                matched = 0
                for seg in segments:
                    ipa = seg.get('text', '')
                    wavs = ipa_to_wav.get(ipa, [])
                    if wavs:
                        wav_name = os.path.basename(wavs[0])
                        seg['ortho'] = wav_to_ortho.get(wav_name, '')
                        matched += 1
                print(f"  Matched {matched}/{len(segments)} by IPA text")
        else:
            print(f"  No CSV found — cannot map ortho to transcript segments")
        
        # Save updated transcript
        with open(transcript_path, 'w', encoding='utf-8') as f:
            json.dump(transcript, f, ensure_ascii=False, indent=2)
        print(f"  Saved updated transcript to {transcript_path}")
        
        # Show first 5
        print(f"\n  First 5 segments:")
        for s in segments[:5]:
            print(f"    {s.get('text',''):15s}  ortho={s.get('ortho',''):20s}  {s['start']:.1f}-{s['end']:.1f}s")

if __name__ == '__main__':
    main()
