"""Loader-based context sources.

LoaderSource calls a Python function to get content and injects it into the prompt.
This is the most common context source type, used for:
- Static files (taste.md, learnings.md)
- Dynamic content (history context, style guidance)
"""

import importlib
from typing import TYPE_CHECKING, Callable

from .base import ContextResult, ContextSource

if TYPE_CHECKING:
    from rich.console import Console
    from serendipity.storage import StorageManager


# Type alias for loader functions
# signature: (storage: StorageManager, options: dict) -> tuple[content: str, warnings: list[str]]
LoaderFunc = Callable[["StorageManager", dict], tuple[str, list[str]]]


class LoaderSource(ContextSource):
    """Context source that calls a Python function to get content.

    Config schema:
    ```yaml
    taste:
      type: loader
      enabled: true
      loader: serendipity.context_sources.builtins.file_loader
      prompt_hint: |
        <persistent_taste>
        {content}
        </persistent_taste>
      options:
        path: ~/.serendipity/taste.md
    ```
    """

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.loader_path = config.get("loader", "")
        self.options = config.get("options", {})
        self._loader_func: LoaderFunc | None = None

    def _get_loader_func(self) -> LoaderFunc:
        """Dynamically import and cache the loader function."""
        if self._loader_func is not None:
            return self._loader_func

        if not self.loader_path:
            raise ValueError(f"No loader path specified for source '{self.name}'")

        # Split module.path.func_name
        try:
            module_path, func_name = self.loader_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            self._loader_func = getattr(module, func_name)
        except (ValueError, ImportError, AttributeError) as e:
            raise ValueError(
                f"Failed to load '{self.loader_path}' for source '{self.name}': {e}"
            ) from e

        return self._loader_func

    async def check_ready(self, console: "Console") -> tuple[bool, str]:
        """Check if loader function is importable.

        Returns:
            (True, "") if loader can be imported, (False, error) otherwise
        """
        try:
            self._get_loader_func()
            return True, ""
        except ValueError as e:
            return False, str(e)

    async def load(self, storage: "StorageManager") -> ContextResult:
        """Call loader function and format result.

        Args:
            storage: StorageManager for accessing files/config

        Returns:
            ContextResult with content and formatted prompt section
        """
        try:
            loader_func = self._get_loader_func()
            content, warnings = loader_func(storage, self.options)
            prompt_section = self.format_prompt_section(content)
            return ContextResult(
                content=content,
                prompt_section=prompt_section,
                warnings=warnings,
            )
        except Exception as e:
            return ContextResult(
                content="",
                prompt_section="",
                warnings=[f"[{self.name}] Failed to load: {e}"],
            )
