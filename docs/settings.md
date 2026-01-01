# Settings Reference

All configuration lives in `~/.serendipity/settings.yaml`. This is the single source of truth.

## CLI Commands

```bash
serendipity settings              # Show current settings
serendipity settings --edit       # Edit in $EDITOR
serendipity settings --reset      # Reset to defaults
serendipity settings get model    # Get specific value (dotted paths work)
```

## Top-Level Settings

```yaml
version: 2
model: opus                    # opus, sonnet, haiku
total_count: 10                # Number of recommendations
feedback_server_port: 9876     # Port for feedback UI
thinking_tokens: null          # Extended thinking (null=disabled, e.g., 10000)
```

CLI flags override these: `serendipity discover --model sonnet --count 5`

## Approaches

How to find content. Each approach gets its own section in output.

```yaml
approaches:
  convergent:
    display_name: "More Like This"
    enabled: true
    prompt_hint: |
      Match explicit interests. Quality over novelty.

  divergent:
    display_name: "Expand Your Palette"
    enabled: true
    prompt_hint: |
      Cross boundaries. Unexpected connections.
```

## Media

What format of content. Each can have sources and metadata schemas.

```yaml
media:
  article:
    display_name: "Articles & Essays"
    enabled: true
    sources:
      - tool: WebSearch
        hints: "{query} essay OR longread"
    prompt_hint: "Quality publications and blogs with voice."
    # preference: "my favorite format"  # optional nudge

  youtube:
    display_name: "YouTube Videos"
    enabled: true
    sources:
      - tool: WebSearch
        hints: "site:youtube.com {query}"
    metadata_schema:
      - name: channel
        required: true
      - name: duration
        required: true
```

## Context Sources

Where to get user profile data. Three types: `loader`, `command`, `mcp`.

```yaml
context_sources:
  # File loader
  taste:
    type: loader
    enabled: true
    loader: serendipity.context_sources.builtins.file_loader
    prompt_hint: |
      <taste>{content}</taste>
    options:
      path: "{profile_dir}/taste.md"

  # Shell command
  clipboard:
    type: command
    enabled: true
    command: "pbpaste | head -100"
    timeout: 30
    prompt_hint: |
      <clipboard>{content}</clipboard>

  # MCP server
  whorl:
    type: mcp
    enabled: false
    server:
      url: http://localhost:{port}/mcp/
    tools:
      allowed:
        - mcp__whorl__text_search_text_search_post
```

Enable/disable: `serendipity settings --enable-source whorl`

## Pairings

Contextual bonus content that accompanies recommendations.

```yaml
pairings_enabled: true  # master toggle

pairings:
  music:
    display_name: "Listen"
    enabled: true
    search_based: true   # true = WebSearch, false = generate
    icon: "🎵"
    prompt_hint: "Suggest a song that complements their mood."

  tip:
    display_name: "Try"
    enabled: true
    search_based: false
    icon: "💡"
    prompt_hint: "One small actionable insight."
```

## Output

Where and how to deliver results.

```yaml
output:
  default_format: html          # html, markdown, json
  default_destination: browser  # browser, stdout, file

  destinations:
    browser:
      type: builtin
      enabled: true

    gmail:
      type: command
      enabled: true
      command: "gmail send --to {to}"
      format: markdown

    slack:
      type: webhook
      enabled: false
      webhook_url: "${SLACK_WEBHOOK_URL}"
```

## Template Variables

Available in all string values:

| Variable | Expands To |
|----------|-----------|
| `{profile_dir}` | `~/.serendipity` |
| `{profile_name}` | `default` |
| `{home}` | `/Users/warren` |
| `{query}` | User's search input |

## Profiles

Manage separate configurations:

```bash
serendipity profile list              # Show all profiles
serendipity profile create work       # New profile
serendipity profile use work          # Switch
serendipity profile manage taste      # Edit taste.md
```

Or set via environment: `SERENDIPITY_PROFILE=work serendipity discover`
