def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers", "mutants: plants faults in a copy of the package; skip with -m 'not mutants'"
    )
