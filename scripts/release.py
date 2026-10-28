#!/usr/bin/env python3
"""Local release step for check_cep (spec 024, contracts/release-and-publish.md).

  release.py prepare [VERSION] [--dry-run] [--yes]
      Date the CHANGES.md heading, write VERSION, stamp CEP_VERSION into
      src/check_cep, commit `chore(release): VERSION` and create the
      annotated tag VERSION. Prints the push command; never pushes.
  release.py notes VERSION
      Print the CHANGES.md section of VERSION (GitHub release body).
  release.py aliases VERSION
      Print the image tags a publish of VERSION may set.

Only local git commands are run (no push/fetch/pull/ls-remote).
"""
import argparse
import datetime
import os
import re
import subprocess
import sys

# SemVer numeric identifiers: no leading zeros (0.01.0 is not a version).
_NUM = r"(0|[1-9]\d*)"
RELEASE_RE = re.compile(rf"^{_NUM}\.{_NUM}\.{_NUM}(?:-rc\.{_NUM})?$")
FINAL_RE = re.compile(rf"^{_NUM}\.{_NUM}\.{_NUM}$")
CEP_VERSION_RE = re.compile(r'^CEP_VERSION = ".*"$', re.MULTILINE)
SPEC_HEADING_RE = re.compile(r"^## Spec (\d+) — (.+)$", re.MULTILINE)

CHANGES = "CHANGES.md"
VERSION_FILE = "VERSION"
PLUGIN = "src/check_cep"
VERSIONS_ENV = "src/container/versions.env"
RELEASE_BRANCH = "main"


class ReleaseError(Exception):
    """A precondition failed; nothing has been changed."""


def git(*args, check=True):
    proc = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def semver_key(version):
    """Sort key per SemVer 2.0.0 for X.Y.Z[-rc.N]: an rc sorts before its final."""
    m = RELEASE_RE.match(version)
    if not m:
        raise ReleaseError(f"invalid version {version!r} (expected X.Y.Z or X.Y.Z-rc.N)")
    major, minor, patch, rc = m.groups()
    if rc is None:
        return (int(major), int(minor), int(patch), 1, 0)
    return (int(major), int(minor), int(patch), 0, int(rc))


def read(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            return f.read()
    except OSError as exc:
        raise ReleaseError(f"{rel}: cannot read ({exc.strerror})") from None


def write(root, rel, text):
    with open(os.path.join(root, rel), "w", encoding="utf-8") as f:
        f.write(text)


def repo_root():
    proc = git("rev-parse", "--show-toplevel", check=False)
    if proc.returncode != 0:
        raise ReleaseError("not inside a git repository")
    return proc.stdout.strip()


def tag_exists(tag):
    return git("rev-parse", "-q", "--verify", f"refs/tags/{tag}", check=False).returncode == 0


def current_version(root):
    version = read(root, VERSION_FILE).strip()
    if not version:
        raise ReleaseError(f"{VERSION_FILE} is empty")
    if not RELEASE_RE.match(version):
        raise ReleaseError(f"{VERSION_FILE} contains an invalid version {version!r}")
    return version


def propose_version(changes, current):
    """0.<NNN>.0 from the newest `## Spec NNN —` chapter that has no version yet."""
    specs = [int(n) for n, _ in SPEC_HEADING_RE.findall(changes)]
    if specs:
        proposal = f"0.{max(specs)}.0"
        if semver_key(proposal) > semver_key(current):
            return proposal
    raise ReleaseError(f"no unreleased '## Spec NNN —' chapter in {CHANGES}; pass the version explicitly")


def find_heading(changes, version):
    """Return (old heading line, new heading line without the date) for VERSION.

    Accepted, in this order:
      `## VERSION — Unreleased — Title`
      `## Spec NNN — Title` with NNN == minor, for X.Y.0 and its rcs
      `## X.Y.0-rc.N — <date> — Spec NNN — Title` (newest rc), for a final X.Y.0
    """
    m = re.search(rf"^## {re.escape(version)} — Unreleased — (.+)$", changes, re.MULTILINE)
    if m:
        return m.group(0), f"## {version} — {{date}} — {m.group(1)}"
    major, minor, patch, rc = RELEASE_RE.match(version).groups()
    if patch == "0":
        for m in SPEC_HEADING_RE.finditer(changes):
            if int(m.group(1)) == int(minor):
                return m.group(0), f"## {version} — {{date}} — Spec {m.group(1)} — {m.group(2)}"
        if rc is None:
            rc_re = re.compile(rf"^## ({major}\.{minor}\.0-rc\.\d+) — [^—]+ — (Spec \d+ — .+)$", re.MULTILINE)
            rcs = sorted(rc_re.finditer(changes), key=lambda m: semver_key(m.group(1)))
            if rcs:
                return rcs[-1].group(0), f"## {version} — {{date}} — {rcs[-1].group(2)}"
    raise ReleaseError(
        f"{CHANGES}: no chapter for {version} "
        f"(expected '## {version} — Unreleased — …' or '## Spec {int(minor):03d} — …')"
    )


def prepare(args):
    root = repo_root()
    os.chdir(root)
    changes = read(root, CHANGES)
    current = current_version(root)

    version = args.version
    if version is None:
        version = propose_version(changes, current)
        print(f"proposed version: {version}")
        if not (args.yes or args.dry_run):
            raise ReleaseError(f"re-run with --yes to release {version}, or pass the version explicitly")

    if not RELEASE_RE.match(version):
        raise ReleaseError(f"invalid version {version!r} (expected X.Y.Z or X.Y.Z-rc.N, no 'v' prefix)")
    branch = git("symbolic-ref", "--quiet", "--short", "HEAD", check=False).stdout.strip()
    if branch != RELEASE_BRANCH:
        raise ReleaseError(f"releases are cut on {RELEASE_BRANCH!r}, current branch is {branch or 'detached HEAD'!r}")
    if git("status", "--porcelain").stdout.strip():
        raise ReleaseError("working tree is not clean (commit or stash first)")
    if semver_key(version) <= semver_key(current):
        raise ReleaseError(f"{version} is not greater than the current version {current}")
    if tag_exists(version):
        raise ReleaseError(f"tag {version} already exists")
    old_heading, new_heading = find_heading(changes, version)
    plugin = read(root, PLUGIN)
    stamps = len(CEP_VERSION_RE.findall(plugin))
    if stamps != 1:
        raise ReleaseError(f'{PLUGIN}: expected exactly one CEP_VERSION = "..." line, found {stamps}')

    new_heading = new_heading.format(date=datetime.date.today().isoformat())
    print(f"{CHANGES}: {old_heading}")
    print(f"{' ' * len(CHANGES)}  → {new_heading}")
    print(f"{VERSION_FILE}: {current} → {version}")
    print(f'{PLUGIN}: CEP_VERSION = "{version}"')
    print(f"commit: chore(release): {version}; annotated tag: {version}")
    if args.dry_run:
        print("dry run: nothing changed")
        return 0

    # The tree was clean (checked above), so a failure in any step below is
    # undone by resetting to the previous HEAD: no commit without its tag.
    previous_head = git("rev-parse", "HEAD").stdout.strip()
    write(root, CHANGES, changes.replace(old_heading, new_heading, 1))
    write(root, VERSION_FILE, f"{version}\n")
    write(root, PLUGIN, CEP_VERSION_RE.sub(f'CEP_VERSION = "{version}"', plugin))
    try:
        git("add", "--", CHANGES, VERSION_FILE, PLUGIN)
        git("commit", "-q", "-m", f"chore(release): {version}")
        git("tag", "-a", version, "-m", f"check_cep {version}")
    except ReleaseError:
        git("reset", "-q", "--hard", previous_head, check=False)
        raise
    print(f"released {version} locally; publish with:")
    print(f"  git push origin {RELEASE_BRANCH} {version}")
    return 0


def notes(args):
    root = repo_root()
    lines = read(root, CHANGES).splitlines()
    prefix = f"## {args.version} — "
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith(prefix))
    except StopIteration:
        raise ReleaseError(f"{CHANGES}: no section '{prefix}…'") from None
    body = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        body.append(line)
    while body and body[-1].strip() in ("", "---"):
        body.pop()
    while body and not body[0].strip():
        body.pop(0)
    print("\n".join(body))
    return 0


def playwright_version(root):
    for line in read(root, VERSIONS_ENV).splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key == "PLAYWRIGHT_VERSION" and value:
            return value
    raise ReleaseError(f"{VERSIONS_ENV}: PLAYWRIGHT_VERSION missing")


def aliases(args):
    version = args.version
    if not RELEASE_RE.match(version):
        raise ReleaseError(f"invalid version {version!r}")
    root = repo_root()
    if not tag_exists(version):
        raise ReleaseError(f"{version} is not a local git tag")
    tags = [version, f"{version}-pw{playwright_version(root)}"]
    if FINAL_RE.match(version):
        finals = [t for t in git("tag", "--list").stdout.split() if FINAL_RE.match(t)]
        key = semver_key(version)
        minor = version.rsplit(".", 1)[0]
        same_minor = [t for t in finals if t.rsplit(".", 1)[0] == minor]
        if all(semver_key(t) <= key for t in same_minor):
            tags.append(minor)
        if all(semver_key(t) <= key for t in finals):
            tags.append("latest")
    print("\n".join(tags))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="check_cep release tooling (local only, never pushes)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="release commit + annotated tag")
    p.add_argument("version", nargs="?", help="X.Y.Z or X.Y.Z-rc.N (default: proposed from CHANGES.md)")
    p.add_argument("--dry-run", action="store_true", help="run all checks, print the planned edits")
    p.add_argument("--yes", action="store_true", help="accept the proposed version")
    p.set_defaults(func=prepare)
    p = sub.add_parser("notes", help="print the CHANGES.md section of a version")
    p.add_argument("version")
    p.set_defaults(func=notes)
    p = sub.add_parser("aliases", help="print the image tags a publish of a version may set")
    p.add_argument("version")
    p.set_defaults(func=aliases)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ReleaseError as exc:
        print(f"release.py: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
