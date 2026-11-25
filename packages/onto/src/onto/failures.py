"""What to tell the person when a command cannot run at all."""

from __future__ import annotations


def describe(exc: BaseException) -> str:
    """One line for an exception the CLI stops on, naming the file when one is involved."""
    if isinstance(exc, OSError) and exc.filename:
        return f"{exc.filename}: {exc.strerror or 'cannot be read'}"
    return str(exc.args[0]) if exc.args else str(exc)


def missing(what: str, path: str, remedy: str) -> FileNotFoundError:
    return FileNotFoundError(f"{path} is missing. It is {what}: {remedy}")
