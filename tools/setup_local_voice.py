"""Install the optional fixed voice environment and pinned local model."""
import json
import os
from pathlib import Path
import platform
import subprocess


def main():
    root = Path(__file__).resolve().parents[1]
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit("本地小鲸音色需要 Apple Silicon macOS 和 Metal。")
    profile = json.loads((root / "assets/voices/xiaojing-v1/voice.json").read_text())
    python = root / ".cache/voice-env/bin/python"
    if not python.exists():
        subprocess.run(["uv", "--cache-dir", str(root / ".cache/uv"), "venv", "--python", "3.11", str(python.parents[1])], check=True)
    subprocess.run(["uv", "--cache-dir", str(root / ".cache/uv"), "pip", "sync", "--python", str(python), str(root / "requirements-voice.txt")], check=True)
    environment = dict(os.environ, HF_HOME=str(root / ".cache/huggingface"))
    # Structured data travels on stdin; no shell interpolation of paths or values.
    code = """import json,sys
from pathlib import Path
from huggingface_hub import snapshot_download
p=json.load(sys.stdin)
snapshot=Path(snapshot_download(p['model_repo'],revision=p['model_revision']))
target=Path('.cache/models/xiaojing-base')
target.parent.mkdir(parents=True,exist_ok=True)
if target.is_symlink(): target.unlink()
if target.exists(): raise SystemExit('模型目标路径已存在，请检查 .cache/models/xiaojing-base')
target.symlink_to(snapshot, target_is_directory=True)
print('固定小鲸音色已安装')
"""
    subprocess.run([str(python), "-c", code], input=json.dumps(profile), text=True,
                   env=environment, cwd=root, check=True)


if __name__ == "__main__":
    main()
