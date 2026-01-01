# Icon System

Icons are auto-discovered from `serendipity/static/icons/`. **Single source of truth**: the SVG files.

## Provenance Requirement

**All icons MUST include provenance** - an XML comment with the exact source URL:

```xml
<!-- Lucide Icons - ISC License - https://unpkg.com/lucide-static@latest/icons/{name}.svg -->
<svg xmlns="http://www.w3.org/2000/svg" ...>
  ...
</svg>
```

## Adding a New Icon

1. Fetch SVG from `https://unpkg.com/lucide-static@latest/icons/<name>.svg`
2. Add provenance comment as first line (see format above)
3. Save to `serendipity/static/icons/<name>.svg`
4. Use in settings: `icon: "<name>"`

That's it. No code changes needed.

## Browse Available Icons

- [Lucide Icons](https://lucide.dev/icons) - Browse and search all available icons
- [unpkg CDN](https://unpkg.com/browse/lucide-static@latest/icons/) - Direct SVG files

## Current Icons

| Icon | Usage |
|------|-------|
| flame | Passion/intensity pairings |
| footprints | Journey/exploration pairings |
| gamepad-2 | Gaming pairings |
| lightbulb | Ideas/tips pairings |
| map-pin | Location pairings |
| music | Music pairings |
| pencil-line | Writing pairings |
| quote | Quote pairings |
| target | Goal/focus pairings |
| thumbs-up | Positive feedback |
| thumbs-down | Negative feedback |
| utensils | Food pairings |
| wine | Drink pairings |
