"""
Collection runs — mounted at `/admin/runs`. Admin only.

`POST` starts a run of one source NOW: the claim and the run row are created
before the response (so a run already in progress is a 409 the admin sees),
and the fetching happens afterwards on the task dispatcher. The response is
the run in `running` state; the screen polls `GET /{run_id}` for the outcome.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.modules.recommendation.api.dependencies import get_job_scorer
from src.modules.recommendation.domain.services.job_scorer import JobScorer
from src.modules.user.domain.entities.user import User
from src.shared.api.auth.dependencies import ADMIN_ONLY, hasAccess
from src.shared.application.schemas.pagination import (
    ListQueryParams,
    PaginatedResponseSchema,
    list_query_params,
)
from src.shared.infrastructure.database import SessionFactory, get_session_factory
from src.shared.infrastructure.security.rate_limiter import enforce, manual_run_limiter
from src.shared.infrastructure.tasks.dispatcher import (
    TaskDispatcher,
    get_task_dispatcher,
)

from ...application.schemas.collection_run_schema import (
    CollectionRunSchema,
    StartRunSchema,
)
from ...application.use_cases.run_history_use_cases import (
    GetRunUseCase,
    ListRunsUseCase,
    present_runs,
)
from ...application.use_cases.run_use_cases import ExecuteRunUseCase, StartRunUseCase
from ...domain.enums.run_status import RunStatus
from ...domain.enums.run_trigger import RunTrigger
from ..dependencies import (
    get_get_run_use_case,
    get_list_runs_use_case,
    get_start_run_use_case,
)

router = APIRouter(tags=["Admin Collection Runs"])


@router.get("", response_model=PaginatedResponseSchema[CollectionRunSchema])
async def list_runs(
    source_id: Optional[UUID] = Query(default=None, description="One source's runs"),
    status_filter: Optional[RunStatus] = Query(default=None, alias="status"),
    trigger: Optional[RunTrigger] = Query(default=None),
    params: ListQueryParams = Depends(list_query_params),
    current_user: User = Depends(hasAccess(roles=ADMIN_ONLY)),
    use_case: ListRunsUseCase = Depends(get_list_runs_use_case),
):
    """
    List collection runs, newest first.

    **Access:** Admin only

    Sort by `started_at` (default), `finished_at`, `status`, `created_count`
    or `fetched_count`.
    """
    items, total = await use_case.execute(
        params, source_id=source_id, status=status_filter, trigger=trigger
    )
    return PaginatedResponseSchema.build(items, total, params)


@router.post(
    "", response_model=CollectionRunSchema, status_code=status.HTTP_202_ACCEPTED
)
async def start_run(
    payload: StartRunSchema,
    current_user: User = Depends(hasAccess(roles=ADMIN_ONLY)),
    use_case: StartRunUseCase = Depends(get_start_run_use_case),
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),
    session_factory: SessionFactory = Depends(get_session_factory),
    scorer: JobScorer = Depends(get_job_scorer),
):
    """
    Collect from one source now.

    **Access:** Admin only; rate limited per admin

    Returns at once with the run in `running` state. Poll `GET /admin/runs/{id}`.

    **Errors:**
    - 404 if the source does not exist
    - 409 if a run of this source is already in progress
    - 429 when the hourly manual-run budget is spent
    """
    enforce(manual_run_limiter, f"user:{current_user.id}")
    run = await use_case.execute(
        payload.source_id, trigger=RunTrigger.MANUAL, triggered_by=current_user.id
    )
    run_id = run.id
    assert run_id is not None
    snapshot = present_runs(use_case.runs.session, [run])[0]

    async def execute() -> None:
        # Its own session: the request's is closed by the time this runs.
        with session_factory() as session:
            await ExecuteRunUseCase(session, scorer=scorer).execute(run_id)

    await dispatcher.submit(execute, name=f"collection-run:{run_id}")
    return snapshot


@router.get("/{run_id}", response_model=CollectionRunSchema)
async def get_run(
    run_id: UUID,
    current_user: User = Depends(hasAccess(roles=ADMIN_ONLY)),
    use_case: GetRunUseCase = Depends(get_get_run_use_case),
):
    """
    Read one run — what the screen polls while it is `running`.

    **Access:** Admin only

    **Errors:**
    - 404 if no run has this id
    """
    return await use_case.execute(run_id)
