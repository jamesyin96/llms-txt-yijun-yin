from app.services.html_parser import parse_html_document


ROOT_URL = "https://example.com/"
PAGE_URL = "https://example.com/docs/index.html"


def test_extracts_metadata_canonical_and_headings() -> None:
    result = parse_html_document(
        """
        <html>
          <head>
            <title> Docs Home </title>
            <meta name="description" content="  Helpful docs.  ">
            <link rel="canonical" href="/docs/">
          </head>
          <body>
            <h1>Documentation</h1>
            <h2>Getting Started</h2>
            <h2>Getting Started</h2>
            <h3>API</h3>
          </body>
        </html>
        """,
        page_url=PAGE_URL,
        root_url=ROOT_URL,
    )

    assert result.title == "Docs Home"
    assert result.description == "Helpful docs."
    assert result.canonical_url == "https://example.com/docs/"
    assert result.h1 == "Documentation"
    assert result.headings == ("Documentation", "Getting Started", "API")


def test_metadata_falls_back_to_open_graph_fields() -> None:
    result = parse_html_document(
        """
        <meta property="og:title" content="OG Title">
        <meta property="og:description" content="OG Description">
        """,
        page_url=PAGE_URL,
        root_url=ROOT_URL,
    )

    assert result.title == "OG Title"
    assert result.description == "OG Description"


def test_extracts_same_host_links_and_deduplicates_urls() -> None:
    result = parse_html_document(
        """
        <a href="/docs/intro#top">Intro</a>
        <a href="https://example.com/docs/intro">Intro Duplicate</a>
        <a href="/docs/search?q=api">Search</a>
        <a href="https://other.example.com/docs">External</a>
        <a href="mailto:hello@example.com">Email</a>
        """,
        page_url=PAGE_URL,
        root_url=ROOT_URL,
    )

    assert [link.url for link in result.links] == [
        "https://example.com/docs/intro",
        "https://example.com/docs/search?q=api",
    ]
    assert result.links[0].text == "Intro"
    assert result.links[1].text == "Search"


def test_link_text_falls_back_to_aria_title_and_nested_image_alt() -> None:
    result = parse_html_document(
        """
        <a href="/aria" aria-label="Aria Label"></a>
        <a href="/title" title="Title Label"></a>
        <a href="/image"><img src="/button.png" alt="Image Label"></a>
        """,
        page_url=PAGE_URL,
        root_url=ROOT_URL,
    )

    assert [(link.url, link.text) for link in result.links] == [
        ("https://example.com/aria", "Aria Label"),
        ("https://example.com/title", "Title Label"),
        ("https://example.com/image", "Image Label"),
    ]


def test_extracts_same_host_images_with_context() -> None:
    result = parse_html_document(
        """
        <img src="/media/chart.png" alt="Revenue chart" title="Chart" width="640" height="480">
        <img src="https://example.com/media/chart.png" alt="Duplicate chart">
        <img src="https://cdn.example.net/media/photo.jpg" alt="External">
        <img src="data:image/png;base64,abc" alt="Inline">
        <img src="/media/flexible.png" width="100%">
        """,
        page_url=PAGE_URL,
        root_url=ROOT_URL,
    )

    assert [(image.url, image.alt, image.title, image.width, image.height) for image in result.images] == [
        ("https://example.com/media/chart.png", "Revenue chart", "Chart", 640, 480),
        ("https://example.com/media/flexible.png", "", "", None, None),
    ]


def test_ignores_cross_host_canonical_url() -> None:
    result = parse_html_document(
        '<link rel="canonical" href="https://other.example.com/docs/">',
        page_url=PAGE_URL,
        root_url=ROOT_URL,
    )

    assert result.canonical_url is None


def test_handles_malformed_html() -> None:
    result = parse_html_document(
        "<html><title>Broken<title><body><h1>Hello<a href='/ok'>OK",
        page_url=PAGE_URL,
        root_url=ROOT_URL,
    )

    assert "Broken" in result.title
    assert result.links[0].url == "https://example.com/ok"

