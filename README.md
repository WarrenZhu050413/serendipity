# Serendipity

A personal discovery engine that finds content you'll love. Claude searches the web based on your taste profile and serves recommendations back.

![Serendipity Interface](screenshot.png)

### 1. Learns Your Taste

Serendipity builds a profile of what you like through:

- **taste.md**: Your written aesthetic preferences
- **Feedback loop**: Click thumbs up/down on the recommendations. The patterns will be extracted to `learnings.md`
- **history**: What you've liked and disliked before

The more you use it, the better it gets.

### 2. Two Discovery Modes

- **Convergent** ("More Like This"): Match your explicit interests directly
- **Divergent** ("Expand Your Palette"): Find content with shared underlying qualities, crossing genre boundaries

Add custom approaches by editing the `approaches` section in settings.

### 3. Pairings

Beyond recommendations, Serendipity suggests contextual "pairings" that complement your discovery session—like wine pairings for a meal:

- **Music**: Background listening that matches your mood
- **Quote**: A thought-provoking quote related to themes
- **Exercise**: Physical activity suggestion
- **Food**: Something to eat/drink while exploring
- **Tip**: Practical advice related to your context

Enable/disable pairings in `settings.yaml`:

```yaml
pairings:
  music:
    enabled: true
    search_based: true # Uses WebSearch
  quote:
    enabled: true
    search_based: false # Generated from Claude's knowledge
```

## Quick Start

```bash
# Install
pip install serendipity

# Set up your Anthropic API key (or can skip if have local Claude Code Authentication)
export ANTHROPIC_API_KEY="your-api-key"

# Run with editor input
serendipity -i
```

Your first run opens an HTML page with recommendations. Click thumbs up/down to give feedback. Edit your taste profile to improve the recommendation for the future, further the diff will be streamed when another batch is generated from the current session.

You can also set up your taste profile for better results:

```bash
serendipity profile -i
```

## Usage

```bash
# Basic usage
serendipity                             # Uses your profile
serendipity -i                          # Open editor for context
serendipity -p                          # From clipboard
serendipity discover notes.md           # From file
serendipity discover "contemplative"    # Quick prompt

# Options
serendipity -m opus                     # Use Claude Opus
serendipity -n 15                       # 15 recommendations
serendipity -s whorl                    # Enable Whorl MCP source
```

### Output Format & Destination

Output format (how recommendations are structured) and destination (where they go) are independent:

```bash
# Format options: html, markdown, json
serendipity -o html      # Rich HTML with cards (default)
serendipity -o markdown  # Plain text
serendipity -o json      # Structured data

# Destination options: browser, stdout, file
serendipity --dest browser   # Open in browser (default)
serendipity --dest stdout    # Print to terminal
serendipity --dest file      # Save to ~/.serendipity/output/
```

### Piping Support

Serendipity auto-detects when output is piped and switches to JSON + stdout:

```bash
# Pipe to jq for filtering
serendipity | jq '.convergent[0].url'

# Save to file
serendipity > recommendations.json

# Chain with other tools
serendipity | jq -r '.convergent[].url' | xargs open
```

Explicit stdin input with `-`:

```bash
cat notes.md | serendipity discover -
echo "jazz music" | serendipity discover -
```

## Profiles

Create separate profiles for different contexts or users:

```bash
serendipity profile list                # List all profiles
serendipity profile create work         # Create new profile
serendipity profile switch work         # Switch active profile
serendipity profile manage              # Edit taste.md
serendipity profile build               # Interactive profile builder
```

### Building Your Profile

The interactive profile builder uses Claude with extended thinking to craft your taste profile through guided questions:

```bash
serendipity profile build               # Start building
serendipity profile build --reset       # Start fresh
```

The builder:
- Asks multi-select questions about your preferences
- Synthesizes answers into a coherent taste profile
- Lets you revise with feedback until satisfied
- Previews what recommendations would look like

Options:
```bash
serendipity profile build -q 6          # 6 questions per round
serendipity profile build -o 6          # Up to 6 options per question
serendipity profile build -t 20000      # More thinking tokens
serendipity profile build --quiet       # Less verbose output
```

Each profile has its own taste, history, and settings:

```
~/.serendipity/profiles/<name>/
├── settings.yaml       # config
├── output/             # generated files
└── user_data/
    ├── taste.md        # your preferences
    ├── history.jsonl   # recommendation history + feedback
    └── learnings.md    # extracted patterns
```

## Configuration

```bash
serendipity settings                    # View all settings
serendipity settings --edit             # Edit in $EDITOR
serendipity settings get media.youtube  # View specific section
serendipity settings add media -i       # Add new media type
serendipity settings add approach -i    # Add new approach
serendipity settings add source -i      # Add new context source
```

## Tech Stack

**CLI**: Python, Typer, Rich

**Agent**: Claude (via claude-agent-sdk), WebSearch

**Output**: HTML with embedded feedback server

## Experimental

Serendipity is highly customizable. Run `serendipity settings` to see the full configuration:

```
Settings
  model: opus
  total_count: 3
  feedback_server_port: 9876
  thinking_tokens: disabled

Approaches (how to find):
  convergent: More Like This (disabled)
  divergent: Expand Your Palette (enabled)

Media Types (what format):
  article: Articles & Essays (disabled)
  youtube: YouTube Videos (disabled)
  book: Books (enabled)
  podcast: Podcasts (disabled)

Agent chooses distribution based on your taste.md

Context Sources (user profile):
  taste: enabled (loader) - User's aesthetic preferences
  learnings: enabled (loader) - Extracted patterns from feedback
  history: enabled (loader) - Recent recommendations and feedback
  whorl: disabled (mcp) - Personal knowledge base via Whorl

Prompts (agent instructions):
  discovery: default
  frontend_design: default
  system: default

Stylesheet: default

Config: ~/.serendipity/profiles/default/settings.yaml
Prompts: ~/.serendipity/profiles/default/prompts
Style: ~/.serendipity/profiles/default/style.css
```

### Custom Media Types

Add new media types beyond articles, videos, and books:

```bash
serendipity settings add media -i
```

Example: adding academic papers as a media type in `settings.yaml`:

```yaml
media:
  paper:
    display_name: "Academic Papers"
    enabled: true
    sources:
      - tool: WebSearch
        hints: "site:arxiv.org OR site:scholar.google.com {query}"
    prompt_hint: "Prefer foundational papers and recent breakthroughs."
```

### Custom Context Sources

Add additional context sources to personalize recommendations:

```bash
serendipity settings add source -i
```

Context sources inject information about you into the agent's context. Built-in sources include `taste.md`, `learnings.md`, and `history`. You can add your own file-based sources or MCP servers.

Enable/disable sources with `serendipity settings --enable-source <name>` or `-s <name>` for one-off runs.

### Custom Agent Prompts

Override the default agent instructions:

```bash
serendipity settings prompts --edit discovery
```

Available prompts: `discovery`, `frontend_design`, `system`. These control how the agent searches, evaluates, and presents recommendations.

### Whorl Integration

[Whorl](https://github.com/Uzay-G/whorl) is a personal knowledge base that stores and indexes your notes and documents. When integrated, Claude searches your Whorl knowledge base *before* making recommendations.

```bash
# Install Whorl (see Whorl README for full setup)
pip install whorled && whorl init

# Enable in Serendipity
serendipity -s whorl              # one-off
serendipity settings --enable-source whorl  # permanent
```

Serendipity auto-starts the Whorl server when enabled.

## Development

```bash
pip install -e ".[dev]"
pytest                  # Run tests
ruff check .            # Lint
```

## Getting Your API Key

1. Go to [Anthropic Console](https://console.anthropic.com/)
2. Sign in or create an account
3. Navigate to API Keys → Create new key
4. Set it:
   ```bash
   export ANTHROPIC_API_KEY="your-key"
   ```
   Or add to `~/.zshrc` / `~/.bashrc`.

## License

MIT
