"""One-time script: create the locked demo org, system user, and model config.

Run once on a fresh deployment (idempotent — safe to re-run):
    source venv/bin/activate
    set -a && source api/.env && set +a
    python -m api.scripts.bootstrap_demo_org

Prints DEMO_ORG_ID and DEMO_USER_ID to add to .env. Also provisions the demo
user's STT/LLM/TTS configuration so demo voice sessions don't crash with a
missing-provider error. Override the defaults via the DEMO_*_MODEL /
DEMO_*_BASE_URL env vars (see _demo_user_configuration).
"""
import asyncio
import os
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.constants import DATABASE_URL
from api.db.models import (
    OrganizationModel,
    UserConfigurationModel,
    UserModel,
    organization_users_association,
)


def _demo_user_configuration() -> dict:
    """Build the demo user's STT/LLM/TTS config from env vars (with local defaults).

    Mirrors the local Speaches (STT/TTS) + Ollama (LLM) stack. Each value is
    overridable so the same script works on a differently-addressed deployment.
    """
    return {
        "llm": {
            "provider": "speaches",
            "api_key": None,
            "model": os.getenv("DEMO_LLM_MODEL", "qwen2.5:3b-instruct"),
            "base_url": os.getenv("DEMO_LLM_BASE_URL", "http://192.168.70.122:11434/v1"),
        },
        "stt": {
            "provider": "speaches",
            "api_key": None,
            "model": os.getenv("DEMO_STT_MODEL", "Systran/faster-distil-whisper-large-v3"),
            "language": "en",
            "base_url": os.getenv("DEMO_STT_BASE_URL", "http://192.168.70.122:8011/v1"),
        },
        "tts": {
            "provider": "speaches",
            "api_key": None,
            "model": os.getenv("DEMO_TTS_MODEL", "speaches-ai/Kokoro-82M-v1.0-ONNX"),
            "voice": os.getenv("DEMO_TTS_VOICE", "af_heart"),
            "base_url": os.getenv("DEMO_TTS_BASE_URL", "http://192.168.70.122:8011/v1"),
            "speed": 1.0,
        },
        "embeddings": None,
        "realtime": None,
        "is_realtime": False,
        "test_phone_number": None,
        "timezone": None,
        "last_validated_at": None,
    }


async def main():
    engine = create_async_engine(DATABASE_URL)
    AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with AsyncSessionLocal() as session:
        # Check if demo org already exists
        result = await session.execute(
            select(OrganizationModel).where(
                OrganizationModel.provider_id == "demo-org-voiceflowx"
            )
        )
        org = result.scalars().first()
        if not org:
            org = OrganizationModel(
                provider_id="demo-org-voiceflowx",
                quota_enabled=False,
            )
            session.add(org)
            await session.flush()

        # Check if demo user already exists
        result = await session.execute(
            select(UserModel).where(UserModel.email == "demo-system@voiceflowx.internal")
        )
        user = result.scalars().first()
        if not user:
            user = UserModel(
                email="demo-system@voiceflowx.internal",
                provider_id=f"demo-system-{uuid.uuid4()}",
                selected_organization_id=org.id,
            )
            session.add(user)
            await session.flush()

        # Always ensure M2M association exists (idempotent via ON CONFLICT DO NOTHING)
        stmt = pg_insert(organization_users_association).values(
            user_id=user.id, organization_id=org.id
        )
        stmt = stmt.on_conflict_do_nothing()
        await session.execute(stmt)

        # Ensure the demo user has an STT/LLM/TTS configuration. Without it the
        # pipeline crashes with "'NoneType' object has no attribute 'provider'".
        result = await session.execute(
            select(UserConfigurationModel).where(
                UserConfigurationModel.user_id == user.id
            )
        )
        user_config = result.scalars().first()
        if not user_config:
            session.add(
                UserConfigurationModel(
                    user_id=user.id,
                    configuration=_demo_user_configuration(),
                )
            )
        else:
            # Refresh in place so re-running picks up changed env defaults.
            user_config.configuration = _demo_user_configuration()

        await session.commit()
        print(f"DEMO_ORG_ID={org.id}")
        print(f"DEMO_USER_ID={user.id}")
        print("Demo user STT/LLM/TTS configuration provisioned.")
        print("Add DEMO_ORG_ID and DEMO_USER_ID to api/.env")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
