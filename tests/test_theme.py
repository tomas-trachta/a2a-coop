import pytest

from a2a_coop import theme

READABLE = 4.5
PALETTES = pytest.mark.parametrize("palette", [theme.LIGHT, theme.DARK], ids=["light", "dark"])


def readable_pairs(palette: theme.Palette) -> dict[str, tuple[str, str]]:
    return {
        "text on surface": (palette.text, palette.surface),
        "text on background": (palette.text, palette.background),
        "secondary on surface": (palette.secondary, palette.surface),
        "secondary on background": (palette.secondary, palette.background),
        "listening": (palette.success, palette.surface),
        "busy": (palette.warning, palette.surface),
        "stale": (palette.error, palette.surface),
        "error notice": (palette.error, palette.background),
        "question heading": (palette.warning, palette.question_background),
        "question text": (palette.text, palette.question_background),
        "primary button": (palette.on_primary, palette.primary),
        "selected row": (palette.selected_text, palette.selected),
        "selected tab": (palette.primary, palette.surface),
        "user": (palette.user, palette.surface),
        "everyone": (palette.everyone, palette.surface),
    }


@PALETTES
def test_text_and_status_colors_are_readable(palette):
    unreadable = {
        name: round(theme.contrast(*pair), 2)
        for name, pair in readable_pairs(palette).items()
        if theme.contrast(*pair) < READABLE
    }

    assert unreadable == {}


@PALETTES
def test_agent_identities_are_readable_on_cards(palette):
    colors = [theme.identity_color(palette, index) for index in range(24)]

    assert min(theme.contrast(color, palette.surface) for color in colors) >= READABLE


def test_light_and_dark_share_identity_slots():
    assert len(theme.LIGHT.identities) == len(theme.DARK.identities) == 12
    assert theme.LIGHT.on_primary == "#FFFFFF"
    assert theme.DARK.on_primary != theme.DARK.surface


def test_contrast_matches_the_wcag_formula():
    assert theme.contrast("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert theme.contrast("#FFFFFF", "#FFFFFF") == pytest.approx(1.0)
