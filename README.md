# MemeSong Studio

A local web app that aligns an `.mp3` and lyrics into word-level karaoke timings and renders **1080×1080 MP4** lyric videos ready to post on X.

## Features
- **Automatic Vocal Isolation + Forced Alignment:** Uses **Demucs** (`htdemucs`) to isolate vocals and **`stable-ts`** (Whisper forced alignment) to lock your exact lyric lines to word-level timestamps.
- **Live 1:1 Karaoke Preview:** Watch your video in real time in the browser with smooth word-by-word highlight sweeps before exporting.
- **Word Timing Editor:** Click any word to seek and nudge its start/end time (`±0.1s` or snap to playhead), or shift the whole song with the global sync offset slider.
- **Two Subtle Animated Backgrounds:**
  - **Animated Gradient:** 5 drifting color themes with subtle audio-reactive glow.
  - **Cover Image (Ken Burns):** Gentle centered zoom with subtle beat breathing, adjustable background dimming, and a localized dark gradient scrim behind the lyrics.
- **Clean Lyric Styling:** Single active line by default (with optional previous/next lines toggle), **Top / Center / Bottom** placement, **Off / Dark / White** text outline, and custom karaoke highlight color.
- **X-Ready MP4 Export:** Encodes `1080×1080`, `H.264` (`yuv420p`), `AAC` audio with `faststart`.

## Prerequisites
- [uv](https://docs.astral.sh/uv/) (manages Python 3.12 and dependencies)
- [FFmpeg](https://ffmpeg.org/) (`brew install ffmpeg` on macOS)

## Quick Start

```bash
uv sync
uv run python run.py
```

Then open **http://127.0.0.1:8765** in your browser.

> **First run note:** The first time you align a song with vocal isolation enabled, Demucs (~80 MB) and Whisper `base` (~140 MB) will download and cache their model weights automatically.
