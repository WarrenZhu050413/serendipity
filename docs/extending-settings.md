# Extending Settings

How to add new configuration types to serendipity. See [architecture.md](architecture.md) for system overview.

## Media Type Best Practices

### Search Hints with `{query}`

The `{query}` placeholder gets replaced with Claude's generated search terms based on user context:

```yaml
sources:
  - tool: WebSearch
    hints: "site:letterboxd.com {query} film"
```

If the user says "I'm in a contemplative mood", Claude might search:
`site:letterboxd.com slow cinema meditative film`

### Site-Specific Searches

Use `site:` operator to target quality sources:

| Media Type | Good Sites |
|------------|------------|
| Music | `spotify.com`, `bandcamp.com` |
| Films | `letterboxd.com` |
| Books | `goodreads.com` |
| Art | `artsandculture.google.com` |
| Architecture | `archdaily.com` |
| Podcasts | Generic search (no reliable single source) |

**Note:** Some sites block Anthropic's crawler (e.g., YouTube). Test with `serendipity search --site youtube.com` before adding.

### Multiple Sources

Combine multiple search sources for better coverage:

```yaml
music:
  sources:
    - tool: WebSearch
      hints: "site:spotify.com {query} album OR playlist"
    - tool: WebSearch
      hints: "site:bandcamp.com {query}"
```

### Metadata Schema

Define what Claude should extract for each recommendation:

```yaml
metadata_schema:
  - name: director
    required: true   # Must include
  - name: year
    required: true
  - name: runtime
    required: false  # Nice to have
```

## Pairing Types

### Search-Based vs Generated

- **`search_based: true`**: Claude uses WebSearch to find real links (recipes, places, games)
- **`search_based: false`**: Claude generates text directly (quotes, tips, prompts)

```yaml
# Search-based: finds actual recipes
drink:
  search_based: true
  prompt_hint: "Search for cocktail or beverage recipes."

# Generated: Claude creates the content
journal:
  search_based: false
  prompt_hint: "A reflective writing prompt."
```

---

## Adding via CLI

```bash
# Media types
serendipity settings add media -n papers -d "Academic Papers"
serendipity settings add media -i  # interactive wizard

# Approaches
serendipity settings add approach -n serendipitous -d "Pure Luck"

# Context sources
serendipity settings add source -n notes -t loader --path "~/notes.md"
serendipity settings add source -n custom -t mcp

# Pairings
serendipity settings add pairing -n quote -d "Reflect" --icon "📜"
serendipity settings add pairing -n drink -s  # -s = search-based
```

## Adding via YAML

Edit `~/.serendipity/settings.yaml` directly:

```yaml
# New approach
approaches:
  serendipitous:
    display_name: "Pure Luck"
    enabled: true
    prompt_hint: |
      Ignore stated preferences. Embrace chaos.

# New media type
media:
  papers:
    display_name: "Academic Papers"
    enabled: true
    sources:
      - tool: WebSearch
        hints: "site:arxiv.org {query}"
    prompt_hint: "Focus on recent papers."
    metadata_schema:
      - name: author
        required: true
      - name: year
        required: false

# New pairing
pairings:
  quote:
    display_name: "Reflect"
    enabled: true
    search_based: false
    icon: "📜"
    prompt_hint: "Share a relevant quote with attribution."

# New context source (loader)
context_sources:
  notes:
    type: loader
    enabled: true
    loader: serendipity.context_sources.builtins.file_loader
    prompt_hint: |
      <notes>{content}</notes>
    options:
      path: "~/notes.md"

  # Shell command source
  clipboard:
    type: command
    command: "pbpaste | head -100"
    prompt_hint: |
      <clipboard>{content}</clipboard>
```

## Adding a New Extension Type (Developer)

For adding an entirely new category (like pairings was added):

1. **Dataclass** in `config/types.py` with `from_dict` classmethod
2. **Field** in `TypesConfig` with `get_enabled_*()` method
3. **Defaults** in `config/defaults/settings.yaml`
4. **Prompt section** in `prompts/builder.py`
5. **Output model** in `models.py` (if needed)
6. **Parsing** in `agent.py` `_parse_response()`
7. **Rendering** in `agent.py` (HTML, markdown, JSON)
8. **Settings function** in `settings.py` (`add_*`)
9. **CLI support** in `cli.py` (non-interactive + wizard)
10. **Tests** in `tests/test_settings.py`

Pattern to follow: Look at `PairingType` implementation across these files.

## Custom Loaders

Create Python loaders in your profile's `loaders/` directory:

```python
# ~/.serendipity/loaders/notion.py
def load(storage, options):
    """Return (content: str, warnings: list[str])"""
    api_key = options.get("api_key")
    # ... fetch from Notion
    return content, []
```

Reference in settings.yaml:
```yaml
context_sources:
  notion:
    type: loader
    loader: notion.load  # finds in profile loaders/
    options:
      api_key: "secret_xxx"
```
