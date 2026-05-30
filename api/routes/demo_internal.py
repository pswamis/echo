"""Internal demo routes — requires X-Demo-Secret header.

Called only by voiceflow-demo-api. Never reachable from the
public internet (Cloudflare Tunnel only routes /ws/demo/* here).
"""
import secrets
from datetime import UTC, datetime

import redis.asyncio as aioredis
from fastapi import APIRouter, Header, HTTPException
from loguru import logger
from pydantic import BaseModel

from api.constants import (
    BACKEND_API_ENDPOINT,
    DEMO_ORG_ID,
    DEMO_SECRET,
    DEMO_USER_ID,
    DEMO_WS_PUBLIC_URL,
    REDIS_URL,
)
from api.db import db_client
from api.db.models import WorkflowModel
from api.enums import WorkflowRunMode
from api.routes.turn_credentials import generate_turn_credentials

SESSION_TTL_SECONDS = 15 * 60  # 15 min

router = APIRouter(prefix="/internal/demo", tags=["demo-internal"])

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def _check_secret(x_demo_secret: str):
    if DEMO_SECRET is None:
        raise HTTPException(status_code=503, detail="Demo not configured")
    if not secrets.compare_digest(x_demo_secret, DEMO_SECRET):
        raise HTTPException(status_code=403, detail="Forbidden")


class CreateDemoRequest(BaseModel):
    session_token: str
    system_prompt: str
    agent_name: str


class CreateDemoResponse(BaseModel):
    ws_url: str
    workflow_run_id: int
    turn_credentials: dict | None = None


@router.post("/create", response_model=CreateDemoResponse)
async def create_demo_session(
    body: CreateDemoRequest,
    x_demo_secret: str = Header(...),
):
    _check_secret(x_demo_secret)

    if not DEMO_ORG_ID or not DEMO_USER_ID:
        raise HTTPException(status_code=503, detail="Demo org not configured")

    workflow_def = {
        "nodes": [
            {
                "id": "start",
                "type": "startCall",
                "position": {"x": 0, "y": 0},
                "data": {
                    "name": "Start",
                    "prompt": body.system_prompt,
                    "is_start": True,
                    "allow_interrupt": True,
                    "add_global_prompt": False,
                },
            },
            {
                "id": "end",
                "type": "endCall",
                "position": {"x": 0, "y": 200},
                "data": {
                    "name": "End",
                    "prompt": "Wrap up the conversation politely.",
                    "is_end": True,
                    "allow_interrupt": False,
                    "add_global_prompt": False,
                },
            },
        ],
        "edges": [
            {
                "id": "start-end",
                "source": "start",
                "target": "end",
                "data": {"label": "End Call", "condition": "When the user is done."},
            }
        ],
    }

    workflow = await db_client.create_workflow(
        name=f"demo-{body.session_token[:8]}",
        workflow_definition=workflow_def,
        user_id=DEMO_USER_ID,
        organization_id=DEMO_ORG_ID,
    )

    # Mark as demo for pruner — reuse the existing connection pool
    async with db_client.async_session() as session:
        wf = await session.get(WorkflowModel, workflow.id)
        if wf:
            wf.is_demo = True
            await session.commit()
        else:
            logger.warning(f"Demo workflow {workflow.id} not found for is_demo update")

    run = await db_client.create_workflow_run(
        name=f"demo-run-{body.session_token[:8]}",
        workflow_id=workflow.id,
        mode=WorkflowRunMode.SMALLWEBRTC.value,
        user_id=DEMO_USER_ID,
        organization_id=DEMO_ORG_ID,
    )

    redis = await get_redis()
    session_data = {
        "workflow_id": str(workflow.id),
        "workflow_run_id": str(run.id),
        "agent_name": body.agent_name,
        "system_prompt": body.system_prompt,
        "slot_claimed": "false",
        "created_at": str(int(datetime.now(UTC).timestamp())),
    }
    await redis.hset(f"demo:session:{body.session_token}", mapping=session_data)
    await redis.expire(f"demo:session:{body.session_token}", SESSION_TTL_SECONDS)

    turn_creds = None
    try:
        turn_creds = generate_turn_credentials("demo")
    except Exception:
        pass

    ws_base = (DEMO_WS_PUBLIC_URL or BACKEND_API_ENDPOINT).replace(
        "https://", "wss://"
    ).replace("http://", "ws://")
    ws_url = f"{ws_base.rstrip('/')}/api/v1/ws/demo/{body.session_token}"
    return CreateDemoResponse(
        ws_url=ws_url,
        workflow_run_id=run.id,
        turn_credentials=turn_creds,
    )


@router.delete("/{token}")
async def delete_demo_session(
    token: str,
    x_demo_secret: str = Header(...),
):
    _check_secret(x_demo_secret)

    redis = await get_redis()
    deleted = await redis.delete(f"demo:session:{token}")
    if deleted:
        await redis.decr("demo:slots:active")
    logger.info(f"Demo session {token[:8]}... deleted by demo-api request")
    return {"ok": True}
