"""Tests for CLI skin engine."""

from cli.skin import (
    get_active_skin_name,
    init_skin_from_config,
    list_skins,
    load_skin,
    set_active_skin,
)
from config.models import EmperorConfig, UiConfig


def test_list_skins_includes_builtins():
    names = {s["name"] for s in list_skins()}
    assert "default" in names
    assert "slate" in names
    assert "mono" in names


def test_load_skin_slate():
    skin = load_skin("slate")
    assert skin.name == "slate"
    assert skin.get_color("banner_title")


def test_set_active_skin():
    set_active_skin("mono", persist=False)
    assert get_active_skin_name() == "mono"
    set_active_skin("default", persist=False)


def test_init_skin_from_config():
    cfg = EmperorConfig(ui=UiConfig(skin="slate"))
    skin = init_skin_from_config(cfg)
    assert skin.name == "slate"
    set_active_skin("default", persist=False)
