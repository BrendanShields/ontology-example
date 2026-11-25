"""What to tell the person when a command cannot run at all."""

from __future__ import annotations

from pathlib import Path

import yaml


def describe(exc: BaseException) -> str:
    """One line for an exception the CLI stops on, naming the file when one is involved."""
    if isinstance(exc, OSError) and exc.filename:
        return f"{exc.filename}: {exc.strerror or 'cannot be read'}"
    return str(exc.args[0]) if exc.args else str(exc)


class SourceUnreadable(ValueError):
    """An ontology source that is not YAML. Says where, never what the parser quoted."""

    def __init__(self, path: Path | str, exc: yaml.YAMLError):
        mark = getattr(exc, "problem_mark", None)
        self.path = Path(path)
        self.where = f" (line {mark.line + 1})" if mark is not None else ""
        super().__init__(f"{path} cannot be read as YAML{self.where}: fix the syntax there")


def missing(what: str, path: str, remedy: str) -> FileNotFoundError:
    return FileNotFoundError(f"{path} is missing. It is {what}: {remedy}")
