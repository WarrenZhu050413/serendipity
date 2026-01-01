"""Interactive profile builder using Claude with extended thinking."""

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import questionary
from questionary import Style

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from serendipity.display import AgentDisplay, DisplayConfig
from serendipity.resources import get_prompt

if TYPE_CHECKING:
    from serendipity.storage import StorageManager


# Custom style for questionary prompts
PROFILE_STYLE = Style([
    ("qmark", "fg:#673ab7 bold"),         # Purple question mark
    ("question", "bold"),                  # Bold question text
    ("answer", "fg:#f44336 bold"),         # Red selected answer
    ("pointer", "fg:#673ab7 bold"),        # Purple pointer
    ("highlighted", "fg:#673ab7 bold"),    # Purple highlighted choice
    ("selected", "fg:#cc5454"),            # Red for selected checkboxes
    ("separator", "fg:#cc5454"),           # Separator color
    ("instruction", "fg:#858585"),         # Gray instruction text
    ("text", ""),                          # Default text
    ("disabled", "fg:#858585 italic"),     # Gray italic for disabled
    ("description", "fg:#858585 italic"),  # Custom: gray italic for descriptions
    ("recommended", "fg:#4caf50 bold"),    # Custom: green for recommended tag
])


# Default prompts (used if not overridden in user's prompts/ dir)
DEFAULT_QUESTIONS_PROMPT = """You are helping someone articulate their personal taste and aesthetic sensibilities.

IMPORTANT: Do NOT use any tools (WebFetch, WebSearch, etc). Generate questions directly based on the profile text provided below.

## Current Taste Profile
{current_taste}

## Already Asked (do not repeat these topics)
{asked_topics}

## Previous Answers This Session
{session_answers}

## Your Task

Generate exactly {count} targeted questions to better understand this person's taste. Do not fetch external URLs - work only with the text above.
Each question should:
1. Explore a specific dimension of taste not yet covered
2. Have exactly {max_options} concrete, evocative options (not generic platitudes)
3. Include brief descriptions that paint a vivid picture
4. Mark ONE option as "recommended" if it clearly aligns with their existing profile

Think carefully about what's MISSING from their profile. Consider dimensions like:
- Sensory preferences (visual, auditory, tactile)
- Intellectual interests (depth, breadth, domains)
- Emotional resonances (what moves them)
- Format preferences (long-form vs short, dense vs spacious)
- Pacing (fast vs slow, intense vs gentle)
- Complexity tolerance (simple vs intricate)
- Novelty vs comfort balance
- Era and cultural affinities

Output JSON between <questions> tags:
<questions>
[
  {
    "id": "unique_topic_id",
    "category": "Category Name",
    "question": "The question text?",
    "multi_select": false,
    "options": [
      {
        "value": "option_id",
        "label": "Short Label",
        "description": "Evocative 1-sentence description",
        "recommended": false
      }
    ]
  }
]
</questions>"""

DEFAULT_SYNTHESIS_PROMPT = """You are helping someone articulate their personal taste and aesthetic sensibilities.

## Existing Taste Profile
{current_taste}

## Session Answers
{all_answers}

## Your Task

Synthesize these answers into an improved taste.md profile. The output should be:
1. Written in first person ("I love...", "I'm drawn to...")
2. Evocative and specific, not generic platitudes
3. Organized into natural paragraphs or thematic sections
4. Preserve valuable content from the existing profile
5. Integrate new insights from answers smoothly
6. Be concise but rich - quality over quantity

Use extended thinking to:
- Find themes and connections across answers
- Identify their unique aesthetic fingerprint
- Choose precise, evocative language

Output the complete new taste.md content between <taste_profile> tags:
<taste_profile>
[markdown content here]
</taste_profile>"""

DEFAULT_REVISION_PROMPT = """You are helping someone refine their personal taste profile based on their feedback.

## Current Draft Profile
{draft_profile}

## User Feedback
{feedback}

## Your Task

Revise the taste profile based on the user's feedback. The feedback might:
- Point out inaccuracies ("I don't actually like X")
- Request additions ("You missed that I love Y")
- Suggest tone changes ("Make it less formal")
- Ask for reorganization ("Group the music stuff together")

Use extended thinking to:
- Understand the spirit of the feedback
- Identify what to keep, change, or add
- Maintain the evocative, first-person style

Output the revised taste.md content between <taste_profile> tags:
<taste_profile>
[markdown content here]
</taste_profile>"""

DEFAULT_PREVIEW_PROMPT = """Based on this taste profile, suggest 3-5 specific things this person might enjoy discovering.

## Taste Profile
{taste_profile}

## Your Task

Generate concrete, specific recommendations that align with this person's aesthetic sensibilities.
Be creative and surprising - don't just echo back what they said they like.
Look for interesting intersections and unexpected connections.

For each recommendation, briefly explain WHY it fits their taste.

Format as a simple list with explanations."""


@dataclass
class QuestionOption:
    """An option for a question."""

    value: str  # Internal value
    label: str  # Display label
    description: str  # Brief explanation
    recommended: bool = False  # Suggested based on context


@dataclass
class TasteQuestion:
    """A single question to ask the user."""

    id: str  # Unique ID for tracking
    category: str  # e.g., "Aesthetics", "Content"
    question: str  # The question text
    options: list[QuestionOption]  # 2-4 concrete options
    multi_select: bool = False  # Whether multiple selections allowed


@dataclass
class UserAnswer:
    """User's response to a question."""

    question_id: str
    category: str
    question: str
    selected: list[str]  # Selected option labels (for context)
    other: str = ""  # Free-form "other" response


@dataclass
class BuildSession:
    """State for a profile building session."""

    current_taste: str  # Existing taste.md content
    asked_topics: set[str] = field(default_factory=set)  # Topics already asked
    all_answers: list[UserAnswer] = field(default_factory=list)
    round_number: int = 1


class ProfileBuilder:
    """Interactive profile builder using Claude with extended thinking."""

    def __init__(
        self,
        console: Console,
        storage: "StorageManager",
        model: str = "opus",
        max_thinking_tokens: int = 10000,
        verbose: bool = False,
    ):
        """Initialize the profile builder.

        Args:
            console: Rich console for output
            storage: StorageManager for loading/saving profiles
            model: Claude model to use (haiku, sonnet, opus)
            max_thinking_tokens: Token budget for extended thinking
            verbose: Show detailed progress including thinking
        """
        self.console = console
        self.storage = storage
        self.model = model
        self.max_thinking_tokens = max_thinking_tokens
        self.verbose = verbose

        # Load prompts from user paths (auto-creates from defaults)
        self.questions_prompt = storage.get_prompt_path(
            "profile_questions.txt", DEFAULT_QUESTIONS_PROMPT
        ).read_text()
        self.synthesis_prompt = storage.get_prompt_path(
            "profile_synthesis.txt", DEFAULT_SYNTHESIS_PROMPT
        ).read_text()
        self.revision_prompt = storage.get_prompt_path(
            "profile_revision.txt", DEFAULT_REVISION_PROMPT
        ).read_text()
        self.preview_prompt = storage.get_prompt_path(
            "profile_preview.txt", DEFAULT_PREVIEW_PROMPT
        ).read_text()

        # Display for verbose output
        self.display = AgentDisplay(
            console=console, config=DisplayConfig(verbose=verbose)
        )

    async def generate_questions(
        self,
        session: BuildSession,
        max_questions: int = 4,
        max_options: int = 4,
    ) -> list[TasteQuestion]:
        """Generate targeted questions based on current taste and history.

        Args:
            session: Current build session state
            max_questions: Number of questions to generate
            max_options: Number of options per question

        Returns:
            List of TasteQuestion objects
        """
        # Format session answers for context
        answers_text = self._format_answers(session.all_answers)

        # Build prompt using safe string replacement (avoids conflict with JSON braces)
        prompt = self.questions_prompt
        prompt = prompt.replace("{current_taste}", session.current_taste or "(No existing profile)")
        prompt = prompt.replace("{asked_topics}", ", ".join(session.asked_topics) or "None yet")
        prompt = prompt.replace("{session_answers}", answers_text or "None yet")
        prompt = prompt.replace("{count}", str(max_questions))
        prompt = prompt.replace("{max_options}", str(max_options))

        options = ClaudeAgentOptions(
            model=self.model,
            system_prompt="You are a taste profile builder helping someone articulate their aesthetic sensibilities. Do not use any tools - generate questions directly.",
            max_turns=1,
            max_thinking_tokens=self.max_thinking_tokens,
            allowed_tools=[],  # No tools - just generate questions
        )

        response_text = []

        self.console.print("[dim]Generating questions...[/dim]")

        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)

            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, ThinkingBlock):
                            self.display.show_thinking(block.thinking)
                        elif isinstance(block, ToolUseBlock):
                            self.display.show_tool_use(
                                name=block.name,
                                tool_id=block.id,
                                input_data=block.input or {},
                            )
                        elif isinstance(block, TextBlock):
                            response_text.append(block.text)

        # Parse questions from response
        full_response = "".join(response_text)
        questions = self._parse_questions(full_response)

        # Track asked topics
        for q in questions:
            session.asked_topics.add(q.id)

        return questions

    async def synthesize_profile(self, session: BuildSession) -> str:
        """Synthesize all answers into improved taste.md prose.

        Args:
            session: Build session with all collected answers

        Returns:
            New taste.md content as string
        """
        # Format all answers
        answers_text = self._format_answers(session.all_answers)

        # Build prompt using safe string replacement
        prompt = self.synthesis_prompt
        prompt = prompt.replace("{current_taste}", session.current_taste or "(No existing profile)")
        prompt = prompt.replace("{all_answers}", answers_text)

        options = ClaudeAgentOptions(
            model=self.model,
            system_prompt="You are a taste profile builder synthesizing user preferences into evocative prose.",
            max_turns=1,
            max_thinking_tokens=self.max_thinking_tokens,
            allowed_tools=[],  # No tools - just synthesize
        )

        response_text = []

        self.console.print("[dim]Synthesizing your profile...[/dim]")

        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)

            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, ThinkingBlock):
                            self.display.show_thinking(block.thinking)
                        elif isinstance(block, TextBlock):
                            response_text.append(block.text)

        # Parse profile from response
        full_response = "".join(response_text)
        return self._parse_profile(full_response)

    async def revise_profile(self, draft_profile: str, feedback: str) -> str:
        """Revise a draft profile based on user feedback.

        Args:
            draft_profile: The current draft profile text
            feedback: User's feedback/criticism

        Returns:
            Revised taste.md content as string
        """
        # Build prompt using safe string replacement
        prompt = self.revision_prompt
        prompt = prompt.replace("{draft_profile}", draft_profile)
        prompt = prompt.replace("{feedback}", feedback)

        options = ClaudeAgentOptions(
            model=self.model,
            system_prompt="You are a taste profile builder revising a profile based on user feedback.",
            max_turns=1,
            max_thinking_tokens=self.max_thinking_tokens,
            allowed_tools=[],  # No tools - just revise
        )

        response_text = []

        self.console.print("[dim]Revising your profile...[/dim]")

        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)

            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, ThinkingBlock):
                            self.display.show_thinking(block.thinking)
                        elif isinstance(block, TextBlock):
                            response_text.append(block.text)

        # Parse profile from response
        full_response = "".join(response_text)
        return self._parse_profile(full_response)

    async def preview_recommendations(self, taste_profile: str) -> str:
        """Generate preview recommendations based on a taste profile.

        Args:
            taste_profile: The taste profile to base recommendations on

        Returns:
            Recommendations text
        """
        # Build prompt using safe string replacement
        prompt = self.preview_prompt
        prompt = prompt.replace("{taste_profile}", taste_profile)

        options = ClaudeAgentOptions(
            model=self.model,
            system_prompt="You are a discovery assistant suggesting things that match someone's taste.",
            max_turns=1,
            max_thinking_tokens=self.max_thinking_tokens,
            allowed_tools=[],  # No tools - just recommend
        )

        response_text = []

        self.console.print("[dim]Generating preview recommendations...[/dim]")

        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)

            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, ThinkingBlock):
                            self.display.show_thinking(block.thinking)
                        elif isinstance(block, TextBlock):
                            response_text.append(block.text)

        return "".join(response_text)

    def run_interactive_round(
        self,
        questions: list[TasteQuestion],
    ) -> tuple[list[UserAnswer], str]:
        """Display questions interactively and collect answers.

        Args:
            questions: List of questions to ask

        Returns:
            Tuple of (answers, action) where action is "continue", "done", or "cancel"
        """
        answers = []

        for q in questions:
            # Category header
            self.console.print()
            self.console.print(f"[bold cyan]─── {q.category.upper()} ───[/bold cyan]")
            self.console.print()

            # Build questionary choices with styled token tuples
            choices = []
            for opt in q.options:
                # Build styled title using token tuples
                title_parts = [("class:text", opt.label)]
                if opt.recommended:
                    title_parts.append(("class:recommended", " ★"))
                title_parts.append(("class:text", "\n      "))
                title_parts.append(("class:description", opt.description))
                choices.append(questionary.Choice(title=title_parts, value=opt.value))

            # Add "other" option with styling
            choices.append(
                questionary.Choice(
                    title=[
                        ("class:text", "Something else..."),
                        ("class:text", "\n      "),
                        ("class:description", "Enter your own answer"),
                    ],
                    value="__other__",
                )
            )

            # Ask question (always multi-select for richer answers)
            result = questionary.checkbox(
                q.question,
                choices=choices,
                instruction="(Space to select, Enter to confirm)",
                style=PROFILE_STYLE,
            ).ask()
            selected = result if result else []

            # Handle cancel (Ctrl+C)
            if result is None:
                return [], "cancel"

            # Handle "other" with text input
            other_text = ""
            if "__other__" in selected:
                other_text = questionary.text(
                    "Please describe:",
                    instruction="(Enter your own answer)",
                    style=PROFILE_STYLE,
                ).ask()
                if other_text is None:
                    return [], "cancel"
                # Remove __other__ from selected, add the text
                selected = [s for s in selected if s != "__other__"]

            # Map values back to labels for context
            value_to_label = {opt.value: opt.label for opt in q.options}
            selected_labels = [value_to_label.get(s, s) for s in selected]

            answers.append(
                UserAnswer(
                    question_id=q.id,
                    category=q.category,
                    question=q.question,
                    selected=selected_labels,
                    other=other_text,
                )
            )

        # Final action choice
        self.console.print()
        action = questionary.select(
            "What next?",
            choices=[
                questionary.Choice("Continue refining (more questions)", value="continue"),
                questionary.Choice("I'm done - synthesize my profile", value="done"),
                questionary.Choice("Cancel (discard this session)", value="cancel"),
            ],
            style=PROFILE_STYLE,
        ).ask()

        if action is None:
            action = "cancel"

        return answers, action

    def _format_answers(self, answers: list[UserAnswer]) -> str:
        """Format answers for inclusion in prompts."""
        if not answers:
            return ""

        parts = []
        for a in answers:
            parts.append(f"**{a.category}**: {a.question}")
            if a.selected:
                parts.append(f"  Selected: {', '.join(a.selected)}")
            if a.other:
                parts.append(f"  Custom: {a.other}")
            parts.append("")

        return "\n".join(parts)

    def _parse_questions(self, text: str) -> list[TasteQuestion]:
        """Parse questions from Claude response."""
        questions = []

        # Extract JSON from <questions> tags
        match = re.search(r"<questions>\s*(.*?)\s*</questions>", text, re.DOTALL)
        json_str = None
        if match:
            json_str = match.group(1)
        else:
            # Try raw JSON array - find [ and parse from there
            start = text.find("[")
            if start >= 0:
                # Try to parse from the [ character
                try:
                    data = json.loads(text[start:])
                    # Successfully parsed, use this
                    json_str = text[start:]
                except json.JSONDecodeError:
                    # Try to find a balanced array
                    json_str = None

        if json_str is None:
            self.console.print(
                "[yellow]Warning: Could not parse questions from response[/yellow]"
            )
            return []

        try:
            data = json.loads(json_str)
            for q_data in data:
                options = [
                    QuestionOption(
                        value=opt.get("value", ""),
                        label=opt.get("label", ""),
                        description=opt.get("description", ""),
                        recommended=opt.get("recommended", False),
                    )
                    for opt in q_data.get("options", [])
                ]
                questions.append(
                    TasteQuestion(
                        id=q_data.get("id", ""),
                        category=q_data.get("category", "General"),
                        question=q_data.get("question", ""),
                        options=options,
                        multi_select=q_data.get("multi_select", False),
                    )
                )
        except json.JSONDecodeError as e:
            self.console.print(f"[yellow]Warning: JSON parse error: {e}[/yellow]")

        return questions

    def _parse_profile(self, text: str) -> str:
        """Parse profile content from Claude response."""
        # Extract from <taste_profile> tags
        match = re.search(r"<taste_profile>\s*(.*?)\s*</taste_profile>", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Fallback: return full text (Claude might not use tags)
        return text.strip()

    def run_sync(
        self,
        reset: bool = False,
        questions_per_batch: int = 4,
        max_options: int = 4,
    ) -> bool:
        """Run the interactive build session synchronously.

        Uses a sync/async hybrid approach: questionary runs synchronously
        while Claude API calls run in asyncio.run() blocks.

        The interview continues indefinitely until the user chooses to
        synthesize their profile or cancel.

        Args:
            reset: Start fresh (ignore existing taste.md)
            questions_per_batch: Number of questions per batch
            max_options: Number of options per question

        Returns:
            True if profile was saved, False if cancelled
        """
        # Load existing taste profile
        current_taste = "" if reset else self.storage.load_taste()

        # Initialize session
        session = BuildSession(current_taste=current_taste)

        # Header
        self.console.print()
        self.console.print(
            Panel(
                "[bold]Build Your Taste Profile[/bold]\n\n"
                "I'll ask you questions to understand your aesthetic sensibilities.\n"
                "After each batch, choose to continue or synthesize your profile.\n"
                "Press Ctrl+C at any time to cancel.",
                border_style="cyan",
            )
        )

        if current_taste:
            self.console.print(
                f"[dim]Building on your existing {len(current_taste.split())} word profile...[/dim]"
            )
        else:
            self.console.print("[dim]Starting from scratch...[/dim]")

        try:
            while True:  # Infinite loop until user chooses to synthesize or cancel
                self.console.print()
                self.console.print(
                    f"[bold]Batch {session.round_number}[/bold] [dim]({len(session.all_answers)} answers so far)[/dim]"
                )

                # Generate questions (async)
                questions = asyncio.run(
                    self.generate_questions(
                        session,
                        max_questions=questions_per_batch,
                        max_options=max_options,
                    )
                )
                if not questions:
                    self.console.print("[yellow]No more questions to ask.[/yellow]")
                    break

                # Run interactive round (sync - questionary needs this)
                answers, action = self.run_interactive_round(questions)

                if action == "cancel":
                    self.console.print("[yellow]Cancelled. No changes saved.[/yellow]")
                    return False

                # Store answers
                session.all_answers.extend(answers)

                if action == "done":
                    break

                session.round_number += 1

            # Synthesize profile
            if not session.all_answers:
                self.console.print("[yellow]No answers collected. Nothing to save.[/yellow]")
                return False

            new_profile = asyncio.run(self.synthesize_profile(session))

            # Interactive feedback loop on synthesis
            while True:
                # Show preview
                self.console.print()
                self.console.print(
                    Panel(
                        new_profile,
                        title="[bold green]Draft Taste Profile[/bold green]",
                        border_style="green",
                    )
                )

                # Ask what to do
                self.console.print()
                action = questionary.select(
                    "What would you like to do?",
                    choices=[
                        questionary.Choice(
                            title=[
                                ("class:text", "Save this profile"),
                                ("class:text", "\n      "),
                                ("class:description", "Looks good - save it to taste.md"),
                            ],
                            value="save",
                        ),
                        questionary.Choice(
                            title=[
                                ("class:text", "Revise based on feedback"),
                                ("class:text", "\n      "),
                                ("class:description", "Tell Claude what to change or add"),
                            ],
                            value="revise",
                        ),
                        questionary.Choice(
                            title=[
                                ("class:text", "Preview recommendations"),
                                ("class:text", "\n      "),
                                ("class:description", "See what Claude would recommend with this profile"),
                            ],
                            value="preview",
                        ),
                        questionary.Choice(
                            title=[
                                ("class:text", "Discard and cancel"),
                                ("class:text", "\n      "),
                                ("class:description", "Exit without saving"),
                            ],
                            value="cancel",
                        ),
                    ],
                    style=PROFILE_STYLE,
                ).ask()

                if action is None or action == "cancel":
                    self.console.print("[yellow]Cancelled. No changes saved.[/yellow]")
                    return False

                if action == "save":
                    # Create backup of existing taste
                    taste_path = self.storage.taste_path
                    if taste_path.exists():
                        backup_path = taste_path.with_suffix(".md.bak")
                        backup_path.write_text(taste_path.read_text())
                        self.console.print(f"[dim]Backup saved to {backup_path}[/dim]")

                    # Save new profile
                    self.storage.save_taste(new_profile)
                    self.console.print("[green]✓ Profile saved![/green]")
                    return True

                if action == "revise":
                    # Get feedback from user
                    self.console.print()
                    feedback = questionary.text(
                        "What would you like to change?",
                        instruction="(Enter for newline, Esc+Enter to submit)",
                        style=PROFILE_STYLE,
                        multiline=True,
                    ).ask()

                    if feedback is None:
                        continue  # User cancelled, show menu again

                    if feedback.strip():
                        # Revise the profile
                        new_profile = asyncio.run(
                            self.revise_profile(new_profile, feedback)
                        )
                    continue  # Show updated profile

                if action == "preview":
                    # Generate preview recommendations
                    recommendations = asyncio.run(
                        self.preview_recommendations(new_profile)
                    )
                    self.console.print()
                    self.console.print(
                        Panel(
                            recommendations,
                            title="[bold cyan]Preview: What Claude Would Recommend[/bold cyan]",
                            border_style="cyan",
                        )
                    )
                    # Wait for user to read, then show menu again
                    self.console.print()
                    questionary.press_any_key_to_continue(
                        "Press any key to continue..."
                    ).ask()
                    continue

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Cancelled. No changes saved.[/yellow]")
            return False

    async def run(
        self,
        reset: bool = False,
        questions_per_batch: int = 4,
        max_options: int = 4,
    ) -> bool:
        """Run the interactive build session (async version).

        Note: This delegates to run_sync because questionary requires
        synchronous execution.

        Args:
            reset: Start fresh (ignore existing taste.md)
            questions_per_batch: Number of questions per batch
            max_options: Number of options per question

        Returns:
            True if profile was saved, False if cancelled
        """
        # questionary doesn't work well in async contexts, so just call sync version
        return self.run_sync(
            reset=reset,
            questions_per_batch=questions_per_batch,
            max_options=max_options,
        )

