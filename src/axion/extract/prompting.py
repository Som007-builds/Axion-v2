"""Versioned prompt loading and deterministic prompt rendering."""

from __future__ import annotations

from importlib import resources

from axion.extract.claims import PROMPT_VERSION, BaselineDocument


class PromptError(Exception):
    """Raised when a prompt version cannot be loaded."""


def load_prompt_template(version: str = PROMPT_VERSION) -> str:
    """Load a prompt from the package; prompts are files, not inline strings."""
    if not version.replace("-", "").replace("_", "").isalnum():
        raise PromptError(f"invalid prompt version {version!r}")
    try:
        path = resources.files("axion.extract").joinpath("prompts", f"{version}.md")
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise PromptError(f"prompt version {version!r} not found") from exc


def render_claim_prompt(
    document: BaselineDocument,
    *,
    version: str = PROMPT_VERSION,
    max_claims: int = 25,
) -> str:
    """Render the claim-extraction prompt with section headings and text."""
    if max_claims < 1:
        raise ValueError("max_claims must be at least 1")
    if not document.sections:
        raise ValueError("baseline document has no sections")
    template = load_prompt_template(version)
    try:
        return template.format(max_claims=max_claims, document=document.text)
    except (KeyError, IndexError) as exc:
        raise PromptError(f"prompt {version!r} has an unknown placeholder") from exc


__all__ = ["PromptError", "load_prompt_template", "render_claim_prompt"]
