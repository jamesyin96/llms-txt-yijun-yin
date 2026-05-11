"""Markdown formatter for the generated `llms.txt` file.

This module stays independent from crawling and persistence so the llms.txt
format can be tested in isolation and updated easily if the spec evolves.
"""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class LlmResource:
    """A resource link that should appear in the generated llms.txt output."""

    title: str
    url: str
    description: str
    section: str = "Key Pages"


@dataclass(frozen=True)
class LlmValidationResult:
    """Validation result for generated llms.txt markdown."""

    valid: bool
    errors: tuple[str, ...] = ()


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


def validate_llms_txt(content: str) -> LlmValidationResult:
    """Validate generated llms.txt content against the llmstxt.org core shape.

    Practical checks implemented here:
    - exactly one H1, and it must be first
    - zero or more H2 sections
    - only H1/H2 headings are allowed
    - each H2 section is a file list made of markdown link list items
    """

    errors: list[str] = []
    lines = [line.rstrip() for line in content.splitlines()]
    non_empty_lines = [line for line in lines if line.strip()]

    if not non_empty_lines:
        errors.append("Generated file is empty.")
        return LlmValidationResult(False, tuple(errors))

    h1_lines = [line for line in non_empty_lines if line.startswith("# ")]
    if len(h1_lines) != 1:
        errors.append("Generated file must contain exactly one H1 title.")
    elif non_empty_lines[0] != h1_lines[0]:
        errors.append("Generated file must start with the H1 title.")

    # llmstxt.org examples permit '-' with/without a space and do not require
    # absolute HTTP(S) links; relative links are common in practice.
    link_pattern = re.compile(r"^-\s*\[[^\]]+\]\(([^)\s]+)\)(?::\s*.+)?$")

    section_indices = [index for index, line in enumerate(lines) if line.startswith("## ")]
    if not section_indices:
        errors.append("Generated file must contain at least one H2 section.")

    if not any(link_pattern.match(line) for line in lines):
        errors.append("Generated file must contain at least one markdown link item.")

    for line in non_empty_lines:
        if line.startswith("#") and not (line.startswith("# ") or line.startswith("## ")):
            errors.append("Only H1 and H2 headings are allowed in llms.txt.")
            break

    for section_index in section_indices:
        section_title = lines[section_index].removeprefix("## ").strip()
        if not section_title:
            errors.append("Section headings must not be empty.")

        next_section = next(
            (index for index in section_indices if index > section_index),
            len(lines),
        )
        section_body = lines[section_index + 1 : next_section]
        section_non_empty = [line.strip() for line in section_body if line.strip()]

        if not any(link_pattern.match(line) for line in section_body):
            errors.append(f"Section '{section_title}' must contain at least one markdown link item.")
            continue

        if any(not link_pattern.match(line) for line in section_non_empty):
            errors.append(
                f"Section '{section_title}' may only contain markdown link list items per llmstxt.org."
            )

    return LlmValidationResult(valid=not errors, errors=tuple(errors))


def _clean_inline_text(value: str) -> str:
    """Collapse whitespace and avoid markdown link bracket collisions."""

    return " ".join(value.replace("[", "(").replace("]", ")").split())
