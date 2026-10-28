#!/usr/bin/env python3
"""Check that every version source agrees (spec 024 FR-014, contracts R-3).

- src/container/versions.env PLAYWRIGHT_VERSION is the single Playwright
  source; src/container/package.json must pin @playwright/test to exactly
  that version and src/container/package-lock.json must resolve to it.
- VERSION must equal the CEP_VERSION stamped into src/check_cep.

Prints one line per conflict, `<file>: <found> (expected <value> from <source>)`,
and exits 1; exits 0 when everything is consistent.
"""
import argparse
import json
import os
import re
import sys

ENV_FILE = "src/container/versions.env"
PACKAGE_JSON = "src/container/package.json"
PACKAGE_LOCK = "src/container/package-lock.json"
VERSION_FILE = "VERSION"
PLUGIN = "src/check_cep"

EXACT_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
CEP_VERSION_RE = re.compile(r'^CEP_VERSION = "(.*)"$', re.MULTILINE)


class SourceError(Exception):
    """A version source is missing or unreadable; the message names the file."""


def read_text(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            return f.read()
    except OSError as exc:
        raise SourceError(f"{rel}: cannot read ({exc.strerror})") from None


def read_json(root, rel):
    try:
        return json.loads(read_text(root, rel))
    except ValueError as exc:
        raise SourceError(f"{rel}: invalid JSON ({exc})") from None


def env_playwright_version(root):
    for line in read_text(root, ENV_FILE).splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key == "PLAYWRIGHT_VERSION" and value:
            return value
    raise SourceError(f"{ENV_FILE}: PLAYWRIGHT_VERSION missing")


def package_json_version(root):
    data = read_json(root, PACKAGE_JSON)
    try:
        return data["dependencies"]["@playwright/test"]
    except (KeyError, TypeError):
        raise SourceError(f"{PACKAGE_JSON}: no @playwright/test dependency") from None


def package_lock_version(root):
    data = read_json(root, PACKAGE_LOCK)
    try:
        return data["packages"]["node_modules/@playwright/test"]["version"]
    except (KeyError, TypeError):
        raise SourceError(f"{PACKAGE_LOCK}: no node_modules/@playwright/test entry") from None


def release_version(root):
    version = read_text(root, VERSION_FILE).strip()
    if not version:
        raise SourceError(f"{VERSION_FILE}: empty")
    return version


def stamped_version(root):
    stamps = CEP_VERSION_RE.findall(read_text(root, PLUGIN))
    if len(stamps) != 1:
        raise SourceError(f'{PLUGIN}: expected exactly one CEP_VERSION = "..." line, found {len(stamps)}')
    return stamps[0]


def check(root):
    """Return the list of conflict lines (empty when consistent)."""
    problems = []

    try:
        playwright = env_playwright_version(root)
    except SourceError as exc:
        problems.append(str(exc))
        playwright = None
    for rel, reader in ((PACKAGE_JSON, package_json_version), (PACKAGE_LOCK, package_lock_version)):
        try:
            found = reader(root)
        except SourceError as exc:
            problems.append(str(exc))
            continue
        if playwright is None:
            continue
        if rel == PACKAGE_JSON and not EXACT_VERSION_RE.match(found):
            problems.append(f"{rel}: {found} (expected exact {playwright} from {ENV_FILE})")
        elif found != playwright:
            problems.append(f"{rel}: {found} (expected {playwright} from {ENV_FILE})")

    try:
        version = release_version(root)
    except SourceError as exc:
        problems.append(str(exc))
        version = None
    try:
        stamped = stamped_version(root)
    except SourceError as exc:
        problems.append(str(exc))
        stamped = None
    if version is not None and stamped is not None and stamped != version:
        problems.append(f"{PLUGIN}: CEP_VERSION {stamped} (expected {version} from {VERSION_FILE})")

    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        help="repository root (default: the checkout containing this script)")
    args = parser.parse_args(argv)
    problems = check(args.root)
    for line in problems:
        print(line)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
