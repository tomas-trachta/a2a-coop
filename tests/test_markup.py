from a2a_coop import markup
from a2a_coop.markup import Line, Span


def kinds(body: str) -> list[tuple[str, str, int, bool]]:
    return [(line.kind, line.marker, line.level, line.gap) for line in markup.parse(body)]


def test_lists_headings_and_paragraphs_are_recognised():
    body = "# Plan\nIntro\n\n- first\n  - nested\n2. second\n   continues here"

    assert kinds(body) == [
        ("heading", "", 0, False),
        ("text", "", 0, False),
        ("item", "•", 0, True),
        ("item", "•", 1, False),
        ("item", "2.", 0, False),
        ("item", "2.", 0, False),
    ]
    assert markup.parse(body)[-1].continued


def test_inline_code_and_bold_become_spans():
    (line,) = markup.parse("Use `open_goal` **before** loading")

    assert line.spans == (Span("Use "), Span("open_goal", "code"), Span(" "), Span("before", "strong"), Span(" loading"))


def test_fenced_code_keeps_its_text_and_language():
    lines = markup.parse("Look:\n```Python\ndef f():\n\n    return 1\n```\nDone")

    assert lines[1] == Line("code", (Span("def f():\n\n    return 1", "code"),), gap=True, language="python")
    assert [line.kind for line in lines] == ["text", "code", "text"]


def test_unclosed_fence_still_shows_the_code():
    (line,) = markup.parse("```sql\nSELECT 1;")

    assert (line.kind, line.language, line.spans[0].text) == ("code", "sql", "SELECT 1;")


def test_fence_survives_backticks_inside_the_snippet():
    snippet = 'text = """\n```\n"""'
    (line,) = markup.parse(markup.fence(snippet, "python"))

    assert (line.language, line.spans[0].text) == ("python", snippet)
