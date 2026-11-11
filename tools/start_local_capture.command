#!/bin/bash
set -euo pipefail
studio_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$studio_root"
if [[ ! -x .venv/bin/python ]]; then
  echo '缺少 .venv，请先按 README 安装项目依赖。'
  exit 1
fi
printf '%s\n' '大肥鱼本地采集：127.0.0.1:8766，初始暂停。' \
  '控制台：http://127.0.0.1:8766/control' \
  'OBS 配置与场景集合：BigWhaleLocal；采集尺寸：1080×1920。' \
  '默认只接受模拟输入；--with-danmaku 使用 .env 中的访客弹幕配置。' \
  '本工具不启动推流；关闭本终端或 Ctrl+C 停止服务。'
exec .venv/bin/python tools/obs_local.py serve --port 8766 "$@"
