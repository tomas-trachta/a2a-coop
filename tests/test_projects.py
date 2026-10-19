import pytest

from a2a_coop import projects
from a2a_coop.errors import CoopError


def test_default_project_comes_first_and_uses_the_home_database(tmp_path):
    projects.add_project(tmp_path, "Zeta")
    projects.add_project(tmp_path, "alpha", folder="/work/alpha")

    listed = projects.list_projects(tmp_path)

    assert [project.name for project in listed] == ["Default", "alpha", "Zeta"]
    assert listed[0].db == tmp_path / "coop.db"
    assert listed[1].db == tmp_path / "projects" / "alpha" / "coop.db"
    assert listed[1].folder == "/work/alpha"


def test_projects_are_found_by_name_or_database(tmp_path):
    shop = projects.add_project(tmp_path, "Web  shop")

    assert shop.name == "Web shop"
    assert projects.get_project(tmp_path, "web shop") == shop
    assert projects.project_for_db(tmp_path, shop.db) == shop
    assert projects.project_for_db(tmp_path, tmp_path / "elsewhere.db") is None


@pytest.mark.parametrize("name", ["", "   ", "default", "Shop", "x" * 41])
def test_invalid_or_duplicate_names_are_refused(tmp_path, name):
    projects.add_project(tmp_path, "Shop")

    with pytest.raises(CoopError):
        projects.add_project(tmp_path, name)


def test_similar_names_get_separate_databases(tmp_path):
    first = projects.add_project(tmp_path, "Web shop")
    second = projects.add_project(tmp_path, "web-shop!")

    assert first.db != second.db


def test_unknown_project_names_the_known_ones(tmp_path):
    projects.add_project(tmp_path, "Shop")

    with pytest.raises(CoopError, match="Default, Shop"):
        projects.get_project(tmp_path, "Blog")


def test_a_damaged_registry_leaves_only_the_default(tmp_path):
    projects.registry_path(tmp_path).write_text("{not json", encoding="utf-8")

    assert [project.name for project in projects.list_projects(tmp_path)] == ["Default"]
