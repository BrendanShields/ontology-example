"""pytest plugin: `pytest --onto-evidence` records Evidence for the Test work items.

The plugin is registered through the `pytest11` entry point of onto-cli and does
nothing unless the option is given.
"""

from __future__ import annotations

from .evidence import PASSED


def pytest_addoption(parser) -> None:
    group = parser.getgroup("onto", "ontology traceability")
    group.addoption(
        "--onto-evidence",
        action="store_true",
        default=False,
        help="record the outcome of each Test work item under work/evidence/",
    )


def pytest_configure(config) -> None:
    if config.getoption("--onto-evidence"):
        config.pluginmanager.register(_Recorder(config), "onto-evidence-recorder")


class _Recorder:
    def __init__(self, config) -> None:
        self.root = config.rootpath
        self.outcomes: dict[str, str] = {}
        self.deselected: set[str] = set()
        self.written: list[str] = []
        self.error: str | None = None

    def pytest_deselected(self, items) -> None:
        self.deselected.update(item.nodeid for item in items)

    def pytest_runtest_logreport(self, report) -> None:
        # A node passed only if its call phase passed and no phase failed.
        # A skipped or expected-to-fail test proves nothing, so it is not a pass.
        previous = self.outcomes.get(report.nodeid)
        if report.failed:
            self.outcomes[report.nodeid] = "failed"
        elif report.skipped and previous != "failed":
            self.outcomes[report.nodeid] = "skipped"
        elif report.when == "call" and report.passed and previous is None:
            self.outcomes[report.nodeid] = PASSED

    def pytest_sessionfinish(self, session) -> None:
        from .evidence import record
        from .workspace import Workspace

        try:
            self.written = record(Workspace.at(self.root), self.outcomes, self.deselected)
        except Exception as exc:  # never turn a test run red because recording failed
            self.error = f"{type(exc).__name__}: {exc}"

    def pytest_terminal_summary(self, terminalreporter) -> None:
        if self.error:
            terminalreporter.write_line(f"onto: could not record evidence ({self.error})", red=True)
        else:
            terminalreporter.write_line(
                f"onto: recorded evidence for {len(self.written)} test item(s) in work/evidence/"
            )
