from app.haos_entrypoint import DEFAULT_WEATHER_ENTITY, build_runtime_env


def _base_options():
    return {
        "service_account_file": "/homeassistant/Google/service_account.json",
        "spreadsheet_id": "sheet-id",
        "worksheet_name": "Confort thermique",
        "timezone": "Europe/Paris",
    }


def test_dev7_options_remain_compatible_with_dev8_weather_default() -> None:
    env = build_runtime_env(_base_options())
    assert env["THERMAL_WEATHER_ENTITY"] == DEFAULT_WEATHER_ENTITY


def test_explicit_weather_entity_is_forwarded_to_runtime() -> None:
    options = _base_options()
    options["weather_entity"] = "weather.dammarie_les_lys"
    env = build_runtime_env(options)
    assert env["THERMAL_WEATHER_ENTITY"] == "weather.dammarie_les_lys"
