from app.haos_entrypoint import (
    DEFAULT_NOTIFICATION_SERVICE,
    DEFAULT_WEATHER_ENTITY,
    build_runtime_env,
)


def _base_options():
    return {
        "service_account_file": "/homeassistant/Google/service_account.json",
        "spreadsheet_id": "sheet-id",
        "worksheet_name": "Confort thermique",
        "timezone": "Europe/Paris",
    }


def test_old_options_remain_compatible_with_new_optional_defaults() -> None:
    env = build_runtime_env(_base_options())
    assert env["THERMAL_WEATHER_ENTITY"] == DEFAULT_WEATHER_ENTITY
    assert env["THERMAL_NOTIFICATION_SERVICE"] == DEFAULT_NOTIFICATION_SERVICE


def test_explicit_weather_and_notification_targets_are_forwarded_to_runtime() -> None:
    options = _base_options()
    options["weather_entity"] = "weather.dammarie_les_lys"
    options["notification_service"] = "notify.mobile_app_phone"
    env = build_runtime_env(options)
    assert env["THERMAL_WEATHER_ENTITY"] == "weather.dammarie_les_lys"
    assert env["THERMAL_NOTIFICATION_SERVICE"] == "notify.mobile_app_phone"
