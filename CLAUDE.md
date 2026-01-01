## CLI Design Principles

The serendipity CLI follows these design principles:

### 1. Settings-to-CLI Flag Parity
Every top-level setting in `settings.yaml` MUST have a corresponding CLI flag in `serendipity discover`:

| Setting | CLI Flag |
|---------|----------|
| `model` | `--model, -m` |
| `total_count` | `--count, -n` |
| `feedback_server_port` | `--port` |
| `thinking_tokens` | `--thinking, -t` |

When adding a new setting, always add the corresponding CLI flag.

### 2. CLI Flags Override Settings
CLI flags take precedence over settings.yaml values. Pattern:
```python
value = cli_flag if cli_flag is not None else settings.value
```

### 3. Single Source of Truth
All configuration lives in `~/.serendipity/settings.yaml`. No scattered config files.

### 4. Generic Commands for Dynamic Data
Don't hardcode subcommands for data defined in config. Use generic commands that route based on config:
```
serendipity profile manage <source_name>   # Routes to handler based on source type
serendipity settings get <path>         # Hierarchical dotted path access
```

### 5. Source Editability Rules
Only file-based loader sources are editable. Check with:
- `type == "loader"` AND
- `loader == "serendipity.context_sources.builtins.file_loader"` AND
- Has `options.path`

MCP sources and dynamic loaders (style_guidance) are read-only.

### 6. Input Priority Waterfall
For context input in discover command:
1. Explicit file argument
2. `-p` flag (clipboard)
3. `-i` flag (editor)
4. Stdin (if piped)
5. None → "surprise me" mode

### 7. Interactive Wizard Pattern
Commands that need guided setup support `-i/--interactive` flag for step-by-step wizards.

### 8. Hierarchical Settings Access
Settings support dotted paths for granular access:
```
serendipity settings get approaches.convergent
serendipity settings edit media.youtube
```

---

## GitHub Issues Workflow

GitHub Issues is the **single source of truth** for tracking bugs, features, and improvements. It serves as persistent memory across sessions and a first place to check when problems arise.

### Core Principle

**Every identified problem or feature MUST have a GitHub issue.** Before starting any work, check if an issue already exists. If not, create one.

### Workflow

#### 1. Identify & Create Issue

When you identify a bug, new feature, or improvement:

```bash
# Check existing issues first
gh issue list
gh issue list --state all | grep -i "keyword"

# Create new issue if none exists
gh issue create --title "Short description" --label "bug,size:small" --body "..."
```

**Issue body contains:**

- Description of the problem/feature
- Current behavior (for bugs)
- Expected/desired behavior
- Relevant context (files, screenshots, error messages)

**Issue body does NOT contain:**

- The fix or implementation plan (that goes in comments)

#### 2. Plan in Comments

Add the fix/implementation plan as **comments** on the issue:

```bash
gh issue comment 123 --body "## Plan
1. Update X in file Y
2. Add tests for Z
3. ..."
```

Multiple comments are fine as the plan evolves.

#### 3. Implement & Test

- Write tests that verify the fix/feature
- Implement the solution
- Ensure `bun run build` passes

#### 4. Commit & Close

**IMPORTANT: Always commit BEFORE closing the issue.** Never close an issue without first committing the related changes.

Commit with issue reference:

```bash
git commit -m "Short description

- Detail 1
- Detail 2
- Tests: src/path/to/test.ts

Fixes #123"
```

Then close with a summary comment:

```bash
gh issue comment 123 --body "Fixed in commit abc1234. Tests added in src/path/to/test.ts"
# Issue auto-closes from "Fixes #123" in commit message
```

### Size Labels

- `size:small` - Quick fixes, renames, single-file changes
- `size:medium` - Multi-file features, moderate refactors
- `size:large` - Architectural changes, major features

### Quick Reference

```bash
gh issue list                         # Open issues
gh issue list --state all             # All issues (check for regressions)
gh issue view 123                     # Read issue details
gh issue comment 123 --body "..."     # Add plan/update
gh issue close 123                    # Close manually
gh issue reopen 123                   # Reopen if regression found
```

### When to Check Issues First

- Before starting new work → existing issue?
- When encountering a bug → was it reported before?
- When something regresses → find the original fix

---

## Testing

Tests use pytest with pytest-xdist for parallel execution (4 workers by default).

### Running Tests

```bash
# Default: fast unit tests only (excludes e2e)
uv run pytest

# Run specific file
uv run pytest tests/test_cli.py

# Single worker (for debugging)
uv run pytest -n 0

# Include end-to-end tests (hits real APIs, slow)
uv run pytest -m e2e

# Run everything including e2e
uv run pytest -m ""
```

### Test Categories

| Marker | Description | When to Run |
|--------|-------------|-------------|
| (none) | Unit tests with mocks | Always (default) |
| `e2e` | Real API calls, slow | Before releases, major changes |

### Writing Tests

**Unit tests** (default): Mock external dependencies like `SerendipityAgent`, `ContextSourceManager`, API calls. These run in <2 seconds total.

**E2E tests** (`@pytest.mark.e2e`): Real API calls, real file I/O. Put in `tests/test_e2e.py`. These are skipped by default.

```python
# Unit test pattern
def test_something(self):
    with patch("serendipity.cli.SerendipityAgent") as mock:
        mock.return_value.run_sync.return_value = mock_result
        # ... test logic

# E2E test pattern
@pytest.mark.e2e
def test_real_discover(self):
    # No mocks - hits real Claude API
    result = runner.invoke(app, ["discover", "test prompt", "-o", "json"])
```

### Common Fixtures

Defined in `tests/conftest.py`:
- `temp_dir` - Temporary directory
- `temp_storage` - StorageManager with temp dir
- `temp_storage_with_taste` - StorageManager with taste profile

---

## Icon System

Icons are auto-discovered from `serendipity/static/icons/`. **Single source of truth**: the SVG files.

### Adding a New Icon

1. Download SVG from [lucide.dev](https://lucide.dev/icons/)
2. Save to `serendipity/static/icons/<name>.svg`
3. Use in settings: `icon: "<name>"`

That's it. No code changes needed.
