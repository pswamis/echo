"""Public WebSocket endpoint for demo voice sessions.

Token-protected: a valid token must have been issued by voiceflow-demo-api
via POST /internal/demo/create and stored in Redis. Single-use (slot_claimed
prevents replay). Runs the same SmallWebRTC pipeline as production calls.
"""
import asyncio

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from api.constants import DEMO_USER_ID, REDIS_URL
from api.db import db_client
from api.routes.webrtc_signaling import (
    ICE_INBOUND_POLICY,
    _keep_candidate,
    filter_outbound_sdp,
    get_ice_servers,
)
from api.services.pipecat.run_pipeline import run_pipeline_smallwebrtc
from api.services.pipecat.ws_sender_registry import (
    register_ws_sender,
    unregister_ws_sender,
)
from aiortc.sdp import candidate_from_sdp
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from starlette.websockets import WebSocketState

router = APIRouter(prefix="/ws", tags=["demo-ws"])

# Atomically claim a demo slot.  Checks slot_claimed, sets it, and increments
# the active counter in a single Redis round-trip — prevents TOCTOU races when
# two WebSocket connections arrive with the same token simultaneously.
# Returns 1 if the slot was newly claimed, 0 if it was already claimed.
_CLAIM_SCRIPT = """
local claimed = redis.call('HGET', KEYS[1], 'slot_claimed')
if claimed == 'true' then return 0 end
redis.call('HSET', KEYS[1], 'slot_claimed', 'true')
redis.call('INCR', KEYS[2])
return 1
"""

_redis: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


@router.websocket("/demo/{token}")
async def demo_websocket(websocket: WebSocket, token: str):
    redis = await _get_redis()
    session_key = f"demo:session:{token}"

    session = await redis.hgetall(session_key)
    if not session:
        await websocket.close(code=1008, reason="Invalid or expired token")
        return

    # Atomically claim the slot — prevents TOCTOU race on concurrent connections
    claimed = await redis.eval(_CLAIM_SCRIPT, 2, session_key, "demo:slots:active")
    if not claimed:
        await websocket.close(code=1008, reason="Token already used")
        return

    workflow_id = int(session["workflow_id"])
    workflow_run_id = int(session["workflow_run_id"])

    await websocket.accept()

    demo_user = await db_client.get_user_by_id(DEMO_USER_ID)
    if not demo_user:
        await websocket.close(code=1011, reason="Demo not configured")
        return

    pc: SmallWebRTCConnection | None = None

    async def ws_sender(message: dict):
        if websocket.application_state == WebSocketState.CONNECTED:
            await websocket.send_json(message)

    register_ws_sender(workflow_run_id, ws_sender)

    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")
            payload = message.get("payload", {})

            if msg_type == "offer":
                pc_id = payload.get("pc_id")
                sdp = payload.get("sdp")
                type_ = payload.get("type")

                ice_servers = get_ice_servers(user_id="demo")
                pc = SmallWebRTCConnection(ice_servers=ice_servers, connection_timeout_secs=60)
                pc._pc_id = pc_id
                await pc.initialize(sdp=sdp, type=type_)

                asyncio.create_task(
                    run_pipeline_smallwebrtc(pc, workflow_id, workflow_run_id, DEMO_USER_ID)
                )

                answer = pc.get_answer()
                await websocket.send_json({
                    "type": "answer",
                    "payload": {
                        "sdp": filter_outbound_sdp(answer["sdp"]),
                        "type": answer["type"],
                        "pc_id": answer["pc_id"],
                    },
                })

            elif msg_type == "ice-candidate" and pc:
                candidate_data = payload.get("candidate")
                if candidate_data:
                    candidate_str = candidate_data.get("candidate", "")
                    if _keep_candidate(candidate_str, ICE_INBOUND_POLICY):
                        try:
                            candidate = candidate_from_sdp(candidate_str)
                            candidate.sdpMid = candidate_data.get("sdpMid")
                            candidate.sdpMLineIndex = candidate_data.get("sdpMLineIndex")
                            await pc.add_ice_candidate(candidate)
                        except Exception as e:
                            logger.error(f"Demo ICE candidate error: {e}")

    except WebSocketDisconnect:
        logger.info(f"Demo WebSocket disconnected for token {token[:8]}...")
    except Exception as e:
        logger.error(f"Demo WebSocket error: {e}")
    finally:
        unregister_ws_sender(workflow_run_id)
        if pc:
            await pc.disconnect()
        deleted = await redis.delete(session_key)
        if deleted:
            await redis.decr("demo:slots:active")
        logger.info(f"Demo slot freed for token {token[:8]}...")
