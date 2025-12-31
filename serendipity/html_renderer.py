"""HTML rendering for serendipity results."""

import tempfile
import webbrowser
from pathlib import Path
from typing import Optional

from serendipity.agent import DiscoveryResult, HtmlStyle

# Default CSS fallback when Claude doesn't provide styling
DEFAULT_CSS = """
* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    line-height: 1.6;
    color: #1f2937;
    background: #f9fafb;
    padding: 2rem;
}
.header {
    text-align: center;
    margin-bottom: 2rem;
}
.header h1 {
    font-size: 2rem;
    font-weight: 700;
    color: #111827;
    margin-bottom: 0.5rem;
}
.header .meta {
    font-size: 0.875rem;
    color: #6b7280;
}
.header .style-note {
    font-size: 0.75rem;
    color: #9ca3af;
    margin-top: 0.25rem;
    font-style: italic;
}
.more-actions {
    display: flex;
    justify-content: center;
    gap: 1rem;
    margin-bottom: 2rem;
}
.more-actions button {
    padding: 0.75rem 1.5rem;
    border: none;
    border-radius: 8px;
    font-size: 1rem;
    cursor: pointer;
    transition: all 0.2s;
}
.more-actions button:hover {
    transform: translateY(-2px);
}
.more-actions .btn-convergent {
    background: #dbeafe;
    color: #1e40af;
}
.more-actions .btn-convergent:hover {
    background: #bfdbfe;
}
.more-actions .btn-divergent {
    background: #ffedd5;
    color: #c2410c;
}
.more-actions .btn-divergent:hover {
    background: #fed7aa;
}
.more-actions button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none;
}
.container {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 2rem;
    max-width: 1400px;
    margin: 0 auto;
}
@media (max-width: 768px) {
    .container {
        grid-template-columns: 1fr;
    }
}
.column {
    padding: 1.5rem;
    border-radius: 12px;
}
.convergent {
    background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
}
.divergent {
    background: linear-gradient(135deg, #fff7ed 0%, #ffedd5 100%);
}
.column h2 {
    font-size: 1.25rem;
    font-weight: 600;
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.convergent h2 {
    color: #1e40af;
}
.divergent h2 {
    color: #c2410c;
}
.recommendation {
    background: white;
    padding: 1rem;
    border-radius: 8px;
    margin-bottom: 1rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    transition: transform 0.2s, box-shadow 0.2s;
}
.recommendation:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}
.recommendation:last-child {
    margin-bottom: 0;
}
.recommendation a {
    font-weight: 600;
    text-decoration: none;
    color: #2563eb;
    word-break: break-all;
}
.recommendation a:hover {
    text-decoration: underline;
}
.recommendation .reason {
    margin-top: 0.5rem;
    font-size: 0.9rem;
    color: #4b5563;
}
.recommendation .actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.75rem;
}
.recommendation .actions button {
    padding: 0.25rem 0.75rem;
    border: 1px solid #e5e7eb;
    border-radius: 4px;
    background: #f9fafb;
    cursor: pointer;
    font-size: 1rem;
    transition: all 0.2s;
}
.recommendation .actions button:hover {
    background: #f3f4f6;
}
.recommendation .actions button.liked {
    background: #dcfce7;
    border-color: #22c55e;
}
.recommendation .actions button.disliked {
    background: #fee2e2;
    border-color: #ef4444;
}
.recommendation .actions button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}
.empty {
    color: #9ca3af;
    font-style: italic;
    text-align: center;
    padding: 2rem;
}
.loading {
    display: none;
    text-align: center;
    padding: 1rem;
    color: #6b7280;
}
.loading.active {
    display: block;
}
"""

# HTML structure template (fixed, CSS is injected)
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Serendipity - Discoveries</title>
    <style>
{css}
    </style>
</head>
<body>
    <div class="header">
        <h1>Your Discoveries</h1>
        <p class="meta">{meta}</p>
        {style_note}
    </div>

    <div class="more-actions">
        <button class="btn-convergent" onclick="requestMore('convergent')">More like this</button>
        <button class="btn-divergent" onclick="requestMore('divergent')">More surprises</button>
    </div>

    <div class="container">
        <div class="column convergent" id="convergent-column">
            <h2>More Like This</h2>
            <div id="convergent-list">
                {convergent_html}
            </div>
            <div class="loading" id="convergent-loading">Loading more...</div>
        </div>
        <div class="column divergent" id="divergent-column">
            <h2>Expand Your Palette</h2>
            <div id="divergent-list">
                {divergent_html}
            </div>
            <div class="loading" id="divergent-loading">Loading more...</div>
        </div>
    </div>

    <script>
        const SESSION_ID = "{session_id}";
        const SERVER_PORT = {server_port};
        // Use relative URL if served from localhost, otherwise absolute
        const API_BASE = window.location.hostname === 'localhost' ? '' : `http://localhost:${{SERVER_PORT}}`;

        async function feedback(button, rating) {{
            const rec = button.closest('.recommendation');
            const url = rec.dataset.url;

            try {{
                const response = await fetch(`${{API_BASE}}/feedback`, {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        url: url,
                        session_id: SESSION_ID,
                        feedback: rating
                    }})
                }});

                if (response.ok) {{
                    // Visual feedback
                    const buttons = rec.querySelectorAll('.actions button');
                    buttons.forEach(btn => {{
                        btn.disabled = true;
                        btn.classList.remove('liked', 'disliked');
                    }});
                    button.classList.add(rating);
                }}
            }} catch (e) {{
                console.error('Feedback error:', e);
                alert('Could not save feedback. Is the serendipity server still running?');
            }}
        }}

        async function requestMore(type) {{
            const btn = document.querySelector(`.btn-${{type}}`);
            const loading = document.getElementById(`${{type}}-loading`);
            const list = document.getElementById(`${{type}}-list`);

            btn.disabled = true;
            loading.classList.add('active');

            try {{
                const response = await fetch(`${{API_BASE}}/more`, {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        session_id: SESSION_ID,
                        type: type,
                        count: 5
                    }})
                }});

                if (response.ok) {{
                    const data = await response.json();
                    if (data.recommendations && data.recommendations.length > 0) {{
                        data.recommendations.forEach(rec => {{
                            const div = document.createElement('div');
                            div.className = 'recommendation';
                            div.dataset.url = rec.url;
                            div.innerHTML = `
                                <a href="${{rec.url}}" target="_blank" rel="noopener">${{rec.url}}</a>
                                <p class="reason">${{rec.reason}}</p>
                                <div class="actions">
                                    <button onclick="feedback(this, 'liked')">👍</button>
                                    <button onclick="feedback(this, 'disliked')">👎</button>
                                </div>
                            `;
                            list.appendChild(div);
                        }});
                    }}
                }} else {{
                    const error = await response.json();
                    console.error('More error:', error);
                    alert('Could not get more recommendations: ' + (error.error || 'Unknown error'));
                }}
            }} catch (e) {{
                console.error('Request more error:', e);
                alert('Could not get more recommendations. Is the serendipity server still running?');
            }} finally {{
                btn.disabled = false;
                loading.classList.remove('active');
            }}
        }}
    </script>
</body>
</html>
"""

RECOMMENDATION_TEMPLATE = """<div class="recommendation" data-url="{url}">
    <a href="{url}" target="_blank" rel="noopener">{url}</a>
    <p class="reason">{reason}</p>
    <div class="actions">
        <button onclick="feedback(this, 'liked')">👍</button>
        <button onclick="feedback(this, 'disliked')">👎</button>
    </div>
</div>
"""


def render_html(
    result: DiscoveryResult,
    server_port: int = 9876,
) -> str:
    """Render discovery results as HTML.

    Args:
        result: The discovery result to render
        server_port: Port for the feedback server

    Returns:
        HTML string
    """
    # Use dynamic CSS from Claude if available, otherwise default
    if result.html_style and result.html_style.css:
        css = result.html_style.css
        style_note = f'<p class="style-note">Style: {result.html_style.description}</p>'
    else:
        css = DEFAULT_CSS
        style_note = ""

    # Render convergent recommendations
    if result.convergent:
        convergent_html = "\n".join(
            RECOMMENDATION_TEMPLATE.format(url=r.url, reason=r.reason)
            for r in result.convergent
        )
    else:
        convergent_html = '<p class="empty">No convergent recommendations found</p>'

    # Render divergent recommendations
    if result.divergent:
        divergent_html = "\n".join(
            RECOMMENDATION_TEMPLATE.format(url=r.url, reason=r.reason)
            for r in result.divergent
        )
    else:
        divergent_html = '<p class="empty">No divergent recommendations found</p>'

    # Build meta info
    meta_parts = []
    meta_parts.append(f"{len(result.convergent)} convergent, {len(result.divergent)} divergent")
    if result.cost_usd:
        meta_parts.append(f"Cost: ${result.cost_usd:.4f}")

    return HTML_TEMPLATE.format(
        css=css,
        meta=" | ".join(meta_parts),
        style_note=style_note,
        convergent_html=convergent_html,
        divergent_html=divergent_html,
        session_id=result.session_id,
        server_port=server_port,
    )


def open_in_browser(html_content: str) -> Path:
    """Write HTML to temp file and open in browser.

    Args:
        html_content: The HTML string to display

    Returns:
        Path to the temporary file
    """
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".html",
        delete=False,
        prefix="serendipity_",
    ) as f:
        f.write(html_content)
        path = Path(f.name)

    webbrowser.open(f"file://{path}")
    return path


def render_and_open(
    result: DiscoveryResult,
    server_port: int = 9876,
) -> Path:
    """Render results and open in browser.

    Args:
        result: The discovery result
        server_port: Port for the feedback server

    Returns:
        Path to the HTML file
    """
    html = render_html(result, server_port=server_port)
    return open_in_browser(html)
