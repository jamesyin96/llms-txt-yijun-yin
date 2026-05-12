from app.config import float_setting, int_setting
import importlib

import app.config as config


def test_int_setting_uses_positive_env_value(monkeypatch) -> None:
    monkeypatch.setenv("TEST_INT_SETTING", "12")

    assert int_setting("TEST_INT_SETTING", 5) == 12


def test_int_setting_falls_back_for_invalid_or_non_positive_values(monkeypatch) -> None:
    monkeypatch.setenv("TEST_INT_SETTING", "not-a-number")
    assert int_setting("TEST_INT_SETTING", 5) == 5

    monkeypatch.setenv("TEST_INT_SETTING", "0")
    assert int_setting("TEST_INT_SETTING", 5) == 5


def test_float_setting_uses_positive_env_value(monkeypatch) -> None:
    monkeypatch.setenv("TEST_FLOAT_SETTING", "12.5")

    assert float_setting("TEST_FLOAT_SETTING", 5.0) == 12.5


def test_float_setting_falls_back_for_invalid_or_non_positive_values(monkeypatch) -> None:
    monkeypatch.setenv("TEST_FLOAT_SETTING", "not-a-number")
    assert float_setting("TEST_FLOAT_SETTING", 5.0) == 5.0

    monkeypatch.setenv("TEST_FLOAT_SETTING", "-1")
    assert float_setting("TEST_FLOAT_SETTING", 5.0) == 5.0


def test_auto_refresh_settings_from_env(monkeypatch) -> None:
    monkeypatch.setenv("AUTO_REFRESH_LOOKBACK_HOURS", "24")
    monkeypatch.setenv("AUTO_REFRESH_POLL_INTERVAL_SECONDS", "7200")

    reloaded = importlib.reload(config)

    assert reloaded.AUTO_REFRESH_LOOKBACK_HOURS == 24
    assert reloaded.AUTO_REFRESH_POLL_INTERVAL_SECONDS == 7200
