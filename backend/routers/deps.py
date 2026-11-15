"""Dependencies and helpers shared by the /api/v1 routers."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Annotated, Iterator

from fastapi import HTTPException, Path, Query, Response, status

from schemas.common import DEFAULT_PAGE_LIMIT, MAX_INT32, MAX_INT64, MAX_PAGE_LIMIT
from services.errors import ConflictError, InvalidInputError, NotFoundError

PortfolioId = Annotated[int, Path(ge=1, le=MAX_INT32)]
TransactionId = Annotated[int, Path(ge=1, le=MAX_INT64)]
Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)]
Offset = Annotated[int, Query(ge=0, le=MAX_INT32)]

DEFAULT_LIMIT = DEFAULT_PAGE_LIMIT
NO_STORE = {"Cache-Control": "no-store, private"}

_STATUS_BY_ERROR = (
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (ConflictError, status.HTTP_409_CONFLICT),
    (InvalidInputError, 422),  # the named constant differs between Starlette versions
)


def no_store(response: Response) -> None:
    """A user's financial records must not be kept by browser or proxy caches."""
    response.headers.update(NO_STORE)


@contextmanager
def http_errors() -> Iterator[None]:
    """Translate service errors to the contract's `{"detail": ...}` responses."""
    try:
        yield
    except (NotFoundError, ConflictError, InvalidInputError) as exc:
        code = next(code for kind, code in _STATUS_BY_ERROR if isinstance(exc, kind))
        raise HTTPException(status_code=code, detail=str(exc), headers=NO_STORE) from exc
