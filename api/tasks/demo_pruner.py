"""Hourly ARQ cron job: delete demo workflow rows older than 24 hours."""
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.constants import DATABASE_URL, DEMO_ORG_ID
from api.db.models import WorkflowDefinitionModel, WorkflowModel, WorkflowRunModel


async def prune_demo_workflows(ctx):
    if not DEMO_ORG_ID:
        return

    cutoff = datetime.now(UTC) - timedelta(hours=24)
    engine = create_async_engine(DATABASE_URL)
    AsyncSession = async_sessionmaker(bind=engine, expire_on_commit=False)

    try:
        async with AsyncSession() as session:
            result = await session.execute(
                select(WorkflowModel.id).where(
                    WorkflowModel.organization_id == DEMO_ORG_ID,
                    WorkflowModel.is_demo == True,  # noqa: E712
                    WorkflowModel.created_at < cutoff,
                )
            )
            old_ids = [row[0] for row in result.all()]
            if not old_ids:
                return

            # Clear released_definition_id FK (self-ref from workflows → workflow_definitions)
            await session.execute(
                update(WorkflowModel)
                .where(WorkflowModel.id.in_(old_ids))
                .values(released_definition_id=None)
            )
            # Delete runs (FK: workflow_runs.workflow_id → workflows.id)
            await session.execute(
                delete(WorkflowRunModel).where(WorkflowRunModel.workflow_id.in_(old_ids))
            )
            # Delete definitions (FK: workflow_definitions.workflow_id → workflows.id)
            await session.execute(
                delete(WorkflowDefinitionModel).where(
                    WorkflowDefinitionModel.workflow_id.in_(old_ids)
                )
            )
            # Delete workflows
            await session.execute(
                delete(WorkflowModel).where(WorkflowModel.id.in_(old_ids))
            )
            await session.commit()
            logger.info(f"Pruned {len(old_ids)} demo workflows older than 24h")
    except Exception as e:
        logger.error(f"Demo pruner error: {e}")
    finally:
        await engine.dispose()
