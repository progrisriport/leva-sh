"""Tests for the content safety policy: command splitting, exec denylist, destructive rules."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from leva.content import EXEC_DENYLIST, is_destructive
from leva.content._policy import simple_commands

D016_TEXT = """
sudo su doas shutdown reboot halt diskutil hdiutil launchctl defaults pmset networksetup scutil
softwareupdate tmutil systemsetup kill killall pkill crontab ssh ssh-add ssh-agent scp sftp curl
ping traceroute dig nslookup host nc open osascript say screencapture pbcopy pbpaste security
xcode-select mdutil mdfind spctl dscl passwd login brew
"""
D016_DENYLIST = D016_TEXT.split()

TOKENIZATION_EXAMPLE = (
    'find . -exec rm {} \\; && sudo rm -rf "a b" 2>&1 | xargs -I {} rm {} > out $(rm x)'
)


def test_exec_denylist_is_the_d016_list() -> None:
    assert len(D016_DENYLIST) == 47
    assert frozenset(D016_DENYLIST) == EXEC_DENYLIST
    assert len(EXEC_DENYLIST) == 47


def test_simple_commands_handles_the_documented_example() -> None:
    argvs = simple_commands(TOKENIZATION_EXAMPLE)
    assert ("rm", "{}") in argvs
    assert ("sudo", "rm", "-rf", "a b") in argvs
    assert ("rm", "-rf", "a b") in argvs
    assert ("xargs", "-I", "{}", "rm", "{}") in argvs
    assert ("rm", "x") in argvs
    assert ("find", ".", "-exec", "rm", "{}") in argvs


def test_simple_commands_drops_leading_assignments() -> None:
    assert simple_commands("FOO=1 rm x") == [("rm", "x")]
    assert simple_commands("FOO=1 BAR=2") == []


def test_simple_commands_unwraps_env_options_and_assignments() -> None:
    assert ("rm", "x") in simple_commands("env -u X FOO=1 rm x")


def test_simple_commands_uses_basename() -> None:
    assert simple_commands("/bin/rm x") == [("rm", "x")]


def test_simple_commands_ignores_redirection_targets() -> None:
    assert simple_commands("echo hi > rm") == [("echo", "hi")]
    assert simple_commands("echo hi 2>&1") == [("echo", "hi")]
    assert simple_commands("cat 3<in") == [("cat",)]


def test_simple_commands_splits_on_separators() -> None:
    assert simple_commands("a x; b y && c z || d | e") == [
        ("a", "x"),
        ("b", "y"),
        ("c", "z"),
        ("d",),
        ("e",),
    ]


def test_simple_commands_joins_continuation_lines_and_splits_script_lines() -> None:
    assert simple_commands("tar -xzf a \\\n  -C d") == [("tar", "-xzf", "a", "-C", "d")]
    assert simple_commands("mkdir d\ncd d") == [("mkdir", "d"), ("cd", "d")]


def test_simple_commands_uses_plain_placeholders() -> None:
    assert simple_commands("rm {{file}}") == [("rm", "file")]


def test_simple_commands_unwraps_nested_wrappers() -> None:
    argvs = simple_commands("sudo -u root nice -n 5 xargs -n 1 rm")
    assert argvs == [
        ("sudo", "-u", "root", "nice", "-n", "5", "xargs", "-n", "1", "rm"),
        ("nice", "-n", "5", "xargs", "-n", "1", "rm"),
        ("xargs", "-n", "1", "rm"),
        ("rm",),
    ]


@pytest.mark.parametrize(
    "cmd",
    ["nohup " * 2000 + "rm x", "sudo " * 2000 + "rm x", "find . " + "-exec " * 2000 + "rm"],
    ids=["nohup", "sudo", "find-exec"],
)
def test_simple_commands_unwraps_chains_deeper_than_the_recursion_limit(cmd: str) -> None:
    argvs = simple_commands(cmd)
    assert len(argvs) == 2001
    assert argvs[-1][0] == "rm"
    assert is_destructive(cmd)


def test_simple_commands_wrapper_without_command() -> None:
    assert simple_commands("sudo -v") == [("sudo", "-v")]
    assert simple_commands("env") == [("env",)]


def test_simple_commands_find_exec_until_plus() -> None:
    argvs = simple_commands("find . -type f -exec rm {} + -print")
    assert ("rm", "{}") in argvs


def test_simple_commands_find_with_several_exec_clauses() -> None:
    argvs = simple_commands("find . -exec ls {} \\; -exec rm {} \\;")
    assert ("ls", "{}") in argvs
    assert ("rm", "{}") in argvs


def test_simple_commands_does_not_see_quoted_command_strings() -> None:
    assert simple_commands("sh -c 'rm x'") == [("sh", "-c", "rm x")]


def test_simple_commands_keeps_quoted_empty_word() -> None:
    assert simple_commands("rm '' x") == [("rm", "", "x")]
    assert simple_commands("echo '' curl") == [("echo", "", "curl")]


def test_simple_commands_keeps_hash_as_a_word() -> None:
    assert ("rm", "x") in simple_commands("echo a # b; rm x")


@pytest.mark.parametrize("cmd", ["a 'b", 'a "b', "a \\"])
def test_simple_commands_rejects_unbalanced_input(cmd: str) -> None:
    with pytest.raises(ValueError, match=r"quotation|escaped"):
        simple_commands(cmd)


@pytest.mark.parametrize(
    "cmd",
    [
        "rm x",
        "rm -rf {{dir}}",
        "unlink x",
        "dd if=a of=b",
        "find . -name x -delete",
        "rsync -a --delete a b",
        "rsync --del a b",
        "rsync --delete-after a b",
        "git reset --hard",
        "git -C repo reset --hard HEAD~1",
        "git -c user.name=x reset --hard",
        "git clean -f",
        "git clean -fd",
        "git clean -xdf",
        "git clean --force",
        "git push -f",
        "git push --force",
        "git push --force-with-lease origin main",
        "git push origin +main",
        "git push '' -f",
        "git branch -D old",
        "git stash drop",
        "git stash clear",
        "diskutil eraseDisk APFS x disk2",
        "diskutil ERASEVOLUME x y z",
        "diskutil secureErase 0 disk2",
        "newfs_apfs disk2",
        "newfs_hfs disk2",
        "defaults delete com.apple.dock",
        "crontab -r",
        "tmutil delete /Volumes/x",
        "tmutil deletelocalsnapshots 2020",
        "security delete-keychain x.keychain",
        "dscl . -delete /Users/x",
        "ls && rm x",
        "echo x | xargs rm",
        "sudo rm -rf x",
        "find . -exec rm {} \\;",
        "find . -name x -exec echo {} \\; -delete",
        "/bin/rm x",
    ],
)
def test_destructive_commands(cmd: str) -> None:
    assert is_destructive(cmd)


@pytest.mark.parametrize(
    "cmd",
    [
        "echo 'rm -rf /'",
        "man rm",
        "which rm",
        "echo rm",
        "grep -r rm .",
        "ls -lrt",
        "echo hi > rm",
        "dd if=x",
        "dd if=x bs=1m",
        "find . -name x",
        "find . -exec echo {} \\; -print",
        "rsync -a a b",
        "git reset --soft HEAD~1",
        "git reset",
        "git clean -n",
        "git push",
        "git push origin main",
        "git branch -d old",
        "git branch",
        "git stash list",
        "git stash",
        "git",
        "git -C",
        "diskutil list",
        "diskutil",
        "defaults read com.apple.dock",
        "defaults",
        "crontab -l",
        "tmutil listbackups",
        "tmutil",
        "security find-identity",
        "dscl . -read /Users/x",
        "tar -xzf {{archive}}",
        "FOO=1",
        "",
    ],
)
def test_non_destructive_commands(cmd: str) -> None:
    assert not is_destructive(cmd)


def test_is_destructive_rejects_unsplittable_command() -> None:
    with pytest.raises(ValueError, match="quotation"):
        is_destructive("rm 'x")


@given(st.text(max_size=60))
def test_simple_commands_total_up_to_value_error(cmd: str) -> None:
    try:
        argvs = simple_commands(cmd)
    except ValueError:
        return
    assert all(argv for argv in argvs)
