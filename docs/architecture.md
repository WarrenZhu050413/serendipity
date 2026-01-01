# Architecture

## Data Flow

```
User Input
    │
    ▼
┌─────────────────┐
│  settings.yaml  │  ← Single source of truth
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   TypesConfig   │  ← Parsed into typed dataclasses (config/types.py)
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐  ┌──────────────┐
│Context│  │PromptBuilder │  ← Compiles config into agent prompts
│Sources│  └──────┬───────┘
└───┬───┘         │
    │             ▼
    │      ┌─────────────┐
    └─────►│   Agent     │  ← Claude with tools (WebSearch, MCP, etc.)
           └──────┬──────┘
                  │
                  ▼
           ┌─────────────┐
           │   Parser    │  ← Extracts JSON from <recommendations> tags
           └──────┬──────┘
                  │
                  ▼
           ┌─────────────┐
           │  Renderers  │  ← HTML, Markdown, JSON output
           └──────┬──────┘
                  │
                  ▼
           ┌─────────────┐
           │Destinations │  ← Browser, stdout, file, webhook, etc.
           └─────────────┘
```

## Key Files

| File | Purpose |
|------|---------|
| `config/types.py` | Dataclass definitions (`TypesConfig`, `MediaType`, `ApproachType`, etc.) |
| `config/defaults/settings.yaml` | Default configuration, copied to user on init |
| `prompts/builder.py` | Compiles TypesConfig into agent prompt sections |
| `agent.py` | Discovery agent, parsing, rendering |
| `models.py` | Output models (`Recommendation`, `Pairing`) |
| `settings.py` | Programmatic config updates (`add_media`, `add_pairing`, etc.) |
| `storage.py` | File operations, profile management |
| `cli.py` | Typer CLI commands |

## Extension Points

The system has five extension points, all configured via `settings.yaml`:

| Extension | What it Controls | Dataclass |
|-----------|-----------------|-----------|
| **Approaches** | Discovery strategies (convergent, divergent) | `ApproachType` |
| **Media** | Content formats (article, youtube, book) | `MediaType` |
| **Context Sources** | User profile data (taste.md, history, MCP) | `ContextSourceConfig` |
| **Pairings** | Bonus content (music, food, tips) | `PairingType` |
| **Destinations** | Output targets (browser, file, webhook) | `DestinationConfig` |

See [extending-settings.md](extending-settings.md) for how to add new types.

## Context Source Types

| Type | How it Works |
|------|--------------|
| `loader` | Python function returns content string |
| `command` | Shell command stdout as content |
| `mcp` | MCP server provides tools for Claude |

## Template Variables

Available in all config string values:

| Variable | Example |
|----------|---------|
| `{profile_dir}` | `~/.serendipity` |
| `{profile_name}` | `default` |
| `{home}` | `/Users/warren` |
| `{query}` | User's search input (in source hints) |

## Profiles

Profiles are independent configurations stored in `~/.serendipity/profiles/{name}/`:

```
~/.serendipity/
  profiles.yaml          # Active profile registry
  profiles/
    default/
      settings.yaml      # This profile's config
      taste.md           # Aesthetic preferences
      learnings.md       # Extracted feedback patterns
      history.jsonl      # Recommendation history
```

Switch with `serendipity profile use <name>` or `SERENDIPITY_PROFILE=name`.
