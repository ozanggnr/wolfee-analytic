"""Domain errors raised by services. Routers translate them to HTTP status codes."""


from sqlalchemy.exc import IntegrityError


def is_unique_violation(exc: IntegrityError, index_name: str, sqlite_columns: str) -> bool:
    """True only when `exc` is a violation of the named unique index.

    Postgres reports the index name; SQLite reports the column list instead.
    Any other integrity failure must propagate rather than be shown as a conflict.
    """
    message = str(exc.orig)
    return index_name in message or f"UNIQUE constraint failed: {sqlite_columns}" in message


class ServiceError(Exception):
    """Base class; the message is safe to show to the caller."""


class NotFoundError(ServiceError):
    """The resource does not exist or belongs to another user. Callers cannot tell which."""


class ConflictError(ServiceError):
    """The request is valid but clashes with the current state."""


class InvalidInputError(ServiceError):
    """The request is well-formed but breaks a business rule."""
