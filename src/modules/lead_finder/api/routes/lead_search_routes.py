"""
Business searches — mounted at `/lead/searches`. Lead finders only, own rows only.

`POST` queues a search and returns it at once (`queued`); the Places calls run
afterwards on the task dispatcher. The screen polls `GET /{id}` for progress.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from src.modules.user.domain.entities.user import User
from src.shared.api.auth.dependencies import LEAD_FINDER_ONLY, hasAccess
from src.shared.application.schemas.pagination import (
    ListQueryParams,
    PaginatedResponseSchema,
    list_query_params,
)
from src.shared.infrastructure.database import SessionFactory, get_session_factory
from src.shared.infrastructure.security.rate_limiter import enforce, lead_search_limiter
from src.shared.infrastructure.tasks.dispatcher import (
    TaskDispatcher,
    get_task_dispatcher,
)

from ...application.schemas.lead_finder_schema import SearchSchema, StartSearchSchema
from ...application.use_cases.search_use_cases import (
    DeleteSearchUseCase,
    ExecuteSearchUseCase,
    GatewayFactory,
    GetSearchUseCase,
    ListSearchesUseCase,
    RerunSearchUseCase,
    StartSearchUseCase,
)
from ...domain.enums import SearchStatus
from ..dependencies import (
    get_delete_search_use_case,
    get_get_search_use_case,
    get_list_searches_use_case,
    get_places_gateway_factory,
    get_rerun_search_use_case,
    get_start_search_use_case,
)

router = APIRouter(tags=["Lead Finder Searches"])


async def _dispatch(
    search: SearchSchema,
    dispatcher: TaskDispatcher,
    session_factory: SessionFactory,
    gateway_factory: GatewayFactory,
) -> None:
    search_id = search.id

    async def execute() -> None:
        # Its own session: the request's is closed by the time this runs.
        with session_factory() as session:
            await ExecuteSearchUseCase(session, gateway_factory).execute(search_id)

    await dispatcher.submit(execute, name=f"lead-search:{search_id}")


@router.get("", response_model=PaginatedResponseSchema[SearchSchema])
async def list_searches(
    status_filter: Optional[SearchStatus] = Query(default=None, alias="status"),
    params: ListQueryParams = Depends(list_query_params),
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: ListSearchesUseCase = Depends(get_list_searches_use_case),
):
    """
    The caller's search history, newest first.

    Searchable over keyword and location; sort by `created_at`, `keyword`,
    `total_results`, `leads_found` or `status`.
    """
    assert current_user.id is not None
    items, total = await use_case.execute(current_user.id, params, status_filter)
    return PaginatedResponseSchema.build(items, total, params)


@router.post("", response_model=SearchSchema, status_code=status.HTTP_202_ACCEPTED)
async def start_search(
    payload: StartSearchSchema,
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: StartSearchUseCase = Depends(get_start_search_use_case),
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),
    session_factory: SessionFactory = Depends(get_session_factory),
    gateway_factory: GatewayFactory = Depends(get_places_gateway_factory),
):
    """
    Start a business search. Returns at once with the search `queued`.

    An empty `locations` list searches all of Bangladesh (every district).

    **Errors:**
    - 409 if the caller already has a search running
    - 422 for an unknown location or category
    - 429 when today's Places quota or the hourly search limit is spent
    - 502 when no Google Maps API key is configured
    """
    enforce(lead_search_limiter, f"user:{current_user.id}")
    assert current_user.id is not None
    search = await use_case.execute(current_user.id, payload)
    await _dispatch(search, dispatcher, session_factory, gateway_factory)
    return search


@router.get("/{search_id}", response_model=SearchSchema)
async def get_search(
    search_id: UUID,
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: GetSearchUseCase = Depends(get_get_search_use_case),
):
    """One search, with progress. **Errors:** 404 if not the caller's."""
    assert current_user.id is not None
    return await use_case.execute(current_user.id, search_id)


@router.post(
    "/{search_id}/rerun",
    response_model=SearchSchema,
    status_code=status.HTTP_202_ACCEPTED,
)
async def rerun_search(
    search_id: UUID,
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: RerunSearchUseCase = Depends(get_rerun_search_use_case),
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),
    session_factory: SessionFactory = Depends(get_session_factory),
    gateway_factory: GatewayFactory = Depends(get_places_gateway_factory),
):
    """Run a past search again as a new search. Same errors as starting one."""
    enforce(lead_search_limiter, f"user:{current_user.id}")
    assert current_user.id is not None
    search = await use_case.execute(current_user.id, search_id)
    await _dispatch(search, dispatcher, session_factory, gateway_factory)
    return search


@router.delete("/{search_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_search(
    search_id: UUID,
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: DeleteSearchUseCase = Depends(get_delete_search_use_case),
):
    """
    Remove a search from the history. Saved leads it found stay saved.

    **Errors:** 404 if not the caller's; 409 while it is still running.
    """
    assert current_user.id is not None
    await use_case.execute(current_user.id, search_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
