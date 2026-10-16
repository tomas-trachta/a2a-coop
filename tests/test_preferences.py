import json

import pytest

from a2a_coop import preferences


def test_preferences_live_next_to_the_coop_database(tmp_path):
    assert preferences.preferences_path(tmp_path / "coop.db") == tmp_path / "ui.json"


def test_missing_preferences_mean_light(tmp_path):
    assert preferences.load_appearance(tmp_path / "ui.json") == "light"


@pytest.mark.parametrize("content", ["{not json", "[]", '{"appearance": "sepia"}', '{"appearance": 3}'])
def test_unusable_preferences_mean_light(tmp_path, content):
    path = tmp_path / "ui.json"
    path.write_text(content, encoding="utf-8")

    assert preferences.load_appearance(path) == "light"


def test_saved_dark_is_loaded_back(tmp_path):
    path = tmp_path / "ui.json"

    preferences.save_appearance(path, "dark")

    assert preferences.load_appearance(path) == "dark"


def test_saving_keeps_other_settings_and_leaves_no_temporary_files(tmp_path):
    path = tmp_path / "ui.json"
    path.write_text(json.dumps({"appearance": "light", "zoom": 2}), encoding="utf-8")

    preferences.save_appearance(path, "dark")

    assert json.loads(path.read_text(encoding="utf-8")) == {"appearance": "dark", "zoom": 2}
    assert [entry.name for entry in tmp_path.iterdir()] == ["ui.json"]


def test_saving_creates_the_folder(tmp_path):
    path = tmp_path / "fresh" / "ui.json"

    preferences.save_appearance(path, "dark")

    assert preferences.load_appearance(path) == "dark"


def test_unknown_appearance_is_not_saved(tmp_path):
    with pytest.raises(ValueError):
        preferences.save_appearance(tmp_path / "ui.json", "sepia")

    assert not (tmp_path / "ui.json").exists()
