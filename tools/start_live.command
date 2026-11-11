#!/bin/bash
set -euo pipefail
studio_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$studio_root"
if [[ ! -x .venv/bin/python ]]; then
  echo '缺少 .venv，请先按 README 安装项目依赖。'
  exit 1
fi
printf '%s\n' '大肥鱼直播后端：127.0.0.1:8766，启动后默认暂停。' \
  '控制台：http://127.0.0.1:8766/control' \
  'OBS 配置与场景集合：BigWhaleLive；采集尺寸：1080×1920。' \
  '沿用 .env 中的模型、固定声线与弹幕设置；本机配置为9748572游客读取。' \
  '本工具不点击OBS推流；请在OBS确认直播配置，在控制台开始主播。' \
  '不要同时启动本地测试服务占用8766；关闭终端或Ctrl+C停止本后端。'
exec .venv/bin/python tools/obs_local.py serve --port 8766 --with-danmaku
