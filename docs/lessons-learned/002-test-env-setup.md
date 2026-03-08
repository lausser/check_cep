# Lessons Learned: 002-test-env-setup

**Branch**: `002-test-env-setup` | **Date**: 2026-03-06

---

## 1. Read the actual code — documented findings can be incomplete

**What happened**: The spec (research item 14) documented three `if args.result_dest == "local"` guards to remove. The code had four. The fourth (the `test-meta.json` read at ~line 1188) was equally broken and needed the same fix, but was missed in the analysis phase.

**Rule**: When a finding says "N occurrences of pattern X", always do a grep before touching the code. The grep is the source of truth, not the prose.

---

## 2. Overloaded context causes drift — start fresh with the plan

**What happened**: After a long spec-writing session, attempting to implement inside the same conversation led to a cluttered, unfocused start. Restarting with only `plan.md` and `tasks.md` produced a clean, focused implementation with no wasted turns.

**Rule**: For implementation tasks, start a new session and read only the plan and tasks. The spec artifacts exist precisely so the implementation session does not need the full design history.

---

## 3. Serena must be activated for the right project

**What happened**: Serena was active on `labs-migration` (a different repo) at session start. All `read_file` and `search_for_pattern` calls silently operated on the wrong project until `activate_project` was called.

**Rule**: At the start of any session that uses Serena, call `get_current_config` and verify the active project matches the working directory before using any file tools.

---

## 4. Serena's `replace_content` has path safety restrictions

**What happened**: Attempting to use `replace_content` on a file under `specs/` raised "Path is ignored; cannot access for safety reasons". The same operation on `src/` files worked fine.

**Rule**: Serena's `replace_content` respects ignore rules that may exclude documentation directories. Use shell `sed` as a fallback for files Serena refuses to touch.

---

## 5. Serena's `replace_content` mode values

**What happened**: Calling `replace_content` with `mode="replace_first"` raised a validation error. The tool only accepts `mode="literal"` or `mode="regex"`.

**Rule**: `mcp__serena__replace_content` mode is `literal` (exact string) or `regex` (pattern). There is no `replace_first`; literal mode already replaces only the first occurrence.

---

## 6. Edit tool requires Read tool — not Serena's read_file

**What happened**: After reading a file with `mcp__serena__read_file`, the Edit tool refused to run with "File has not been read yet". The Edit tool tracks reads done via its own `Read` tool only.

**Rule**: Before using `Edit`, always issue a `Read` call (the built-in tool). Serena's `read_file` does not satisfy the Edit tool's prerequisite check.

---

## 7. argparse uses the last occurrence of a repeated flag

**What happened**: `run_check_cep()` hardcodes `--host-name testhost --service-description pytest_test`. Tests that need different values pass them again in `extra_args`. argparse resolves duplicate `store`-action flags to the last value, so the extra_args effectively override the defaults.

**Rule**: This is a valid and useful pattern for wrapper functions with hardcoded defaults. Document it with a comment so future readers do not think it is an error.

---

## 8. pytest fixture returning a callable is the right pattern for injectable helpers

**What happened**: `write_playwright_config` needed to be callable from tests across multiple conftest scopes. Making it a module-level function required explicit imports; making it a fixture that returns a callable let pytest inject it naturally.

**Rule**: When a conftest-defined helper needs to cross package boundaries inside a pytest suite, wrap it in a fixture that returns the function. Tests inject it as a parameter without any import statement.

---

## 9. Remove unused imports immediately

**What happened**: `import io` was added to `tests/integration/conftest.py` in anticipation of in-memory tarfile creation. The implementation ended up using a file-path approach, leaving the import unused. It was only caught during a final review pass.

**Rule**: When you change implementation approach mid-way, immediately re-check every import you added for that approach and remove the ones that are no longer needed.

---

## 10. `importlib.util.spec_from_file_location` returns None for extension-less scripts

**What happened**: `src/check_cep` is a Python script without a `.py` extension. `spec_from_file_location` determines the loader from the file extension; with no extension it returns `None`, causing `module_from_spec(None)` to raise `AttributeError`.

**Fix**: Pass the loader explicitly:
```python
import importlib.machinery
_loader = importlib.machinery.SourceFileLoader("check_cep_mod", str(path))
_spec = importlib.util.spec_from_file_location("check_cep_mod", str(path), loader=_loader)
```

**Rule**: When using `importlib` to load a Python file that lacks a `.py` extension, always supply a `SourceFileLoader` explicitly. Never rely on extension-based loader detection for non-standard filenames.

---

## 11. Clarify "testing the software" vs. "software that does testing"

**What happened**: check_cep's purpose is to run E2E browser tests. Its own integration test suite is therefore a test-of-tests setup. The TUTORIAL.md section about running the test suite needed an explicit scope callout to prevent readers from confusing "testing check_cep" with "using check_cep to test websites".

**Rule**: When the product under test is itself a testing tool, documentation for its own test suite must open with an explicit scope clarification. Otherwise readers conflate the two levels.
