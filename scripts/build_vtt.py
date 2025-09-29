"""Utilities to align a Portuguese transcript and optional English translation
with an audio file and export a WebVTT subtitle file suitable for the player
included in this repository.

The script relies on `faster-whisper` for light-weight forced alignment.  The
alignment procedure transcribes the audio in European Portuguese, aligns the
word-level timestamps with the provided transcript, and emits cues that contain
both the original text and (optionally) an English translation.

Example usage:

    python scripts/build_vtt.py \
        --audio ./examples/podcast.mp3 \
        --portuguese ./examples/podcast.pt.txt \
        --english ./examples/podcast.en.txt \
        --model medium \
        --output ./examples/podcast.vtt

The Portuguese and English text files should contain exactly the same number of
non-empty lines once comments and blank rows are stripped.  Each line represents
a logical unit in the conversation (for example a speaker turn).  The script
tries to align each of those units with the best matching span in the audio.  If
alignment fails for a unit, the script falls back to an estimated duration based
on neighbouring cues so that the resulting file is still usable.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence

from faster_whisper import WhisperModel
from slugify import slugify


_WORD_RE = re.compile(r"\w+", re.UNICODE)


@dataclasses.dataclass
class TranscriptLine:
    """Represents a single unit in the user's reference transcript."""

    index: int
    text: str
    translation: Optional[str] = None


@dataclasses.dataclass
class Word:
    """Represents a recognized word with normalized text and timestamps."""

    text: str
    normalized: str
    start: float
    end: float


@dataclasses.dataclass
class Cue:
    """Represents a WebVTT cue."""

    identifier: str
    start: float
    end: float
    transcript: TranscriptLine

    def to_vtt(self) -> str:
        start = seconds_to_timestamp(self.start)
        end = seconds_to_timestamp(self.end)
        cue_body = f"<span class=\"pt\">{escape_vtt(self.transcript.text)}</span>"
        if self.transcript.translation:
            cue_body += "<br/><span class=\"en\">"
            cue_body += escape_vtt(self.transcript.translation)
            cue_body += "</span>"
        return f"{self.identifier}\n{start} --> {end}\n{cue_body}\n"


class AlignmentError(RuntimeError):
    """Raised when the alignment process fails fatally."""


def normalize_token(token: str) -> str:
    token = token.casefold()
    token = unicodedata.normalize("NFD", token)
    token = "".join(ch for ch in token if unicodedata.category(ch) != "Mn")
    token = re.sub(r"[^\w]", "", token)
    return token


def load_transcript(path: Path, translation_path: Optional[Path]) -> List[TranscriptLine]:
    def iter_lines(p: Path) -> Iterator[str]:
        for raw in p.read_text(encoding="utf-8").splitlines():
            stripped = raw.strip()
            if stripped and not stripped.startswith("#"):
                yield stripped

    portuguese_lines = list(iter_lines(path))
    translations: List[Optional[str]]

    if translation_path:
        english_lines = list(iter_lines(translation_path))
        if len(english_lines) != len(portuguese_lines):
            raise AlignmentError(
                "The Portuguese and English transcripts must have the same number of non-empty lines."
            )
        translations = english_lines
    else:
        translations = [None] * len(portuguese_lines)

    return [
        TranscriptLine(index=i, text=pt, translation=translations[i])
        for i, pt in enumerate(portuguese_lines)
    ]


def transcribe_audio(model: WhisperModel, audio_path: Path, *, language: str) -> List[Word]:
    """Transcribe the audio and return a flattened list of timestamped words."""

    segments, _ = model.transcribe(
        str(audio_path),
        language=language,
        beam_size=5,
        word_timestamps=True,
    )

    words: List[Word] = []
    for segment in segments:
        for word in segment.words:
            normalized = normalize_token(word.word)
            if not normalized:
                continue
            words.append(
                Word(
                    text=word.word,
                    normalized=normalized,
                    start=float(word.start),
                    end=float(word.end),
                )
            )
    if not words:
        raise AlignmentError("No words were recognized in the audio. Check the language parameter and audio quality.")
    return words


def align_transcript(lines: Sequence[TranscriptLine], words: Sequence[Word]) -> List[Cue]:
    cues: List[Cue] = []
    pointer = 0
    word_count = len(words)
    average_word_duration = sum(w.end - w.start for w in words) / max(word_count, 1)

    for line in lines:
        tokens = [normalize_token(token) for token in _WORD_RE.findall(line.text)]
        token_matches: List[int] = []

        for token in tokens:
            best_index = None
            best_score = 0.0
            search_window = range(pointer, min(pointer + 30, word_count))
            for idx in search_window:
                candidate = words[idx].normalized
                if not candidate:
                    continue
                if candidate == token:
                    best_index = idx
                    best_score = 1.0
                    break
                # Fallback to partial ratio to cope with punctuation differences.
                score = similarity(token, candidate)
                if score > best_score:
                    best_score = score
                    best_index = idx
            if best_index is not None and best_score >= 0.6:
                token_matches.append(best_index)
                pointer = best_index + 1

        if token_matches:
            start_word = words[token_matches[0]]
            end_word = words[token_matches[-1]]
            start_time = start_word.start
            end_time = end_word.end
        else:
            # Fallback: estimate a reasonable window around the current pointer.
            start_idx = min(pointer, word_count - 1)
            end_idx = min(start_idx + max(len(tokens), 1), word_count - 1)
            start_time = words[start_idx].start
            end_time = words[end_idx].end
            pointer = end_idx + 1

        # Guarantee strictly increasing timestamps.
        if cues:
            previous_end = cues[-1].end
            start_time = max(start_time, previous_end + 1e-3)
        if end_time <= start_time:
            end_time = start_time + max(average_word_duration, 0.3)

        identifier = f"line-{slugify(line.index, lowercase=False)}"
        cues.append(Cue(identifier=identifier, start=start_time, end=end_time, transcript=line))

    return cues


def seconds_to_timestamp(value: float) -> str:
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    seconds = int(value % 60)
    milliseconds = int(round((value - math.floor(value)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def escape_vtt(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def similarity(a: str, b: str) -> float:
    """Compute a simple similarity ratio between two strings."""

    if not a or not b:
        return 0.0
    matches = sum(1 for x, y in zip(a, b) if x == y)
    return matches / max(len(a), len(b))


def write_vtt(output_path: Path, cues: Sequence[Cue]) -> None:
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write("WEBVTT\n\n")
        for cue in cues:
            handle.write(cue.to_vtt())
            handle.write("\n")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True, help="Path to the MP3/MP4 audio file.")
    parser.add_argument(
        "--portuguese",
        type=Path,
        required=True,
        help="Path to the Portuguese transcript (one speaker turn per line).",
    )
    parser.add_argument(
        "--english",
        type=Path,
        help="Path to the English translation (one speaker turn per line).",
    )
    parser.add_argument(
        "--model",
        default="small",
        help="Name or path of the Whisper model to use (default: small).",
    )
    parser.add_argument(
        "--device",
        default="auto",
        help="Inference device for faster-whisper (auto, cpu, cuda).",
    )
    parser.add_argument(
        "--language",
        default="pt",
        help="Language code for the audio (default: pt for Portuguese).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output.vtt"),
        help="Destination path for the generated WebVTT file.",
    )
    parser.add_argument(
        "--dump-debug",
        type=Path,
        help="Optional path to export alignment diagnostics as JSON.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)

    transcript_lines = load_transcript(args.portuguese, args.english)
    model = WhisperModel(args.model, device=args.device)
    words = transcribe_audio(model, args.audio, language=args.language)
    cues = align_transcript(transcript_lines, words)
    write_vtt(args.output, cues)

    if args.dump_debug:
        debug_payload = {
            "audio": str(args.audio),
            "portuguese": str(args.portuguese),
            "english": str(args.english) if args.english else None,
            "model": args.model,
            "cues": [
                {
                    "index": cue.transcript.index,
                    "start": cue.start,
                    "end": cue.end,
                    "text": cue.transcript.text,
                    "translation": cue.transcript.translation,
                }
                for cue in cues
            ],
        }
        args.dump_debug.write_text(json.dumps(debug_payload, indent=2), encoding="utf-8")

    print(f"Generated {len(cues)} cues in {args.output}")


if __name__ == "__main__":
    main()
