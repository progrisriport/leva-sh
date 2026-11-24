"""Safety policy for curated commands: the exec denylist and destructive-command detection."""

from __future__ import annotations

import re
import shlex
from collections.abc import Callable, Iterator, Mapping
from pathlib import PurePosixPath
from typing import Final, TypeAlias

from leva import placeholders


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


EXEC_DENYLIST: Final[frozenset[str]] = _words(
    """
    sudo su doas shutdown reboot halt diskutil hdiutil launchctl defaults pmset networksetup scutil
    softwareupdate tmutil systemsetup kill killall pkill crontab ssh ssh-add ssh-agent scp sftp
    curl ping traceroute dig nslookup host nc open osascript say screencapture pbcopy pbpaste
    security xcode-select mdutil mdfind spctl dscl passwd login brew
    """
)

Argv: TypeAlias = tuple[str, ...]

_OPERATOR_CHARS: Final = frozenset("();<>|&")
_ASSIGNMENT: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
_EXEC_FLAGS: Final = frozenset({"-exec", "-execdir", "-ok", "-okdir"})
_EXEC_END: Final = "+"
_SUBSTITUTION: Final = "$"

# Wrapper program -> options that take an argument.
_WRAPPERS: Final[Mapping[str, frozenset[str]]] = {
    "sudo": frozenset({"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U"}),
    "doas": frozenset({"-u", "-C"}),
    "env": frozenset({"-u", "-P", "-S"}),
    "xargs": frozenset({"-E", "-I", "-J", "-L", "-n", "-P", "-R", "-S", "-s"}),
    "nice": frozenset({"-n"}),
    "nohup": frozenset(),
    "time": frozenset(),
    "command": frozenset(),
    "exec": frozenset({"-a"}),
    "caffeinate": frozenset({"-t", "-w"}),
}

_DISKUTIL_DESTRUCTIVE: Final = _words(
    """
    erasedisk erasevolume reformat zerodisk randomdisk secureerase partitiondisk deletecontainer
    deletevolume
    """
)
_GIT_OPTIONS_WITH_ARGUMENT: Final = frozenset({"-C", "-c"})


def _tokenize(cmd: str) -> list[str]:
    """Split `cmd` into shell-like tokens; punctuation runs come back as their own tokens."""
    text = placeholders.to_plain(cmd).replace("\\\n", " ").replace("\n", " ; ")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def _is_operator(token: str) -> bool:
    # A quoted empty word ('') comes back as an empty token: it is a word, not an operator.
    return bool(token) and all(char in _OPERATOR_CHARS for char in token)


def _split_commands(tokens: list[str]) -> Iterator[list[str]]:
    """Yield the words of every simple command.

    Separators split commands; a redirection drops its target and a file descriptor number in
    front of it; a bare ``$`` (the start of ``$(...)``) is dropped.
    """
    current: list[str] = []
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
        elif token == _SUBSTITUTION:
            continue
        elif not _is_operator(token):
            current.append(token)
        elif "<" in token or ">" in token:
            skip_next = True
            if len(current) > 1 and current[-1].isdigit():
                current.pop()
        else:
            yield current
            current = []
    yield current


def _with_basename(words: list[str]) -> Argv:
    return (PurePosixPath(words[0]).name, *words[1:])


def _strip_assignments(words: list[str]) -> list[str]:
    start = 0
    while start < len(words) and _ASSIGNMENT.match(words[start]):
        start += 1
    return words[start:]


def _unwrap(argv: Argv) -> list[str]:
    """Return the words after the wrapper program `argv[0]`, its options and their arguments."""
    takes_argument = _WRAPPERS[argv[0]]
    rest = list(argv[1:])
    index = 0
    while index < len(rest) and rest[index].startswith("-"):
        index += 2 if rest[index] in takes_argument else 1
    rest = rest[index:]
    return _strip_assignments(rest) if argv[0] == "env" else rest


def _exec_clauses(argv: Argv) -> Iterator[list[str]]:
    r"""Yield the command of every ``-exec`` style clause of a ``find`` argv.

    A clause that was split off its ``find`` by an escaped ``\\;`` starts with the flag itself.
    """
    if argv[0] != "find" and argv[0] not in _EXEC_FLAGS:
        return
    index = 0
    while index < len(argv):
        if argv[index] not in _EXEC_FLAGS:
            index += 1
            continue
        end = index + 1
        while end < len(argv) and argv[end] != _EXEC_END:
            end += 1
        yield list(argv[index + 1 : end])
        index = end


def _inner(argv: Argv) -> Iterator[Argv]:
    inner: list[list[str]] = []
    if argv[0] in _WRAPPERS:
        inner.append(_unwrap(argv))
    inner.extend(_exec_clauses(argv))
    for words in inner:
        if words:
            yield _with_basename(words)


def _expand(argv: Argv) -> Iterator[Argv]:
    yield argv
    for inner in _inner(argv):
        yield from _expand(inner)


def simple_commands(cmd: str) -> list[Argv]:
    r"""Return the argv of every simple command in `cmd`, wrappers and ``find -exec`` unwrapped.

    The scan is purely lexical and never runs a shell. Placeholders count as their names,
    ``\\<newline>`` joins lines and any other newline separates commands. Leading ``VAR=value``
    assignments and redirections are dropped and ``argv[0]`` is reduced to its basename.
    Commands inside quoted strings (``sh -c 'rm x'``), backticks, functions and aliases are not
    seen.

    Args:
        cmd: Command or script text.

    Returns:
        The argv tuples in order of appearance; an unwrapped command follows its wrapper.

    Raises:
        ValueError: If `cmd` has an unbalanced quote or a trailing escape.
    """
    argvs: list[Argv] = []
    for words in _split_commands(_tokenize(cmd)):
        words = _strip_assignments(words)
        if words:
            argvs.extend(_expand(_with_basename(words)))
    return argvs


def _first_argument(args: Argv) -> str | None:
    return next((arg for arg in args if not arg.startswith("-")), None)


def _always(_args: Argv) -> bool:
    return True


def _dd(args: Argv) -> bool:
    return any(arg.startswith("of=") for arg in args)


def _find(args: Argv) -> bool:
    return "-delete" in args


def _rsync(args: Argv) -> bool:
    return any(arg.startswith("--del") for arg in args)


def _git_subcommand(args: Argv) -> tuple[str | None, Argv]:
    """Return the git subcommand and the arguments after it, skipping global options."""
    index = 0
    while index < len(args) and args[index].startswith("-"):
        index += 2 if args[index] in _GIT_OPTIONS_WITH_ARGUMENT else 1
    if index >= len(args):
        return None, ()
    return args[index], args[index + 1 :]


def _has_short_flag(args: Argv, letter: str) -> bool:
    return any(arg.startswith("-") and not arg.startswith("--") and letter in arg for arg in args)


def _git_clean(rest: Argv) -> bool:
    return "--force" in rest or _has_short_flag(rest, "f")


def _git_push(rest: Argv) -> bool:
    # A refspec starting with `+` (`git push origin +main`) forces that ref.
    return "-f" in rest or any(arg.startswith(("--force", "+")) for arg in rest)


def _git_stash(rest: Argv) -> bool:
    return bool(rest) and rest[0] in {"drop", "clear"}


_GIT_RULES: Final[Mapping[str, Callable[[Argv], bool]]] = {
    "reset": lambda rest: "--hard" in rest,
    "clean": _git_clean,
    "push": _git_push,
    "branch": lambda rest: "-D" in rest,
    "stash": _git_stash,
}


def _git(args: Argv) -> bool:
    subcommand, rest = _git_subcommand(args)
    rule = _GIT_RULES.get(subcommand or "")
    return rule is not None and rule(rest)


def _diskutil(args: Argv) -> bool:
    return any(arg.casefold() in _DISKUTIL_DESTRUCTIVE for arg in args)


def _defaults(args: Argv) -> bool:
    return _first_argument(args) == "delete"


def _crontab(args: Argv) -> bool:
    return "-r" in args


def _tmutil(args: Argv) -> bool:
    return (_first_argument(args) or "").startswith("delete")


def _security(args: Argv) -> bool:
    return (_first_argument(args) or "").startswith("delete-")


def _dscl(args: Argv) -> bool:
    return "-delete" in args


_RULES: Final[Mapping[str, Callable[[Argv], bool]]] = {
    "rm": _always,
    "unlink": _always,
    "dd": _dd,
    "find": _find,
    "rsync": _rsync,
    "git": _git,
    "diskutil": _diskutil,
    "defaults": _defaults,
    "crontab": _crontab,
    "tmutil": _tmutil,
    "security": _security,
    "dscl": _dscl,
}


def _matches_rule(argv: Argv) -> bool:
    program, args = argv[0], argv[1:]
    if program.startswith("newfs"):
        return True
    if program.startswith("-"):
        # The rest of a `find` after an escaped `;` (`find . -exec ls {} \; -delete`).
        return _find(argv)
    rule = _RULES.get(program)
    return rule is not None and rule(args)


def is_destructive(cmd: str) -> bool:
    """Tell whether any command in `cmd` matches a D-016 destructive pattern (D-030).

    Args:
        cmd: Command text, possibly with ``{{placeholders}}``.

    Returns:
        True when a simple command (also inside a wrapper or ``find -exec``) deletes, erases,
        overwrites or force-pushes; quoted text and arguments of ``man`` or ``echo`` do not count.

    Raises:
        ValueError: If `cmd` cannot be split into words.
    """
    return any(_matches_rule(argv) for argv in simple_commands(cmd))
