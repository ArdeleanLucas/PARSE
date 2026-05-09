from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

COMPUTE_DISPATCH_FUNCTIONS = ("_compute_subprocess_entry", "_run_compute_job")


@dataclass(frozen=True)
class ComputeDispatchEntry:
    dispatch_function: str
    lineno: int
    aliases: tuple[str, ...]
    runner_attr: str

    @property
    def canonical_type(self) -> str:
        return self.aliases[0]


class _DispatchParseError(RuntimeError):
    pass


def _jobs_path() -> Path:
    return Path(__file__).resolve().with_name("jobs.py")


def _normalized_type_aliases(test: ast.AST) -> tuple[str, ...] | None:
    if not isinstance(test, ast.Compare):
        return None
    if not isinstance(test.left, ast.Name) or test.left.id != "normalized_type":
        return None
    if len(test.ops) != 1 or len(test.comparators) != 1:
        return None

    op = test.ops[0]
    comparator = test.comparators[0]
    if isinstance(op, ast.Eq):
        if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
            return (comparator.value,)
        raise _DispatchParseError(
            f"normalized_type equality at line {test.lineno} must compare against a string literal"
        )
    if isinstance(op, ast.In):
        if not isinstance(comparator, (ast.Set, ast.Tuple, ast.List)):
            raise _DispatchParseError(
                f"normalized_type membership at line {test.lineno} must use a literal set/tuple/list"
            )
        aliases: list[str] = []
        for element in comparator.elts:
            if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
                raise _DispatchParseError(
                    f"normalized_type membership at line {test.lineno} contains non-string literal"
                )
            aliases.append(element.value)
        return tuple(aliases)
    return None


def _runner_attr_from_body(dispatch_function: str, node: ast.If) -> str:
    for statement in node.body:
        for child in ast.walk(statement):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "_server"
                and func.attr.startswith("_compute_")
            ):
                return func.attr
    aliases = _normalized_type_aliases(node.test)
    raise _DispatchParseError(
        f"{dispatch_function}:{node.lineno} has aliases {aliases!r} but no _server._compute_* call"
    )


def _dispatch_entries_from_function(function: ast.FunctionDef) -> tuple[ComputeDispatchEntry, ...]:
    entries: list[ComputeDispatchEntry] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.If):
            continue
        aliases = _normalized_type_aliases(node.test)
        if aliases is None:
            continue
        if not aliases:
            raise _DispatchParseError(f"{function.name}:{node.lineno} has an empty compute_type alias set")
        entries.append(
            ComputeDispatchEntry(
                dispatch_function=function.name,
                lineno=node.lineno,
                aliases=aliases,
                runner_attr=_runner_attr_from_body(function.name, node),
            )
        )
    return tuple(sorted(entries, key=lambda entry: entry.lineno))


def parse_compute_dispatches(jobs_path: Path | None = None) -> dict[str, tuple[ComputeDispatchEntry, ...]]:
    """AST-parse jobs.py and return compute_type dispatch entries by runner function."""
    path = jobs_path or _jobs_path()
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    functions = {
        node.name: node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name in COMPUTE_DISPATCH_FUNCTIONS
    }
    dispatches: dict[str, tuple[ComputeDispatchEntry, ...]] = {}
    for function_name in COMPUTE_DISPATCH_FUNCTIONS:
        function = functions.get(function_name)
        if function is None:
            continue
        entries = _dispatch_entries_from_function(function)
        if entries:
            dispatches[function_name] = entries
    return dispatches


def list_canonical_compute_types(jobs_path: Path | None = None) -> list[str]:
    """Return the canonical compute_type for each registered dispatch branch.

    The first alias written in jobs.py is treated as the canonical HTTP
    compute_type for tests that need one representative payload per branch.
    """
    dispatches = parse_compute_dispatches(jobs_path)
    entries = dispatches.get("_run_compute_job") or dispatches.get("_compute_subprocess_entry") or ()
    return [entry.canonical_type for entry in entries]
