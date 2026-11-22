"""Pure AST checker for the stdlib and private-import restrictions on ``src/leva`` (D-002).

Every import, dotted attribute chain rooted at an imported name, and reference to a builtin
becomes a qualified name (``subprocess.run``, ``os.environ``, ``builtins.print``,
``leva.store._schema``). Rules decide which modules may use which qualified names.
"""

from __future__ import annotations

import ast
import builtins
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypeGuard

BUILTIN_NAMES: Final = frozenset(dir(builtins))


@dataclass(frozen=True, slots=True)
class SourceModule:
    """A Python source file under the scanned root, with its dotted module name."""

    name: str
    path: str
    is_package: bool

    @property
    def package(self) -> str:
        """The package that relative imports in this module start from."""
        return self.name if self.is_package else self.name.rpartition(".")[0]


@dataclass(frozen=True, slots=True)
class Use:
    """A qualified name used by a module, with the line that uses it."""

    target: str
    line: int


@dataclass(frozen=True, slots=True)
class Violation:
    """A use that a rule forbids; ``path`` is relative to the scanned root."""

    path: str
    line: int
    rule: str
    target: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.target}"


@dataclass(frozen=True, slots=True)
class Restriction:
    """Names in ``targets`` (and anything below them) may be used only inside ``allowed``."""

    name: str
    targets: frozenset[str]
    allowed: frozenset[str]

    def forbids(self, module: str, target: str) -> bool:
        return any(within(target, t) for t in self.targets) and not any(
            within(module, a) for a in self.allowed
        )


@dataclass(frozen=True, slots=True)
class PrivateImport:
    """``<root>.X.<..._private...>`` may be used only from inside ``<root>.X``."""

    root: str
    name: str = "private-import"

    def forbids(self, module: str, target: str) -> bool:
        parts = target.split(".")
        if parts[0] != self.root or not any(is_private(p) for p in parts[2:]):
            return False
        return not within(module, ".".join(parts[:2]))


Rule = Restriction | PrivateImport

RULES: Final[tuple[Rule, ...]] = (
    Restriction(
        "subprocess",
        frozenset(
            {
                "subprocess",
                "asyncio.subprocess",
                "asyncio.create_subprocess_exec",
                "asyncio.create_subprocess_shell",
            }
        ),
        frozenset({"leva.clipboard", "leva.sources", "leva.manparse", "leva.verify"}),
    ),
    Restriction(
        "sqlite3", frozenset({"sqlite3"}), frozenset({"leva.store", "leva.repo", "leva.cli"})
    ),
    Restriction(
        "environment",
        frozenset(
            {"os.environ", "os.environb", "os.getenv", "os.getenvb", "os.putenv", "os.unsetenv"}
        ),
        frozenset({"leva.cli"}),
    ),
    Restriction(
        "network",
        frozenset({"socket", "urllib", "http", "ssl", "ftplib", "smtplib"}),
        frozenset(),
    ),
    Restriction(
        "print", frozenset({"builtins.print"}), frozenset({"leva.cli", "leva.verify.__main__"})
    ),
    Restriction("dev-code", frozenset({"spikes", "tests", "tools"}), frozenset()),
    PrivateImport(root="leva"),
)


def within(name: str, prefix: str) -> bool:
    """Return whether dotted ``name`` is ``prefix`` or lies below it."""
    return name == prefix or name.startswith(f"{prefix}.")


def is_private(part: str) -> bool:
    """Return whether a name component is private (``_x``, but not a dunder like ``__main__``)."""
    return part.startswith("_") and not (part.startswith("__") and part.endswith("__"))


def source_modules(root: Path) -> list[SourceModule]:
    """List every ``.py`` file under ``root`` as a module, sorted by path."""
    modules = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        is_package = relative.name == "__init__.py"
        parts = relative.parent.parts if is_package else (*relative.parent.parts, relative.stem)
        modules.append(SourceModule(".".join(parts), relative.as_posix(), is_package))
    return modules


def find_violations(root: Path, rules: Iterable[Rule]) -> list[Violation]:
    """Check every module under ``root`` against ``rules``.

    Returns:
        At most one violation per (path, line, rule), sorted by path, line and rule name.

    Raises:
        ValueError: If a relative import climbs above the top-level package.
        SyntaxError: If a source file does not parse.
    """
    rules = tuple(rules)
    found: dict[tuple[str, int, str], Violation] = {}
    for module in source_modules(root):
        tree = ast.parse((root / module.path).read_text(encoding="utf-8"), module.path)
        for use in collect_uses(tree, module):
            for rule in rules:
                if rule.forbids(module.name, use.target):
                    key = (module.path, use.line, rule.name)
                    found.setdefault(key, Violation(*key, use.target))
    return [found[key] for key in sorted(found)]


def collect_uses(tree: ast.Module, module: SourceModule) -> list[Use]:
    """Return every qualified name ``tree`` uses, in AST walk order."""
    bindings = import_bindings(tree, module)
    uses: list[Use] = []
    for node in ast.walk(tree):
        uses.extend(node_uses(node, module, bindings))
    return uses


def node_uses(node: ast.AST, module: SourceModule, bindings: dict[str, str]) -> Iterator[Use]:
    """Yield the qualified names one AST node uses."""
    if isinstance(node, ast.Import):
        yield from (Use(alias.name, node.lineno) for alias in node.names)
    elif isinstance(node, ast.ImportFrom):
        base = resolve_from(node, module)
        yield from (Use(f"{base}.{alias.name}", node.lineno) for alias in node.names)
    elif isinstance(node, ast.Attribute):
        qualified = qualify(node, bindings)
        if qualified is not None:
            yield Use(qualified, node.lineno)
    elif is_builtin_reference(node, bindings):
        yield Use(f"builtins.{node.id}", node.lineno)


def is_builtin_reference(node: ast.AST, bindings: dict[str, str]) -> TypeGuard[ast.Name]:
    """Return whether ``node`` reads a builtin name that no import in the module rebinds."""
    return (
        isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id in BUILTIN_NAMES
        and node.id not in bindings
    )


def import_bindings(tree: ast.Module, module: SourceModule) -> dict[str, str]:
    """Map each name bound by an import anywhere in ``tree`` to the qualified name it denotes."""
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname is None:
                    top = alias.name.partition(".")[0]
                    bindings[top] = top
                else:
                    bindings[alias.asname] = alias.name
        elif isinstance(node, ast.ImportFrom):
            base = resolve_from(node, module)
            for alias in node.names:
                bindings[alias.asname or alias.name] = f"{base}.{alias.name}"
    return bindings


def resolve_from(node: ast.ImportFrom, module: SourceModule) -> str:
    """Return the absolute module a ``from ... import`` statement imports from."""
    if node.level == 0:
        return node.module or ""
    package = module.package.split(".") if module.package else []
    if node.level > len(package):
        raise ValueError(
            f"{module.path}:{node.lineno}: relative import beyond the top-level package"
        )
    base = package[: len(package) - node.level + 1]
    return ".".join(base if node.module is None else [*base, node.module])


def qualify(node: ast.Attribute, bindings: dict[str, str]) -> str | None:
    """Return the qualified name of ``a.b.c`` when ``a`` is bound by an import, else None."""
    attributes: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        attributes.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name) or current.id not in bindings:
        return None
    return ".".join([bindings[current.id], *reversed(attributes)])
