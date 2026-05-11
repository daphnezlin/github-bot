import hashlib
import hmac
import json
import os
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from agent.reviewer import run_review_agent

load_dotenv()

app = FastAPI(title="github-bot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

active_connections: dict[int, WebSocket] = {}


def verify_github_signature(payload: bytes, signature: str) -> bool:
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "").encode()
    expected = "sha256=" + hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


import asyncio

@app.post("/webhook")
async def github_webhook(request: Request):
    payload_bytes = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not verify_github_signature(payload_bytes, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    event_type = request.headers.get("X-GitHub-Event", "")
    payload = json.loads(payload_bytes)
    action = payload.get("action", "")

    if event_type != "pull_request":
        return {"status": "ignored"}
    if action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored"}

    pr = payload["pull_request"]
    repo_full_name = payload["repository"]["full_name"]
    pr_number = pr["number"]
    pr_title = pr["title"]
    pr_body = pr.get("body", "") or ""

    ws = active_connections.get(pr_number)

    # run agent in background so webhook returns immediately
    asyncio.create_task(run_review_agent(
        repo_full_name=repo_full_name,
        pr_number=pr_number,
        pr_title=pr_title,
        pr_body=pr_body,
        websocket=ws,
    ))

    return {"status": "review started", "pr": pr_number}


@app.websocket("/ws/{pr_number}")
async def websocket_endpoint(websocket: WebSocket, pr_number: int):
    await websocket.accept()
    active_connections[pr_number] = websocket
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.pop(pr_number, None)


@app.get("/health")
async def health():
    return {"status": "ok"}
