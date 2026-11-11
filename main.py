"""BigWhaleLive: local HTTP and WebSocket application."""
from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from agent import Agent
from config import ROOT, Limits, load_settings, require_supported_modes
from contracts import ApiError, Control, Danmaku


def error_response(status, code, message):
    return JSONResponse(status_code=status, content={"error": {
        "code": code, "message": message, "request_id": str(uuid4())}})


class LocalBoundary:
    """Same-origin local service plus bounded JSON bodies, before body parsing."""
    def __init__(self, app, port=8765):
        self.app = app
        self.origins = {f"http://{host}:{port}" for host in ("127.0.0.1", "localhost")}
        self.hosts = {f"{host}:{port}" for host in ("127.0.0.1", "localhost")}
        if port == 8765:
            self.hosts.update({"127.0.0.1", "localhost"})

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        headers = {key.decode().lower(): value.decode() for key, value in scope.get("headers", [])}
        bad_host = headers.get("host") not in self.hosts
        bad_origin = headers.get("origin") not in self.origins if "origin" in headers else scope["type"] == "websocket"
        if bad_host or bad_origin:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                await error_response(403, "origin_not_allowed", "仅允许本机同源访问")(scope, receive, send)
            return
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path.startswith("/static/audio/") or any(part.startswith(".") for part in path.split("/") if part):
                return await error_response(404, "not_found", "资源不存在")(scope, receive, send)
            if scope["method"] == "POST":
                if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                    return await error_response(415, "json_required", "请使用 JSON 请求")(scope, receive, send)
                body = bytearray()
                while True:
                    chunk = await receive()
                    if chunk["type"] == "http.disconnect":
                        return
                    body.extend(chunk.get("body", b""))
                    if len(body) > 16384:
                        if scope.get("path") == "/api/danmaku":
                            await scope["app"].state.agent.reject_input()
                        return await error_response(413, "request_too_large", "请求体超过大小限制")(scope, receive, send)
                    if not chunk.get("more_body", False):
                        break
                delivered = False

                async def replay():
                    nonlocal delivered
                    if not delivered:
                        delivered = True
                        return {"type": "http.request", "body": bytes(body), "more_body": False}
                    return await receive()
                return await self.app(scope, replay, send)
        return await self.app(scope, receive, send)


def create_app(*, settings=None, root: Path = ROOT, limits=None, agent_factory=Agent, port=8765):
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Invalid local service port")
    limits = limits or Limits()

    @asynccontextmanager
    async def lifespan(application):
        configured = settings if settings is not None else load_settings()
        require_supported_modes(configured)
        agent = agent_factory(configured, root, limits=limits)
        application.state.agent = agent
        try:
            await agent.start()
            yield
        finally:
            await agent.stop()

    application = FastAPI(title="BigWhaleLive", version="0.2.0", lifespan=lifespan,
                          docs_url=None, redoc_url=None, openapi_url=None)
    application.add_middleware(LocalBoundary, port=port)

    @application.exception_handler(ApiError)
    async def api_error(request, exc):
        return error_response(exc.status, exc.code, exc.message)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        if request.url.path == "/api/danmaku":
            await request.app.state.agent.reject_input()
        return error_response(422, "invalid_request", "请求字段、格式或长度不符合要求")

    @application.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response(exc.status_code, "not_found" if exc.status_code == 404 else "request_failed", "资源不存在或请求不被支持")

    @application.get("/")
    async def stage():
        return FileResponse(root / "static/stage.html")

    @application.get("/control")
    async def control_page():
        return FileResponse(root / "static/control.html")

    @application.get("/api/health")
    async def health(request: Request):
        return {"status": "ok", "instance_id": request.app.state.agent.instance_id, "protocol_version": 1}

    @application.get("/api/state")
    async def state(request: Request):
        return request.app.state.agent.state()

    @application.post("/api/danmaku")
    async def danmaku(message: Danmaku, request: Request):
        status, body = await request.app.state.agent.accept(message)
        return JSONResponse(status_code=status, content=body)

    @application.post("/api/control")
    async def control(message: Control, request: Request):
        return await request.app.state.agent.control(message.action)

    @application.get("/audio/{utterance_id}.mp3")
    async def audio(utterance_id: str, request: Request):
        try:
            if str(UUID(utterance_id)) != utterance_id:
                raise ValueError
            agent = request.app.state.agent
            path = agent.audio.path(utterance_id)
            if path.is_symlink() or not path.is_file() or time.time() - path.stat().st_mtime > limits.audio_age:
                raise ValueError
        except ValueError:
            return error_response(404, "not_found", "音频不存在或已过期")
        return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})

    @application.websocket("/ws")
    async def socket(websocket: WebSocket):
        await websocket.accept()
        agent = websocket.app.state.agent
        client = await agent.connect()

        async def writer():
            close_code = 1000
            try:
                while not client.close_code:
                    try:
                        message = await asyncio.wait_for(client.queue.get(), 0.25)
                    except TimeoutError:
                        continue
                    await asyncio.wait_for(websocket.send_json(message), limits.send_timeout)
                close_code = client.close_code
            except asyncio.CancelledError:
                raise
            except Exception:
                close_code = 1013
                agent._mark_closed(client, close_code)
            finally:
                await agent.disconnect(client.identity)
                with suppress(Exception):
                    await asyncio.wait_for(websocket.close(code=client.close_code or close_code), limits.send_timeout)

        sender = asyncio.create_task(writer())
        try:
            while not client.close_code:
                event = await websocket.receive()
                if event["type"] == "websocket.disconnect":
                    break
                raw = event.get("text")
                data = event.get("bytes")
                if (len(raw.encode("utf-8")) if raw is not None else len(data or b"")) > limits.frame_bytes:
                    agent._mark_closed(client, 1009)
                    break
                try:
                    value = json.loads(raw) if raw is not None else None
                except (ValueError, TypeError):
                    value = None
                await agent.handle(client, value)
        except (RuntimeError, OSError):
            pass
        finally:
            await agent.disconnect(client.identity)
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)
            with suppress(Exception):
                await websocket.close(code=client.close_code or 1000)

    for name in ("static", "models", "vendor"):
        application.mount(f"/{name}", StaticFiles(directory=root / name, check_dir=False), name=name)
    return application


app = create_app()
