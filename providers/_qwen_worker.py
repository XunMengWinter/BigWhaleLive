"""Private line protocol worker; invoked using the optional voice environment."""
from __future__ import annotations

import base64
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    output = sys.stdout
    # MLX/Transformers sometimes print during loading; stdout is protocol only.
    with redirect_stdout(sys.stderr):
        import mlx.core as mx
        import numpy as np
        from mlx_audio.tts.utils import load_model

        model_path, profile_path = map(Path, sys.argv[1:])
        profile = json.loads((profile_path / "voice.json").read_text())
        reference = profile_path / "reference.wav"
        if hashlib.sha256(reference.read_bytes()).hexdigest() != profile["reference_sha256"]:
            raise ValueError("Invalid voice reference")
        model = load_model(str(model_path))
        if model.config.tts_model_type != "base":
            raise ValueError("Voice requires the Base model")

        for line in sys.stdin:
            try:
                text = json.loads(line)["text"]
                if not isinstance(text, str) or not text.strip() or len(text) > 120:
                    raise ValueError("Invalid text")
                mx.random.seed(profile["seed"])
                chunks, samples, sample_rate = [], 0, 24000
                for result in model.generate(
                    text=text, ref_audio=str(reference), ref_text=profile["reference_text"],
                    lang_code="Chinese", temperature=profile["temperature"], max_tokens=768,
                    verbose=False, stream=False,
                ):
                    chunk = np.asarray(result.audio, dtype=np.float32).reshape(-1)
                    sample_rate = result.sample_rate
                    samples += len(chunk)
                    if samples > sample_rate * 42 or not np.isfinite(chunk).all():
                        raise ValueError("Invalid audio")
                    chunks.append(chunk)
                if not chunks or samples == 0:
                    raise ValueError("Empty audio")
                audio = np.concatenate(chunks)
                encoded = subprocess.run(
                    ["ffmpeg", "-v", "error", "-f", "f32le", "-ar", str(sample_rate),
                     "-ac", "1", "-i", "pipe:0", "-f", "mp3", "-b:a", "64k", "pipe:1"],
                    input=audio.tobytes(), capture_output=True, check=True, timeout=10,
                ).stdout
                if not encoded or len(encoded) > 5 * 1024 * 1024:
                    raise ValueError("Invalid encoded audio")
                for offset in range(0, len(encoded), 32768):
                    output.write(json.dumps({"type": "audio", "data": base64.b64encode(encoded[offset:offset + 32768]).decode()}) + "\n")
                output.write('{"type":"done"}\n')
                output.flush()
            except Exception:
                # Never publish provider details or user text through the protocol.
                output.write('{"type":"error"}\n')
                output.flush()


if __name__ == "__main__":
    main()
