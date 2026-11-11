"""Safe readiness check; --listen verifies reception without invoking AI/TTS."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bilibili_adapter import BilibiliOpenLive
from bilibili_web import BilibiliWeb
from config import ConfigurationError, Limits, load_settings, secret_value


async def listen(settings, seconds):
    stopped = asyncio.Event()
    received = 0
    seen = set()
    adapter = None

    async def message(event):
        nonlocal received
        if event.event_id in seen:
            return 200, {"duplicate": True}
        if received >= 3:
            return 202, {"duplicate": False}
        seen.add(event.event_id)
        received += 1
        print(json.dumps({"received": received, "text_length": len(event.text)}, ensure_ascii=False), flush=True)
        if received >= 3:
            stopped.set()
        return 202, {"duplicate": False}

    async def status():
        print(json.dumps({"status": adapter.status, "room_id": adapter.room_id,
                          "reason": adapter.reason, "error_code": adapter.error_code}, ensure_ascii=False), flush=True)
        if adapter.status == "error":
            stopped.set()

    adapter = (BilibiliWeb if settings.bili_mode == "web" else BilibiliOpenLive)(settings, Limits(), message, status)
    try:
        adapter.start()
        try:
            await asyncio.wait_for(stopped.wait(), seconds)
        except TimeoutError:
            pass
    finally:
        await adapter.aclose()
    print(json.dumps({"received": received, "diagnostics": adapter.diagnostics()}, ensure_ascii=False))
    return 0 if received >= 3 and adapter.status == "connected" and adapter.counters["end_failures"] == 0 else 1


def main():
    parser = argparse.ArgumentParser(description="检查 B站开放平台配置；默认不发起网络请求。")
    parser.add_argument("--listen", action="store_true", help="真实连接并统计弹幕，不调用 LLM 或语音")
    parser.add_argument("--seconds", type=int, default=60, help="接收验证时间，5–300 秒")
    args = parser.parse_args()
    if not 5 <= args.seconds <= 300:
        parser.error("--seconds 须在 5–300 范围内")
    try:
        settings = load_settings()
    except ConfigurationError as error:
        print(str(error))
        return 2
    names = ("bili_app_id", "bili_access_key", "bili_access_secret", "bili_auth_code")
    missing = [name.upper() for name in names if not secret_value(getattr(settings, name))] if settings.bili_mode == "open_live" else []
    print(json.dumps({"mode": settings.bili_mode, "room_id": settings.bili_room_id if settings.bili_mode == "web" else None,
                      "missing_keys": missing}, ensure_ascii=False))
    if missing:
        print("请按 docs/bilibili-setup.md 申请应用并将配置填写到本地 .env；不要将密钥发到聊天。")
        return 2
    if not args.listen:
        print("配置项已填写；尚未验证平台授权或实际连接。")
        return 0
    if settings.bili_mode == "off":
        print("真实接收需要先设置 BILI_MODE=web 或 open_live。")
        return 2
    return asyncio.run(listen(settings, args.seconds))


if __name__ == "__main__":
    raise SystemExit(main())
