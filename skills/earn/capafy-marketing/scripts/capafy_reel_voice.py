#!/usr/bin/env python3
"""Give a rendered Hook Lab reel a voice, a music bed and a visible first frame.

The 2026-10-11 X batch (capafy-videos/hooklab-*) shipped silent and its first frame was
black, so X showed an empty dark box. This keeps the approved render and fixes both at $0:
narration from the reel's own on-screen copy via edge-tts (macOS say fallback), a quiet synthesized music bed,
and the hook frame held for the first 0.6 s. Output: <slug>/renders-v2/video.mp4 + manifest.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import subprocess
import sys
from pathlib import Path

BASE = Path.home() / ".local/state/life-manager/marketing/capafy-videos"
VOICE = "en-US-AndrewMultilingualNeural"
FALLBACK_VOICE = "Samantha"  # macOS say: edge-tts 403s intermittently and lost both 2026-10-23 reels
# Opener copied from the top creator shorts (creative/winner-patterns.md): confession, pain, "The solution?".
CONFESSION = "I have a confession. I used to spend an hour on the first line of every video."
HOOK_FRAME_AT = 2.2  # seconds into the render where the hook line is fully visible
PROPER = {"Instagram", "TikTok", "YouTube", "Reels", "Shorts", "X"}
LEAD = 5.0           # seconds the hook frame (with confession top text) is held while the confession is spoken


def _lines(path: Path) -> list[str]:
    t = re.sub(r"<style.*?</style>|<script.*?</script>", "", path.read_text(), flags=re.S)
    return [x.strip() for x in html.unescape(re.sub(r"<[^>]+>", "\n", t)).split("\n") if x.strip()]


def narration(hook: list[str], cards: list[str], cta: list[str]) -> str:
    """Spoken script from the reel's own copy: hook, the three quoted lines, the on-screen CTA."""
    product = cta[0].removeprefix("Search ").strip()
    tagline = cta[2].strip() if len(cta) > 2 else ""
    title = cards[0]
    topic = title.split(":")[0].strip()
    quotes = [c.strip("“”\"") for c in cards if c.startswith("“")][:3]
    if len(hook) < 2 or len(quotes) != 3 or not product:
        raise ValueError(f"unexpected reel copy: hook={hook} quotes={quotes} cta={cta}")
    what = "three hooks" if "hook" in title.split(":")[-1].lower() else "the script"
    verb = "are" if what == "three hooks" else "is"
    first = topic.split()[0]
    topic = topic if first in PROPER else topic[0].lower() + topic[1:]
    article = "an" if topic[0].lower() in "aeiou" else "a"
    parts = [CONFESSION, hook[0], hook[1], f"The solution? {product}. Here {verb} {what} it wrote for {article} {topic}."]
    parts += [f"{n}. {q}" for n, q in zip(("One", "Two", "Three"), quotes)]
    parts.append(f"Search {product} on Capafy. {tagline}".strip())
    return " ".join(parts).replace(" 3 ", " three ").replace("first 3 seconds", "first three seconds")


def _run(*cmd: str) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def tts(text_file: Path, mp3: Path) -> str:
    """edge-tts first; on refusal fall back to the local macOS voice so the day's reel still ships."""
    try:
        _run("edge-tts", "--voice", VOICE, "--rate=+6%", "--file", str(text_file), "--write-media", str(mp3))
        return VOICE
    except subprocess.CalledProcessError:
        aiff = mp3.with_suffix(".aiff")
        _run("say", "-v", FALLBACK_VOICE, "-r", "190", "-f", str(text_file), "-o", str(aiff))
        _run("ffmpeg", "-v", "error", "-y", "-i", str(aiff), str(mp3))
        return FALLBACK_VOICE


def confession_frame(src: Path, dst: Path) -> None:
    """Bold top text over the hook frame, the format every winner short opens with."""
    from PIL import Image, ImageDraw, ImageFont  # noqa: PLC0415
    img = Image.open(src).convert("RGB")
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 104)
    for i, row in enumerate(("I HAVE A", "CONFESSION")):
        d.text((img.width // 2, 330 + i * 125), row, font=font, fill=(255, 255, 255), anchor="mm",
               stroke_width=6, stroke_fill=(0, 0, 0))
    img.save(dst)


def _dur(path: Path) -> float:
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", str(path)], text=True).strip())


def build(slug: str) -> dict:
    d = BASE / slug
    src, out = d / "renders/video.mp4", d / "renders-v2"
    out.mkdir(exist_ok=True)
    text = narration(_lines(d / "compositions/hook.html"), _lines(d / "compositions/cards.html"),
                     _lines(d / "compositions/cta.html"))
    (out / "narration.txt").write_text(text + "\n")
    voice = tts(out / "narration.txt", out / "voice.mp3")
    total = max(_dur(src) + LEAD, _dur(out / "voice.mp3") + 0.2 + 0.8)
    _run("ffmpeg", "-v", "error", "-y",
         "-f", "lavfi", "-i", f"sine=f=220:d={total}", "-f", "lavfi", "-i", f"sine=f=277.18:d={total}",
         "-f", "lavfi", "-i", f"sine=f=329.63:d={total}", "-f", "lavfi", "-i", f"anoisesrc=c=pink:d={total}:a=0.05",
         "-filter_complex",
         "[0][1][2]amix=inputs=3,tremolo=f=0.15:d=0.4,lowpass=f=900[pad];[3]lowpass=f=500[n];"
         f"[pad][n]amix=inputs=2:weights=1 0.5,volume=-4dB,afade=t=in:d=2,afade=t=out:st={total - 2.5}:d=2.5[bgm]",
         "-map", "[bgm]", "-ar", "44100", str(out / "bgm.m4a"))
    _run("ffmpeg", "-v", "error", "-y", "-ss", str(HOOK_FRAME_AT), "-i", str(src), "-frames:v", "1", str(out / "hookframe.png"))
    confession_frame(out / "hookframe.png", out / "openframe.png")
    lead_ms = 200  # the confession is spoken over the held open frame
    _run("ffmpeg", "-v", "error", "-y", "-loop", "1", "-t", str(LEAD), "-framerate", "30", "-i", str(out / "openframe.png"),
         "-i", str(src), "-i", str(out / "voice.mp3"), "-i", str(out / "bgm.m4a"),
         "-filter_complex",
         "[0:v]scale=1080:1920,fps=30,setsar=1,format=yuv420p[a];[1:v]fps=30,setsar=1,format=yuv420p[b];"
         f"[a][b]concat=n=2:v=1:a=0,tpad=stop_mode=clone:stop_duration={total}[v];"
         f"[2:a]adelay={lead_ms}|{lead_ms}[vo];[vo][3:a]amix=inputs=2:duration=longest:normalize=0[aout]",
         "-map", "[v]", "-map", "[aout]", "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out / "video.mp4"))
    manifest = {"slug": slug, "source": str(src), "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
                "voice": voice, "narration": text, "duration_s": round(_dur(out / "video.mp4"), 2),
                "output": str(out / "video.mp4"), "output_sha256": hashlib.sha256((out / "video.mp4").read_bytes()).hexdigest()}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    for s in sys.argv[1:]:
        print(json.dumps(build(s)))
