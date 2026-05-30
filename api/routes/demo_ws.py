"""Public WebSocket endpoint for demo voice sessions.

Token-protected: a valid token must have been issued by voiceflow-demo-api
via POST /internal/demo/create and stored in Redis. Single-use (slot_claimed
prevents replay).

Connection handling is delegated to the production ``signaling_manager`` — the
exact same SignalingManager used by authenticated and embed calls — so demo
sessions inherit its full WebRTC lifecycle (offer / ICE trickling /
renegotiation / peer-connection cleanup) rather than a hand-rolled subset. The
only demo-specific concerns kept here are token validation and slot accounting.
"""
import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from api.constants import DEMO_USER_ID, REDIS_URL
from api.db import db_client
from api.routes.webrtc_signaling import signaling_manager

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

    # Atomically claim the slot — prevents TOCTOU race on concurrent connections.
    claimed = await redis.eval(_CLAIM_SCRIPT, 2, session_key, "demo:slots:active")
    if not claimed:
        await websocket.close(code=1008, reason="Token already used")
        return

    # Slot is now claimed (counter incremented). Guarantee it is always freed.
    try:
        workflow_id = int(session["workflow_id"])
        workflow_run_id = int(session["workflow_run_id"])

        demo_user = await db_client.get_user_by_id(DEMO_USER_ID)
        if not demo_user:
            await websocket.close(code=1011, reason="Demo not configured")
            return

        # Delegate to the production signaling manager — identical WebRTC
        # connection handling to authenticated/embed calls (it calls
        # websocket.accept() and owns the offer/ICE/renegotiation loop).
        await signaling_manager.handle_websocket(
            websocket, workflow_id, workflow_run_id, demo_user
        )
    except WebSocketDisconnect:
        logger.info(f"Demo WebSocket disconnected for token {token[:8]}...")
    except Exception as e:
        logger.error(f"Demo WebSocket error: {e}")
    finally:
        deleted = await redis.delete(session_key)
        if deleted:
            await redis.decr("demo:slots:active")
        logger.info(f"Demo slot freed for token {token[:8]}...")
