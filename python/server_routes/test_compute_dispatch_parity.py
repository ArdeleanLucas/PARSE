from __future__ import annotations

import importlib
from collections.abc import Mapping

import server

from server_routes._compute_dispatch_introspection import parse_compute_dispatches


_EXPECTED_DISPATCH_FUNCTIONS = ("_compute_subprocess_entry", "_run_compute_job")


def _alias_to_runner(entries) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for entry in entries:
        assert entry.aliases, f"{entry.dispatch_function}:{entry.lineno} has no compute_type aliases"
        for alias in entry.aliases:
            assert isinstance(alias, str), f"{entry.dispatch_function}:{entry.lineno} contains non-string alias {alias!r}"
            assert alias, f"{entry.dispatch_function}:{entry.lineno} contains an empty compute_type alias"
            previous = mapping.setdefault(alias, entry.runner_attr)
            assert previous == entry.runner_attr, (
                f"compute_type {alias!r} maps to both {previous!r} and {entry.runner_attr!r} "
                f"inside {entry.dispatch_function}"
            )
    return mapping


def test_compute_dispatch_alias_sets_match_between_runner_modes() -> None:
    dispatches = parse_compute_dispatches()
    missing_functions = [name for name in _EXPECTED_DISPATCH_FUNCTIONS if name not in dispatches]
    assert not missing_functions, f"jobs.py missing compute dispatch chains for: {missing_functions!r}"

    child_aliases = _alias_to_runner(dispatches["_compute_subprocess_entry"])
    thread_aliases = _alias_to_runner(dispatches["_run_compute_job"])

    missing_from_child = sorted(set(thread_aliases) - set(child_aliases))
    missing_from_thread = sorted(set(child_aliases) - set(thread_aliases))
    assert not missing_from_child and not missing_from_thread, (
        "compute dispatch alias parity mismatch between jobs.py runner modes; "
        f"registered only in _run_compute_job: {missing_from_child}; "
        f"registered only in _compute_subprocess_entry: {missing_from_thread}"
    )

    mismatched_runners = {
        alias: (child_aliases[alias], thread_aliases[alias])
        for alias in sorted(child_aliases)
        if child_aliases[alias] != thread_aliases[alias]
    }
    assert not mismatched_runners, (
        "compute dispatch aliases must call the same runner in subprocess and thread modes; "
        f"mismatches: {mismatched_runners!r}"
    )


def test_compute_dispatch_aliases_map_to_importable_server_runners() -> None:
    dispatches: Mapping[str, tuple[object, ...]] = parse_compute_dispatches()
    importlib.import_module("server")

    missing: list[str] = []
    non_callable: list[str] = []
    for dispatch_function in _EXPECTED_DISPATCH_FUNCTIONS:
        for entry in dispatches[dispatch_function]:
            assert entry.runner_attr.startswith("_compute_"), (
                f"{entry.dispatch_function}:{entry.lineno} maps {entry.aliases!r} "
                f"to non-compute runner {entry.runner_attr!r}"
            )
            if not hasattr(server, entry.runner_attr):
                missing.append(f"{entry.runner_attr} for aliases {entry.aliases!r}")
            elif not callable(getattr(server, entry.runner_attr)):
                non_callable.append(f"{entry.runner_attr} for aliases {entry.aliases!r}")

    assert not missing, "jobs.py dispatch references missing server runner(s): " + "; ".join(missing)
    assert not non_callable, "jobs.py dispatch references non-callable server runner(s): " + "; ".join(non_callable)
