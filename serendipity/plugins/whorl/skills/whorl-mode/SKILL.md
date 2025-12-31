---
name: whorl-mode
description: Search user's personal knowledge base (whorl) for context about their preferences, interests, and past writings. Use this to personalize recommendations.
---

# Whorl Mode - Personal Knowledge Base Integration

When this skill is active, you have access to the user's personal knowledge base stored in whorl. This contains their notes, journals, blog posts, preferences, and other personal documents.

## Available MCP Tools

Use these tools to search the user's knowledge base:

### Text Search (Fast, Keyword-Based)
```
mcp__whorl__text_search_text_search_post
- query: Keywords to search for
- limit: Max results (default 10)
- context: Lines of context around matches (default 2)
```

### Agent Search (Semantic, AI-Powered)
```
mcp__whorl__agent_search_agent_search_post
- query: Natural language question
```
Note: Requires ANTHROPIC_API_KEY in whorl server

### Bash Commands
```
mcp__whorl__bash_bash_post
- command: Bash command to run in ~/.whorl/docs/
- timeout: Timeout in seconds (default 30)
```

## When to Search Whorl

**ALWAYS search whorl FIRST** when making recommendations to:
1. Understand user's aesthetic preferences and taste
2. Find topics they've written about or are interested in
3. Discover their favorite authors, artists, or influences
4. Learn their writing style and voice
5. Find prior work they've done on similar topics

## Search Strategies

### For Understanding User Taste
```
text_search: "favorite books authors influences"
text_search: "aesthetic design preferences style"
text_search: "interests hobbies projects"
```

### For Finding Related Context
```
text_search: "{topic from user context}"
text_search: "recommendations liked enjoyed"
```

### For Understanding User Background
```
text_search: "about background experience"
text_search: "writing essays posts"
```

## Integration with Serendipity

When generating recommendations:
1. **First**: Search whorl for user preferences and interests
2. **Then**: Use WebSearch to find recommendations
3. **Finally**: Match recommendations to user's established taste

This makes recommendations more personal and relevant.

## Example Workflow

```
User context: "I'm working on a project about urban design"

1. Search whorl: text_search("urban design architecture cities")
   -> Find user's notes on Christopher Alexander, Jane Jacobs

2. Search whorl: text_search("favorite books design")
   -> Find they love "A Pattern Language", "Death and Life of Great American Cities"

3. Use this context to find convergent recommendations that match their taste
   and divergent recommendations that expand on their interests
```
