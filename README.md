# Notebook LM Podcast Transcript Runner

This project helps you align Notebook LM generated podcast transcripts with the
original Portuguese audio and play them back locally on your Android phone (or
any modern browser) with synchronized bilingual subtitles.

## Repository structure

```
├── scripts/
│   └── build_vtt.py      # CLI tool to align transcripts and generate WebVTT
├── webapp/
│   ├── index.html        # Offline-friendly audio player UI
│   ├── script.js         # Transcript rendering and synchronization logic
│   └── styles.css        # Visual styling
└── requirements.txt      # Python dependencies for alignment
```

## 1. Generate a WebVTT transcript

Use the `build_vtt.py` script to align your Portuguese transcript (and optional
English translation) with the MP3/MP4 audio exported from Notebook LM.

1. Install Python dependencies (Python 3.9+ recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

   > The script relies on [faster-whisper](https://github.com/guillaumekln/faster-whisper),
   > which downloads the requested Whisper model on first use. `small` is a good
   > default, but you can switch to `medium` for better accuracy if your device
   > has enough RAM.

2. Prepare two plain-text files:
   - `podcast.pt.txt`: Portuguese transcript, one speaker turn per line.
   - `podcast.en.txt`: English translation, also one line per speaker turn (must
     have the same number of non-empty lines as the Portuguese file).

3. Run the alignment script:

   ```bash
   python scripts/build_vtt.py \
     --audio path/to/podcast.mp3 \
     --portuguese path/to/podcast.pt.txt \
     --english path/to/podcast.en.txt \
     --model small \
     --output path/to/podcast.vtt
   ```

   - Omit `--english` if you only want the Portuguese transcript.
   - Use `--dump-debug alignment.json` to inspect the computed cue boundaries.
   - If the audio is MP4, pass the path as `--audio path/to/podcast.mp4` (the
     script extracts audio automatically via ffmpeg shipped with `faster-whisper`).

The result is a WebVTT file where each cue contains both the Portuguese line and
its English translation using `<span class="pt">` and `<span class="en">` blocks.

## 2. Load the files in the local player

The `webapp/` folder contains a lightweight player that runs entirely offline in
your mobile browser.

1. Copy `webapp/` to your phone (or serve it locally with a static file server).
2. Open `index.html` in Chrome/Firefox on Android. You can add it to your home
   screen for quick access.
3. Tap **Audio file** and select the podcast MP3/MP4 file.
4. Tap **Transcript** and select the generated `.vtt` file.
5. Playback controls will stay in sync with the transcript. Tap any cue to jump
   to that segment. Toggle the translation visibility with the checkbox.

Because everything happens client-side, your files remain on-device—nothing is
uploaded to the internet.

## Tips for better alignments

- Make sure the Portuguese transcript closely matches the spoken audio (same
  punctuation and speaker turns). When transcripts differ significantly, use the
  `--dump-debug` output to spot cues that might need manual adjustment.
- Consider using higher-quality Whisper models (`medium`, `large-v2`) for
  trickier audio. They take longer to download but greatly improve accuracy.
- You can fine-tune cue timings manually by editing the generated `.vtt` file
  in any text editor—the player will pick up your adjustments automatically.

## Roadmap ideas

- Optional playback speed controls and looping for focused practice.
- Support for exporting/ importing Anki cards per cue.
- On-device storage of recent sessions.
