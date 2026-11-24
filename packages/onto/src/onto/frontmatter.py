"""Markdown files with YAML frontmatter: the on-disk form of every work item."""

from __future__ import annotations

import yaml

DELIMITER = "---"


class FrontmatterError(ValueError):
    """The file does not start with a well-formed YAML frontmatter block."""


class _Loader(yaml.SafeLoader):
    """SafeLoader that leaves dates as the strings the author wrote.

    The JSON Schema describes dates and timestamps as strings with a format,
    so they must not be turned into datetime objects on the way in.
    """


_Loader.yaml_implicit_resolvers = {
    key: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


class _Dumper(yaml.SafeDumper):
    pass


def _represent_str(dumper: yaml.Dumper, value: str) -> yaml.Node:
    # Long prose (EARS sentences, rationales) reads best as a folded block.
    if len(value) > 72 and "\n" not in value.strip():
        return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=">")
    return dumper.represent_scalar("tag:yaml.org,2002:str", value)


def _represent_list(dumper: yaml.Dumper, value: list) -> yaml.Node:
    # Lists of ids and terms stay on one line; the mapping itself is one key per line.
    return dumper.represent_sequence("tag:yaml.org,2002:seq", value, flow_style=True)


_Dumper.add_representer(str, _represent_str)
_Dumper.add_representer(list, _represent_list)


def split(text: str) -> tuple[dict, str]:
    """Return (frontmatter, body). Raises FrontmatterError if there is no frontmatter."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != DELIMITER:
        raise FrontmatterError("file does not start with a '---' frontmatter block")
    for index in range(1, len(lines)):
        if lines[index].strip() == DELIMITER:
            break
    else:
        raise FrontmatterError("frontmatter block is not closed with '---'")
    try:
        meta = yaml.load("\n".join(lines[1:index]), Loader=_Loader)
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(meta, dict):
        raise FrontmatterError("frontmatter must be a YAML mapping")
    body = "\n".join(lines[index + 1 :]).strip("\n")
    return meta, body


def render(meta: dict, body: str = "") -> str:
    """Serialise frontmatter and body back into file content."""
    dumped = yaml.dump(
        meta,
        Dumper=_Dumper,
        sort_keys=False,
        allow_unicode=True,
        width=88,
        default_flow_style=False,
    )
    text = f"{DELIMITER}\n{dumped}{DELIMITER}\n"
    if body.strip():
        text += f"\n{body.strip()}\n"
    return text
