"""Build sharper, transparent playback copies without changing the upstream clips."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "static/assets/dsh-pet"
OUTPUT = SOURCE / "clear-v1"
# Sharpen luminance only at source resolution; leave chroma and alpha untouched.
# Lanczos reconstruction replaces the browser's large bilinear enlargement.
FILTER = "unsharp=3:3:0.6:3:3:0:3:3:0,scale=1920:1080:flags=lanczos"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe(path: Path) -> dict:
    data = subprocess.check_output([
        "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,nb_read_frames:format=duration",
        "-of", "json", str(path),
    ])
    return json.loads(data)


def main() -> None:
    upstream = json.loads((SOURCE / "manifest.json").read_text())
    originals = {entry["file"]: entry for entry in upstream["assets"]}
    OUTPUT.mkdir(exist_ok=True)
    records = []
    for name in ("idle", "speaking", "thinking"):
        source = SOURCE / f"{name}.webm"
        if sha256(source) != originals[source.name]["sha256"]:
            raise ValueError(f"Upstream checksum mismatch: {source.name}")
        target = OUTPUT / source.name
        temporary = OUTPUT / f".{name}.tmp.webm"
        command = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-threads", "2", "-c:v", "libvpx-vp9", "-i", str(source),
            "-an", "-filter_threads", "2", "-vf", FILTER,
            "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0",
            "-crf", "16", "-deadline", "good", "-cpu-used", "3",
            "-row-mt", "1", "-threads", "2", "-auto-alt-ref", "0",
            str(temporary),
        ]
        try:
            subprocess.run(command, check=True)
            before, after = probe(source), probe(temporary)
            a, b = before["streams"][0], after["streams"][0]
            assert (b["width"], b["height"]) == (1920, 1080)
            assert (a["nb_read_frames"], a["r_frame_rate"]) == (b["nb_read_frames"], b["r_frame_rate"])
            assert abs(float(before["format"]["duration"]) - float(after["format"]["duration"])) < .01
            alpha = subprocess.check_output([
                "ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-i", str(temporary),
                "-vf", "alphaextract", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-",
            ])
            assert min(alpha) == 0 and max(alpha) == 255, "Transparency was lost"
            temporary.replace(target)
            records.append({"file": target.name, "source": f"../{source.name}",
                            "source_sha256": sha256(source), "sha256": sha256(target),
                            "bytes": target.stat().st_size, **b,
                            "duration": after["format"]["duration"]})
            print(f"Verified {name}: {b['nb_read_frames']} frames, transparent 1920x1080", flush=True)
        finally:
            temporary.unlink(missing_ok=True)
    poster = OUTPUT / "poster.png"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-c:v", "libvpx-vp9", "-i", str(OUTPUT / "idle.webm"),
        "-frames:v", "1", "-pix_fmt", "rgba", str(poster),
    ], check=True)
    records.append({"file": poster.name, "derived_from": "idle.webm first frame",
                    "sha256": sha256(poster), "bytes": poster.stat().st_size})
    manifest = {"version": "clear-v1", "license": upstream["license"],
                "upstream_commit": upstream["commit"], "filter": FILTER,
                "encoder": "libvpx-vp9, yuva420p, CRF16, cpu-used3, 2 threads",
                "ffmpeg": subprocess.check_output(["ffmpeg", "-version"], text=True).splitlines()[0],
                "note": "Reconstruction and mild sharpening, not native HD or generative redrawing.",
                "assets": records}
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
