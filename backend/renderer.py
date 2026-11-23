from __future__ import annotations

import math
import subprocess
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

VIDEO_SIZE = 1080
FPS = 30

THEMES: dict[str, dict[str, tuple[int, int, int] | str]] = {
    "midnight": {
        "bg1": (9, 13, 31),
        "bg2": (24, 18, 66),
        "orb1": (56, 189, 248),
        "orb2": (168, 85, 247),
        "accent": "#38bdf8",
    },
    "sunset": {
        "bg1": (24, 10, 28),
        "bg2": (64, 18, 44),
        "orb1": (249, 115, 22),
        "orb2": (236, 72, 153),
        "accent": "#fb923c",
    },
    "emerald": {
        "bg1": (6, 24, 22),
        "bg2": (12, 54, 48),
        "orb1": (52, 211, 153),
        "orb2": (45, 212, 191),
        "accent": "#34d399",
    },
    "gold": {
        "bg1": (18, 15, 11),
        "bg2": (46, 33, 17),
        "orb1": (251, 191, 36),
        "orb2": (245, 158, 11),
        "accent": "#fbbf24",
    },
    "monochrome": {
        "bg1": (10, 10, 14),
        "bg2": (32, 33, 42),
        "orb1": (148, 163, 184),
        "orb2": (226, 232, 240),
        "accent": "#f8fafc",
    },
}


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (56, 189, 248)


def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/System/Library/Fonts/SFNS.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        if bold
        else [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/System/Library/Fonts/SFNS.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    for path in candidates:
        if Path(path).exists():
            try:
                index = 1 if (bold and path.endswith("HelveticaNeue.ttc")) else 0
                return ImageFont.truetype(path, size=size, index=index)
            except OSError:
                continue
    return ImageFont.load_default()


def extract_audio_envelope(audio_path: Path, fps: int, total_frames: int) -> np.ndarray:
    """Compute a smoothed per-frame [0..1] RMS audio energy envelope using ffmpeg."""
    sample_rate = 8000
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(audio_path),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "f32le",
        "-",
    ]
    raw = subprocess.check_output(cmd)
    samples = np.frombuffer(raw, dtype=np.float32)
    if samples.size == 0:
        return np.zeros(total_frames, dtype=np.float32)

    samples_per_frame = max(1, sample_rate // fps)
    energies = np.zeros(total_frames, dtype=np.float32)
    for i in range(total_frames):
        s0 = i * samples_per_frame
        s1 = min(samples.size, s0 + samples_per_frame)
        if s0 < samples.size:
            chunk = samples[s0:s1]
            energies[i] = float(np.sqrt(np.mean(chunk * chunk)))

    # Normalize to 95th percentile so loud peaks don't crush everything else
    p95 = float(np.percentile(energies, 95)) if energies.size else 1.0
    if p95 > 1e-6:
        energies = np.clip(energies / p95, 0.0, 1.0)

    # Exponential smoothing for organic visual pulse
    smoothed = np.zeros_like(energies)
    val = 0.0
    for i in range(total_frames):
        alpha = 0.25 if energies[i] > val else 0.12
        val = val + alpha * (energies[i] - val)
        smoothed[i] = val
    return smoothed


def _prepare_cover_image(image_path: Path, size: int) -> Image.Image:
    """Load cover image and scale up slightly for gentle Ken Burns zoom headroom."""
    img = Image.open(image_path).convert("RGB")
    target = int(size * 1.12)
    w, h = img.size
    scale = max(target / w, target / h)
    new_w, new_h = int(round(w * scale)), int(round(h * scale))
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - target) // 2
    top = (new_h - target) // 2
    img = img.crop((left, top, left + target, top + target))
    return img


def _make_gradient_bg(
    t: float,
    energy: float,
    theme: dict,
    grid_x: np.ndarray,
    grid_y: np.ndarray,
    size: int,
) -> Image.Image:
    """Render a smooth animated multi-stop gradient with drifting ambient orbs and audio pulse."""
    bg1 = np.array(theme["bg1"], dtype=np.float32)
    bg2 = np.array(theme["bg2"], dtype=np.float32)
    orb1 = np.array(theme["orb1"], dtype=np.float32)
    orb2 = np.array(theme["orb2"], dtype=np.float32)

    # Diagonal shifting base gradient
    angle = t * 0.15
    mix = 0.5 + 0.5 * (grid_x * math.cos(angle) + grid_y * math.sin(angle))
    mix = np.clip(mix, 0.0, 1.0)[..., None]
    frame = bg1 * (1.0 - mix) + bg2 * mix

    # Orb 1 drifting gently
    o1x = 0.28 + 0.22 * math.sin(t * 0.37)
    o1y = 0.30 + 0.20 * math.cos(t * 0.29)
    d1 = (grid_x - o1x) ** 2 + (grid_y - o1y) ** 2
    g1 = np.exp(-d1 * (4.2 - 0.8 * energy)) * (0.28 + 0.16 * energy)

    # Orb 2 drifting counter-phase
    o2x = 0.72 + 0.20 * math.cos(t * 0.31)
    o2y = 0.72 + 0.22 * math.sin(t * 0.23)
    d2 = (grid_x - o2x) ** 2 + (grid_y - o2y) ** 2
    g2 = np.exp(-d2 * (4.0 - 0.7 * energy)) * (0.24 + 0.14 * energy)

    # Subtle center audio-reactive glow behind lyrics
    dc = (grid_x - 0.5) ** 2 + (grid_y - 0.5) ** 2
    gc = np.exp(-dc * 6.0) * (0.06 + 0.14 * energy)

    frame = frame + g1[..., None] * orb1 + g2[..., None] * orb2 + gc[..., None] * orb1
    arr = np.clip(frame, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="RGB").resize((size, size), Image.Resampling.BILINEAR)


def _build_scrim_overlay(size: int, lyric_position: str, show_neighbor_lines: bool = False) -> Image.Image:
    """Build a localized dark gradient scrim behind the lyric region so artwork stays bright."""
    ys = np.linspace(0.0, 1.0, size, dtype=np.float32)
    if lyric_position == "bottom":
        start = 0.56 if show_neighbor_lines else 0.70
        alpha_1d = np.clip((ys - start) / (1.0 - start), 0.0, 1.0) ** 1.45 * 215.0
    elif lyric_position == "top":
        end = 0.44 if show_neighbor_lines else 0.30
        alpha_1d = np.clip((end - ys) / end, 0.0, 1.0) ** 1.45 * 215.0
    else:
        spread = 0.065 if show_neighbor_lines else 0.030
        alpha_1d = np.exp(-((ys - 0.50) ** 2) / spread) * 165.0

    alpha_2d = np.repeat(alpha_1d[:, None], size, axis=1).astype(np.uint8)
    rgba = np.zeros((size, size, 4), dtype=np.uint8)
    rgba[..., 0] = 6
    rgba[..., 1] = 8
    rgba[..., 2] = 16
    rgba[..., 3] = alpha_2d
    return Image.fromarray(rgba, mode="RGBA")


def _make_cover_bg(
    cover_img: Image.Image,
    t: float,
    duration: float,
    energy: float,
    accent_rgb: tuple[int, int, int],
    vignette_mask: Image.Image,
    scrim_overlay: Image.Image,
    bg_dim: float,
    size: int,
) -> Image.Image:
    """Apply gentle centered Ken Burns zoom + subtle beat pulse + localized lyric scrim."""
    # Gentle ping-pong zoom (1.00 -> 1.07) + tiny 1.5% beat breathing so edge faces stay framed
    cycle = 0.5 - 0.5 * math.cos(t * (2.0 * math.pi / max(duration, 18.0)))
    zoom = 1.0 + 0.07 * cycle + 0.015 * energy
    cw, ch = cover_img.size
    crop_size = min(cw, int(round(cw / zoom)))
    max_shift = max(0, cw - crop_size)
    # Very gentle centered drift (keeps edge subjects framed)
    px = 0.5 + 0.14 * math.sin(t * 0.17)
    py = 0.5 + 0.14 * math.cos(t * 0.13)
    left = int(round(max_shift * px))
    top = int(round(max_shift * py))
    cropped = cover_img.crop((left, top, left + crop_size, top + crop_size))
    bg = cropped.resize((size, size), Image.Resampling.BILINEAR).convert("RGBA")

    # Adjustable uniform dimming (keep low for bright artwork)
    dim_clamped = max(0.0, min(0.85, float(bg_dim)))
    if dim_clamped > 0.01:
        dark_alpha = int(round(dim_clamped * 255))
        dark_overlay = Image.new("RGBA", (size, size), (8, 10, 18, dark_alpha))
        bg = Image.alpha_composite(bg, dark_overlay)

    # Localized gradient scrim behind the lyric zone
    bg = Image.alpha_composite(bg, scrim_overlay)
    return bg.convert("RGB")


def _wrap_words_into_rows(
    words: list[dict],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    space_w: int,
) -> list[list[tuple[dict, int]]]:
    """Wrap a line's words into visual rows that fit within max_width."""
    rows: list[list[tuple[dict, int]]] = []
    current_row: list[tuple[dict, int]] = []
    current_w = 0

    for w in words:
        bbox = font.getbbox(w["text"])
        word_w = max(1, int(bbox[2] - bbox[0]))
        needed = word_w if not current_row else current_w + space_w + word_w
        if current_row and needed > max_width:
            rows.append(current_row)
            current_row = [(w, word_w)]
            current_w = word_w
        else:
            current_row.append((w, word_w))
            current_w = needed

    if current_row:
        rows.append(current_row)
    return rows


def _find_active_line_index(lines: list[dict], t: float) -> int:
    """Find the active lyric line index at time t."""
    if not lines:
        return -1
    for idx, line in enumerate(lines):
        if line["start"] <= t <= line["end"]:
            return idx
    # Between lines: if next line is within 0.45s, switch early for smooth reading;
    # otherwise keep the most recent line visible until next begins.
    for idx, line in enumerate(lines):
        if t < line["start"]:
            if idx == 0:
                return 0 if (line["start"] - t) <= 1.2 else -1
            prev_line = lines[idx - 1]
            if (line["start"] - t) <= 0.45:
                return idx
            if (t - prev_line["end"]) <= 2.5:
                return idx - 1
            return idx
    return len(lines) - 1


def _resolve_outline(text_outline: str | bool) -> tuple[int, tuple[int, int, int]]:
    """Return (enabled_flag, rgb) for 'dark', 'white', or 'none' (with bool fallback)."""
    if text_outline is False or text_outline == "none":
        return 0, (0, 0, 0)
    if text_outline == "white":
        return 1, (255, 255, 255)
    return 1, (0, 0, 0)


def _draw_plain_line(
    canvas: Image.Image,
    text: str,
    y_center: int,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    color: tuple[int, int, int, int],
    max_width: int,
    text_outline: str | bool = "dark",
) -> None:
    """Draw a dimmed previous/next lyric line centered vertically at y_center."""
    words = [{"text": w} for w in text.split()]
    space_w = max(8, int(font.getlength(" ")))
    rows = _wrap_words_into_rows(words, font, max_width, space_w)
    line_h = int(font.size * 1.26) if hasattr(font, "size") else 44
    total_h = len(rows) * line_h
    y = y_center - total_h // 2

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    has_outline, outline_rgb = _resolve_outline(text_outline)
    stroke_w = 2 if has_outline else 0
    stroke_col = (*outline_rgb, min(195, int(color[3] * 1.4)))

    for row in rows:
        row_text = " ".join(item[0]["text"] for item in row)
        bbox = draw.textbbox((0, 0), row_text, font=font)
        tw = bbox[2] - bbox[0]
        x = (canvas.width - tw) // 2
        draw.text((x, y + 2), row_text, font=font, fill=(0, 0, 0, min(155, color[3])))
        draw.text(
            (x, y),
            row_text,
            font=font,
            fill=color,
            stroke_width=stroke_w,
            stroke_fill=stroke_col,
        )
        y += line_h

    canvas.alpha_composite(overlay)


def _draw_karaoke_active_line(
    canvas: Image.Image,
    line: dict,
    t: float,
    y_center: int,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    accent_rgb: tuple[int, int, int],
    max_width: int,
    text_outline: str | bool = "dark",
) -> None:
    """Draw the active lyric line with smooth word-by-word karaoke highlight sweep."""
    space_w = max(12, int(font.getlength(" ")))
    rows = _wrap_words_into_rows(line["words"], font, max_width, space_w)
    font_sz = font.size if hasattr(font, "size") else 60
    line_h = int(font_sz * 1.30)
    total_h = len(rows) * line_h
    y = y_center - total_h // 2

    base_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    base_draw = ImageDraw.Draw(base_layer)
    glow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)

    has_outline, outline_rgb = _resolve_outline(text_outline)
    unsung_color = (255, 255, 255, 245 if has_outline else 220)
    sung_color = (*accent_rgb, 255)
    shadow_color = (0, 0, 0, 195)
    stroke_w = 4 if has_outline else 0
    stroke_col = (*outline_rgb, 235)

    for row in rows:
        row_w = sum(w for _, w in row) + space_w * max(0, len(row) - 1)
        x = (canvas.width - row_w) // 2

        for word, word_w in row:
            txt = word["text"]
            ws = float(word["start"])
            we = float(word["end"])

            # Shadow + unsung base with optional crisp dark outline
            base_draw.text((x, y + 3), txt, font=font, fill=shadow_color)
            base_draw.text(
                (x, y),
                txt,
                font=font,
                fill=unsung_color,
                stroke_width=stroke_w,
                stroke_fill=stroke_col,
            )

            if t >= we:
                # Fully sung word
                base_draw.text(
                    (x, y),
                    txt,
                    font=font,
                    fill=sung_color,
                    stroke_width=stroke_w,
                    stroke_fill=stroke_col,
                )
            elif t > ws:
                # Currently sung word: smooth left-to-right karaoke fill + subtle glow
                progress = max(0.0, min(1.0, (t - ws) / max(0.04, we - ws)))
                glow_draw.text((x, y), txt, font=font, fill=(*accent_rgb, 150))

                pad = 14
                strip_w = word_w + pad * 2
                strip_h = line_h + pad * 2
                strip = Image.new("RGBA", (strip_w, strip_h), (0, 0, 0, 0))
                s_draw = ImageDraw.Draw(strip)
                s_draw.text(
                    (pad, pad),
                    txt,
                    font=font,
                    fill=sung_color,
                    stroke_width=stroke_w,
                    stroke_fill=stroke_col,
                )
                clip_w = max(1, int(round(pad + word_w * progress)))
                cropped = strip.crop((0, 0, min(strip_w, clip_w), strip_h))
                base_layer.alpha_composite(cropped, (x - pad, y - pad))

            x += word_w + space_w
        y += line_h

    glow_blurred = glow_layer.filter(ImageFilter.GaussianBlur(radius=10))
    canvas.alpha_composite(glow_blurred)
    canvas.alpha_composite(base_layer)


def render_karaoke_video(
    audio_path: Path,
    timings: dict,
    output_path: Path,
    *,
    theme_name: str = "midnight",
    accent_color: str | None = None,
    title: str = "",
    artist: str = "",
    cover_image_path: Path | None = None,
    use_cover_image: bool = False,
    time_offset: float = 0.0,
    lyric_position: str = "center",
    bg_dim: float = 0.18,
    text_outline: str | bool = "dark",
    show_neighbor_lines: bool = False,
    on_progress: Callable[[str, float], None] | None = None,
) -> Path:
    """Render a 1080x1080 karaoke MP4 video optimized for X."""
    duration = float(timings["duration"])
    total_frames = max(1, int(math.ceil(duration * FPS)))
    lines = timings.get("lines", [])
    pos = lyric_position if lyric_position in ("top", "center", "bottom") else "center"

    theme = THEMES.get(theme_name, THEMES["midnight"])
    accent_rgb = _hex_to_rgb(accent_color or str(theme["accent"]))

    if on_progress:
        on_progress("Analyzing audio energy for subtle background pulse...", 0.05)

    energies = extract_audio_envelope(audio_path, FPS, total_frames)

    # Precompute low-res grid for fast gradient generation (180x180 -> bilinear 1080x1080)
    grid_res = 180
    xs = np.linspace(0.0, 1.0, grid_res, dtype=np.float32)
    ys = np.linspace(0.0, 1.0, grid_res, dtype=np.float32)
    grid_x, grid_y = np.meshgrid(xs, ys)

    # Optional Ken Burns cover image + localized scrim
    cover_img: Image.Image | None = None
    vignette_mask: Image.Image | None = None
    scrim_overlay: Image.Image | None = None
    if use_cover_image and cover_image_path and cover_image_path.exists():
        cover_img = _prepare_cover_image(cover_image_path, VIDEO_SIZE)
        vx = np.linspace(-1.0, 1.0, VIDEO_SIZE, dtype=np.float32)
        vy = np.linspace(-1.0, 1.0, VIDEO_SIZE, dtype=np.float32)
        mgx, mgy = np.meshgrid(vx, vy)
        radial = np.exp(-((mgx * mgx + mgy * mgy) * 1.8)) * 255.0
        vignette_mask = Image.fromarray(np.clip(radial, 0, 255).astype(np.uint8), mode="L")
        scrim_overlay = _build_scrim_overlay(VIDEO_SIZE, pos, show_neighbor_lines)

    # Fonts & layout coordinates by lyric position
    if pos == "center":
        active_font = _load_font(62, bold=True)
        neighbor_font = _load_font(38, bold=False)
        y_prev, y_active, y_next = 340, 540, 740
    elif pos == "bottom":
        active_font = _load_font(58 if not show_neighbor_lines else 54, bold=True)
        neighbor_font = _load_font(32, bold=False)
        y_prev, y_active, y_next = (745, 845, 940) if show_neighbor_lines else (745, 900, 940)
    else:  # top
        active_font = _load_font(58 if not show_neighbor_lines else 54, bold=True)
        neighbor_font = _load_font(32, bold=False)
        y_prev, y_active, y_next = (140, 235, 330) if show_neighbor_lines else (140, 165, 330)

    title_font = _load_font(44, bold=True)
    artist_font = _load_font(30, bold=False)

    # Start FFmpeg encoding process
    cmd = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-s",
        f"{VIDEO_SIZE}x{VIDEO_SIZE}",
        "-pix_fmt",
        "rgb24",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        "-shortest",
        str(output_path),
    ]

    if on_progress:
        on_progress("Rendering karaoke video frames...", 0.10)

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin is not None

    max_text_w = VIDEO_SIZE - 140
    header_title = title.strip()
    header_artist = artist.strip()

    try:
        for frame_idx in range(total_frames):
            t = frame_idx / FPS
            lyric_t = t - time_offset
            energy = float(energies[frame_idx])

            if cover_img is not None and vignette_mask is not None and scrim_overlay is not None:
                bg = _make_cover_bg(
                    cover_img,
                    t,
                    duration,
                    energy,
                    accent_rgb,
                    vignette_mask,
                    scrim_overlay,
                    bg_dim,
                    VIDEO_SIZE,
                )
            else:
                bg = _make_gradient_bg(t, energy, theme, grid_x, grid_y, VIDEO_SIZE)

            canvas = bg.convert("RGBA")

            # Optional header (placed opposite the lyrics when lyrics are at top; subtle dark shadow only)
            has_outline, _ = _resolve_outline(text_outline)
            if header_title or header_artist:
                hdr_layer = Image.new("RGBA", (VIDEO_SIZE, VIDEO_SIZE), (0, 0, 0, 0))
                hdr_draw = ImageDraw.Draw(hdr_layer)
                hdr_y = 896 if pos == "top" else 42
                if header_title:
                    tb = hdr_draw.textbbox((0, 0), header_title, font=title_font)
                    tx = (VIDEO_SIZE - (tb[2] - tb[0])) // 2
                    hdr_draw.text((tx, hdr_y + 3), header_title, font=title_font, fill=(0, 0, 0, 190))
                    hdr_draw.text((tx, hdr_y), header_title, font=title_font, fill=(255, 255, 255, 250))
                if header_artist:
                    ab = hdr_draw.textbbox((0, 0), header_artist, font=artist_font)
                    ax = (VIDEO_SIZE - (ab[2] - ab[0])) // 2
                    hdr_draw.text((ax, hdr_y + 57), header_artist, font=artist_font, fill=(0, 0, 0, 175))
                    hdr_draw.text((ax, hdr_y + 54), header_artist, font=artist_font, fill=(255, 255, 255, 225))
                canvas.alpha_composite(hdr_layer)

            # Karaoke lyrics (single active line by default, or optional 3-line window)
            active_idx = _find_active_line_index(lines, lyric_t)
            if active_idx >= 0:
                if show_neighbor_lines and active_idx > 0:
                    _draw_plain_line(
                        canvas,
                        lines[active_idx - 1]["text"],
                        y_center=y_prev,
                        font=neighbor_font,
                        color=(255, 255, 255, 115 if has_outline else 82),
                        max_width=max_text_w,
                        text_outline=text_outline,
                    )

                _draw_karaoke_active_line(
                    canvas,
                    lines[active_idx],
                    lyric_t,
                    y_center=y_active,
                    font=active_font,
                    accent_rgb=accent_rgb,
                    max_width=max_text_w,
                    text_outline=text_outline,
                )

                if show_neighbor_lines and active_idx + 1 < len(lines):
                    _draw_plain_line(
                        canvas,
                        lines[active_idx + 1]["text"],
                        y_center=y_next,
                        font=neighbor_font,
                        color=(255, 255, 255, 145 if has_outline else 110),
                        max_width=max_text_w,
                        text_outline=text_outline,
                    )

            # Bottom progress bar
            bar_layer = Image.new("RGBA", (VIDEO_SIZE, VIDEO_SIZE), (0, 0, 0, 0))
            bar_draw = ImageDraw.Draw(bar_layer)
            bar_x0, bar_x1 = 96, VIDEO_SIZE - 96
            bar_y = VIDEO_SIZE - 64
            bar_draw.rounded_rectangle(
                [bar_x0, bar_y, bar_x1, bar_y + 6],
                radius=3,
                fill=(255, 255, 255, 48),
            )
            prog = max(0.0, min(1.0, t / max(duration, 0.01)))
            fill_x1 = bar_x0 + int(round((bar_x1 - bar_x0) * prog))
            if fill_x1 > bar_x0 + 3:
                bar_draw.rounded_rectangle(
                    [bar_x0, bar_y, fill_x1, bar_y + 6],
                    radius=3,
                    fill=(*accent_rgb, 235),
                )
            canvas.alpha_composite(bar_layer)

            try:
                proc.stdin.write(canvas.convert("RGB").tobytes())
            except BrokenPipeError:
                # FFmpeg closed stdin early (e.g. -shortest reached end of audio stream)
                break

            if on_progress and (frame_idx % 15 == 0 or frame_idx == total_frames - 1):
                pct = 0.10 + 0.88 * ((frame_idx + 1) / total_frames)
                on_progress(
                    f"Rendering frame {frame_idx + 1} / {total_frames}...",
                    pct,
                )

        proc.stdin.close()
        stderr = proc.stderr.read().decode("utf-8", errors="ignore") if proc.stderr else ""
        ret = proc.wait()
        if ret != 0:
            raise RuntimeError(f"FFmpeg render failed (exit {ret}): {stderr[-800:]}")
    finally:
        if proc.poll() is None:
            proc.kill()

    if on_progress:
        on_progress("Video ready for X!", 1.0)
    return output_path
