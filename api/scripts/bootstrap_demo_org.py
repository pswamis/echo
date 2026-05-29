"""One-time script: create the locked demo org and system user.

Run once on a fresh deployment:
    source venv/bin/activate
    set -a && source api/.env && set +a
    python -m api.scripts.bootstrap_demo_org

Prints DEMO_ORG_ID and DEMO_USER_ID to add to .env.
"""
import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.constants import DATABASE_URL
from api.db.models import OrganizationModel, UserModel, organization_users_association


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

        await session.commit()
        print(f"DEMO_ORG_ID={org.id}")
        print(f"DEMO_USER_ID={user.id}")
        print("Add these to api/.env")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
