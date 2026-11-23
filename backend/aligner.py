from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

import torch

_MODEL_CACHE: dict[str, object] = {}


def get_audio_duration(audio_path: Path) -> float:
    """Return duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    return float(out)


def separate_vocals(
    audio_path: Path,
    work_dir: Path,
    on_progress: Callable[[str, float], None] | None = None,
) -> Path:
    """Run Demucs two-stems vocal separation and return path to vocals.wav."""
    cached = work_dir / "vocals.wav"
    if cached.exists() and cached.stat().st_size > 0:
        if on_progress:
            on_progress("Using cached isolated vocals...", 0.35)
        return cached

    if on_progress:
        on_progress("Isolating vocals with Demucs (first run downloads model)...", 0.1)

    demucs_out = work_dir / "demucs_out"
    demucs_out.mkdir(parents=True, exist_ok=True)

    device = "mps" if torch.backends.mps.is_available() else "cpu"

    def _run(dev: str) -> subprocess.CompletedProcess[str]:
        cmd = [
            sys.executable,
            "-m",
            "demucs",
            "--two-stems=vocals",
            "-n",
            "htdemucs",
            "-d",
            dev,
            "-o",
            str(demucs_out),
            str(audio_path),
        ]
        return subprocess.run(cmd, capture_output=True, text=True)

    result = _run(device)
    if result.returncode != 0 and device == "mps":
        # Fallback to CPU if MPS hits an unsupported op
        if on_progress:
            on_progress("Retrying vocal separation on CPU...", 0.15)
        result = _run("cpu")

    if result.returncode != 0:
        raise RuntimeError(f"Demucs failed: {result.stderr[-800:]}")

    vocals_path = demucs_out / "htdemucs" / audio_path.stem / "vocals.wav"
    if not vocals_path.exists():
        matches = list(demucs_out.rglob("vocals.wav"))
        if not matches:
            raise FileNotFoundError("Demucs completed but vocals.wav was not found.")
        vocals_path = matches[0]

    vocals_path.replace(cached)
    if on_progress:
        on_progress("Vocals isolated.", 0.40)
    return cached


def _get_whisper_model(model_name: str):
    if model_name not in _MODEL_CACHE:
        import stable_whisper

        # CPU is fast and numerically stable on Apple Silicon for Whisper forced alignment
        _MODEL_CACHE[model_name] = stable_whisper.load_model(model_name, device="cpu")
    return _MODEL_CACHE[model_name]


def _normalize_token(text: str) -> str:
    return re.sub(r"[^a-z0-9']+", "", text.lower())


def _parse_lyric_lines(lyrics_text: str) -> list[list[str]]:
    """Split user lyrics into non-empty lines, each containing display word tokens."""
    lines: list[list[str]] = []
    for raw_line in lyrics_text.splitlines():
        cleaned = raw_line.strip()
        if not cleaned:
            continue
        # Skip common section headers like [Chorus], [Verse 1] if on their own line
        if re.fullmatch(r"\[[^\]]+\]", cleaned):
            continue
        words = cleaned.split()
        if words:
            lines.append(words)
    return lines


def _map_words_to_lines(
    lyric_lines: list[list[str]],
    aligned_words: list[dict],
    total_duration: float,
) -> list[dict]:
    """Map flat aligned word timings back onto the user's exact lyric lines."""
    expected_tokens: list[tuple[int, int, str]] = []
    for line_idx, words in enumerate(lyric_lines):
        for word_idx, word in enumerate(words):
            expected_tokens.append((line_idx, word_idx, word))

    if not expected_tokens:
        return []

    # Build aligned list with normalized keys
    aligned_norm = [
        (
            _normalize_token(w["word"]),
            float(w["start"]),
            float(w["end"]),
        )
        for w in aligned_words
        if w["word"].strip()
    ]

    # Greedy pointer alignment with small lookahead to stay synced if punctuation splits tokens
    mapped: list[tuple[float | None, float | None]] = [(None, None)] * len(expected_tokens)
    a_idx = 0
    n_aligned = len(aligned_norm)

    for e_idx, (_, _, word_text) in enumerate(expected_tokens):
        e_norm = _normalize_token(word_text)
        if not e_norm:
            continue
        if a_idx >= n_aligned:
            break

        # Look ahead up to 4 aligned tokens for a match
        found = -1
        for look in range(a_idx, min(a_idx + 5, n_aligned)):
            a_norm = aligned_norm[look][0]
            if a_norm == e_norm or (e_norm and a_norm and (e_norm.startswith(a_norm) or a_norm.startswith(e_norm))):
                found = look
                break

        if found != -1:
            start_t = aligned_norm[found][1]
            end_t = aligned_norm[found][2]
            # If the expected word was split into multiple sub-tokens (e.g. hyphenated), consume them
            next_idx = found + 1
            combined = aligned_norm[found][0]
            while next_idx < n_aligned and len(combined) < len(e_norm) and e_norm.startswith(combined + aligned_norm[next_idx][0]):
                combined += aligned_norm[next_idx][0]
                end_t = aligned_norm[next_idx][2]
                next_idx += 1
            mapped[e_idx] = (start_t, end_t)
            a_idx = next_idx
        else:
            # Fallback: take current aligned token directly so we don't drift
            mapped[e_idx] = (aligned_norm[a_idx][1], aligned_norm[a_idx][2])
            a_idx += 1

    # Interpolate any missing timings smoothly between known neighbors
    known_indices = [i for i, (s, e) in enumerate(mapped) if s is not None and e is not None]
    if not known_indices:
        # Total fallback: evenly space across song duration
        step = total_duration / max(len(mapped), 1)
        for i in range(len(mapped)):
            mapped[i] = (round(i * step, 3), round((i + 1) * step, 3))
    else:
        # Fill leading missing
        first_k = known_indices[0]
        if first_k > 0:
            first_start = mapped[first_k][0] or 0.0
            span_start = max(0.0, first_start - first_k * 0.35)
            step = (first_start - span_start) / first_k if first_start > span_start else 0.1
            for i in range(first_k):
                mapped[i] = (span_start + i * step, span_start + (i + 1) * step)

        # Fill interior gaps
        for idx_pos in range(len(known_indices) - 1):
            left = known_indices[idx_pos]
            right = known_indices[idx_pos + 1]
            gap = right - left - 1
            if gap > 0:
                t0 = mapped[left][1] or mapped[left][0] or 0.0
                t1 = mapped[right][0] or t0
                step = max((t1 - t0) / gap, 0.05)
                for g in range(gap):
                    mapped[left + 1 + g] = (t0 + g * step, t0 + (g + 1) * step)

        # Fill trailing missing
        last_k = known_indices[-1]
        if last_k < len(mapped) - 1:
            rem = len(mapped) - 1 - last_k
            t0 = mapped[last_k][1] or 0.0
            span_end = min(total_duration, t0 + rem * 0.4)
            step = max((span_end - t0) / rem, 0.05)
            for g in range(rem):
                mapped[last_k + 1 + g] = (t0 + g * step, min(total_duration, t0 + (g + 1) * step))

    # Reconstruct structured lines with monotonic clamped timestamps
    structured_lines: list[dict] = []
    flat_idx = 0
    prev_end = 0.0

    for line_idx, words in enumerate(lyric_lines):
        line_words: list[dict] = []
        for word_text in words:
            s, e = mapped[flat_idx]
            flat_idx += 1
            s = max(0.0, min(float(s or 0.0), total_duration))
            e = max(s + 0.05, min(float(e or (s + 0.2)), total_duration))
            if s < prev_end - 0.05:
                s = prev_end
                e = max(s + 0.05, e)
            prev_end = e
            line_words.append(
                {
                    "text": word_text,
                    "start": round(s, 3),
                    "end": round(e, 3),
                }
            )
        structured_lines.append(
            {
                "id": line_idx,
                "text": " ".join(words),
                "start": line_words[0]["start"],
                "end": line_words[-1]["end"],
                "words": line_words,
            }
        )

    return structured_lines


def align_lyrics(
    audio_path: Path,
    lyrics_text: str,
    work_dir: Path,
    *,
    isolate_vocals: bool = True,
    model_name: str = "base",
    language: str = "en",
    on_progress: Callable[[str, float], None] | None = None,
) -> dict:
    """Align lyrics_text to audio_path and return structured line/word timings."""
    duration = get_audio_duration(audio_path)
    lyric_lines = _parse_lyric_lines(lyrics_text)
    if not lyric_lines:
        raise ValueError("No lyric lines found. Please provide at least one line of lyrics.")

    target_audio = audio_path
    if isolate_vocals:
        target_audio = separate_vocals(audio_path, work_dir, on_progress=on_progress)
    elif on_progress:
        on_progress("Skipping vocal separation...", 0.35)

    if on_progress:
        on_progress(f"Loading Whisper '{model_name}' alignment model...", 0.45)
    model = _get_whisper_model(model_name)

    if on_progress:
        on_progress("Aligning lyrics to vocals...", 0.60)

    joined_text = "\n".join(" ".join(line) for line in lyric_lines)
    result = model.align(str(target_audio), joined_text, language=language, regroup=False)

    aligned_words = [
        {
            "word": w.word,
            "start": float(w.start),
            "end": float(w.end),
        }
        for w in result.all_words()
    ]

    if on_progress:
        on_progress("Mapping word timings to lyric lines...", 0.90)

    lines = _map_words_to_lines(lyric_lines, aligned_words, duration)

    data = {
        "duration": round(duration, 3),
        "lines": lines,
    }
    (work_dir / "timings.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    if on_progress:
        on_progress("Alignment complete!", 1.0)
    return data
