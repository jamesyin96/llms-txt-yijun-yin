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


def test_validation_rejects_non_h1_h2_headings() -> None:
    result = validate_llms_txt(
        "# Example\n\n## Key Pages\n\n- [Home](https://example.com/)\n\n### Extra\n"
    )

    assert not result.valid
    assert "Only H1 and H2 headings are allowed in llms.txt." in result.errors


def test_validation_rejects_non_link_content_inside_file_list_section() -> None:
    result = validate_llms_txt(
        "# Example\n\n## Key Pages\n\n- [Home](https://example.com/)\nThis should not be here\n"
    )

    assert not result.valid
    assert "Section 'Key Pages' may only contain markdown link list items per llmstxt.org." in result.errors


def test_validation_accepts_dash_without_space_in_link_list() -> None:
    result = validate_llms_txt("# Example\n\n## Key Pages\n\n-[Home](https://example.com/)\n")

    assert result.valid


def test_validation_accepts_relative_url_links() -> None:
    result = validate_llms_txt("# Example\n\n## Docs\n\n- [API](/docs/api.md): Relative path\n")

    assert result.valid


def test_validation_accepts_optional_info_before_sections() -> None:
    result = validate_llms_txt(
        "# Example\n\n> Short summary\n\nContext paragraph with details.\n\n- Bullet detail\n\n## Docs\n\n- [API](https://example.com/docs/api.md)\n"
    )

    assert result.valid
