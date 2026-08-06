import os
from pathlib import Path
import pytest

from app.config import Settings
from app.config_loader import load_toml_settings


def test_toml_loading_defaults(tmp_path):
    defaults = tmp_path / "defaults.toml"
    defaults.write_text("""
[app]
name = "TestApp"
log_level = "DEBUG"
""")
    dev = tmp_path / "development.toml"
    dev.write_text("""
[app]
debug = true
""")
    res = load_toml_settings(config_dir=tmp_path, app_env="development")
    assert res["app_name"] == "TestApp"
    assert res["log_level"] == "DEBUG"
    assert res["debug"] is True


def test_toml_environment_overlays(tmp_path):
    defaults = tmp_path / "defaults.toml"
    defaults.write_text("""
[recommendations]
final_count = 3
""")
    prod = tmp_path / "production.toml"
    prod.write_text("""
[recommendations]
final_count = 5
""")
    res_prod = load_toml_settings(config_dir=tmp_path, app_env="production")
    assert res_prod["recommendation_final_count"] == 5


def test_toml_invalid_app_env(tmp_path):
    with pytest.raises(ValueError, match="Unsupported APP_ENV"):
        load_toml_settings(config_dir=tmp_path, app_env="invalid_environment")


def test_toml_invalid_toml_file(tmp_path):
    defaults = tmp_path / "defaults.toml"
    defaults.write_text("[app\ninvalid_toml = ")
    dev = tmp_path / "development.toml"
    dev.write_text("")
    with pytest.raises(ValueError, match="Malformed TOML file"):
        load_toml_settings(config_dir=tmp_path, app_env="development")


def test_precedence_env_var_overrides_toml(monkeypatch):
    monkeypatch.setenv("RECOMMENDATION_FINAL_COUNT", "4")
    settings = Settings(app_env="development")
    assert settings.recommendation_final_count == 4


def test_constructor_kwargs_override_all():
    settings = Settings(app_env="test", recommendation_final_count=7)
    assert settings.recommendation_final_count == 7


def test_local_toml_override_in_development(tmp_path):
    defaults = tmp_path / "defaults.toml"
    defaults.write_text("[app]\nname = 'DefaultName'\n")
    dev = tmp_path / "development.toml"
    dev.write_text("[app]\nname = 'DevName'\n")
    local = tmp_path / "local.toml"
    local.write_text("[app]\nname = 'LocalName'\n")

    res_dev = load_toml_settings(config_dir=tmp_path, app_env="development")
    assert res_dev["app_name"] == "LocalName"

    res_prod = load_toml_settings(config_dir=tmp_path, app_env="production")
    assert res_prod.get("app_name") == "DefaultName"


def test_parsed_boolean_and_integer_env_vars(monkeypatch):
    monkeypatch.setenv("RECOMMENDATIONS_ENABLED", "false")
    monkeypatch.setenv("VECTOR_SIZE", "768")
    settings = Settings(app_env="test")
    assert settings.recommendations_enabled is False
    assert settings.vector_size == 768
