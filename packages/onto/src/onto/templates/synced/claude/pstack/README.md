# Vendored pstack

`upstream/` holds the pstack files this repository builds on, copied unchanged
from one pinned commit. The skills under `.claude/skills/` are adapted from them.
[`NOTICE.md`](NOTICE.md) says what was taken and what was changed.

Nothing under `upstream/` is loaded by Claude Code: it is not a skills folder.
It is kept so that the difference between upstream and this repository is always
one command away.

```bash
python tools/check_vendored.py          # the copies still match the pinned commit
python tools/check_vendored.py --diff   # what each adapted skill changed
```

## Taking a newer pstack

1. Clone <https://github.com/michael-denyer/pstack-claude> at the commit you want and read its `CHANGES.md` from the pinned commit to that one.
2. For each file in `provenance.json`, diff the new upstream file against the copy in `upstream/`. That is what upstream changed.
3. Carry each change you want into the adapted skill by hand. Read every line you take: these files instruct an agent that can edit this repository.
4. Replace the copy in `upstream/`, update its `sha256` and the `commit` in `provenance.json`, and note anything new in `NOTICE.md`.
5. `python tools/check_vendored.py` passes, and the pull request is reviewed by the owners of `.claude/` in CODEOWNERS.

## Adding another pstack skill

Copy the file into `upstream/` unchanged, add an entry to `provenance.json`
with its hash, write the adapted version under `.claude/skills/<name>/SKILL.md`
with a comment naming its source, and add a row to `NOTICE.md`.
