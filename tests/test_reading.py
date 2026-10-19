from pygments.lexers import get_lexer_by_name

from a2a_coop import markup, reading


def test_every_offered_language_has_a_highlighter():
    languages = [name for name in reading.CODE_LANGUAGES.values() if name]

    assert len(languages) == 30
    assert all(get_lexer_by_name(name) for name in languages)


def test_code_blocks_are_split_into_rows_with_padded_edges():
    (line,) = markup.parse(markup.fence("def f():\n\n    return 1", "python"))
    segments = reading.code_block(line, ("body",))
    rows = "".join(content for content, tags in segments).split("\n")

    assert rows == ["def f():", "", "    return 1", ""]
    assert "body-code-first" in segments[0][1] and "body-code-last" not in segments[0][1]
    assert "body-code-last" in segments[-1][1]
    assert any("syntax:keyword" in tags for content, tags in segments if content == "def")


def test_plain_text_code_is_not_highlighted():
    (line,) = markup.parse(markup.fence("SELECT 1;"))
    segments = reading.code_block(line, ("body",))

    assert segments == [
        ("SELECT 1;", ("body", "body-code-block", "body-code-first", "body-code-last")),
        ("\n", ("body", "body-code-block", "body-code-first", "body-code-last")),
    ]
