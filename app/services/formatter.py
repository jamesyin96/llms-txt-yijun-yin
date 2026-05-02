"""Markdown formatter for the generated `llms.txt` file.

This module stays independent from crawling and persistence so the llms.txt
format can be tested in isolation and updated easily if the spec evolves.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LlmResource:
    """A resource link that should appear in the generated llms.txt output."""

    title: str
    url: str
    description: str
    section: str = "Key Pages"


def render_llms_txt(site_name: str, summary: str, resources: list[LlmResource]) -> str:
    """Render site metadata and grouped resources into llms.txt markdown."""

    lines = [f"# {site_name.strip() or 'Website'}", ""]

    if summary:
        lines.extend([f"> {summary.strip()}", ""])

    grouped: dict[str, list[LlmResource]] = {}
    for resource in resources:
        grouped.setdefault(resource.section or "Key Pages", []).append(resource)

    for section, section_resources in grouped.items():
        lines.extend([f"## {section}", ""])
        for resource in section_resources:
            title = _clean_inline_text(resource.title) or resource.url
            description = _clean_inline_text(resource.description)
            suffix = f": {description}" if description else ""
            lines.append(f"- [{title}]({resource.url}){suffix}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _clean_inline_text(value: str) -> str:
    """Collapse whitespace and avoid markdown link bracket collisions."""

    return " ".join(value.replace("[", "(").replace("]", ")").split())
