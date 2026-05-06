from app.services.formatter import LlmResource, render_llms_txt, validate_llms_txt


def test_rendered_llms_txt_passes_quality_gate() -> None:
    content = render_llms_txt(
        "Example",
        "Example summary.",
        [
            LlmResource(
                title="Docs",
                url="https://example.com/docs",
                description="Documentation.",
                section="Documentation",
            )
        ],
    )

    result = validate_llms_txt(content)

    assert result.valid
    assert result.errors == ()


def test_validation_requires_one_h1_at_start() -> None:
    result = validate_llms_txt("Intro\n# Example\n\n## Key Pages\n\n- [Home](https://example.com/)\n")

    assert not result.valid
    assert "Generated file must start with the H1 title." in result.errors


def test_validation_requires_section_and_markdown_link() -> None:
    result = validate_llms_txt("# Example\n\n> Summary\n")

    assert not result.valid
    assert "Generated file must contain at least one H2 section." in result.errors
    assert "Generated file must contain at least one markdown link item." in result.errors


def test_validation_requires_links_inside_each_section() -> None:
    result = validate_llms_txt(
        "# Example\n\n## Empty Section\n\n## Key Pages\n\n- [Home](https://example.com/)\n"
    )

    assert not result.valid
    assert "Section 'Empty Section' must contain at least one markdown link item." in result.errors

