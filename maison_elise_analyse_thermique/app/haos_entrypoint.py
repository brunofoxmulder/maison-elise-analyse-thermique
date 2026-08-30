from __future__ import annotations

import json
import os
from pathlib import Path


DEFAULT_WEATHER_ENTITY = "weather.dammarie_les_lys"
DEFAULT_NOTIFICATION_SERVICE = ""


def build_runtime_env(options: dict) -> dict[str, str]:
    required = {
        "service_account_file": "THERMAL_GOOGLE_SERVICE_ACCOUNT_FILE",
        "spreadsheet_id": "THERMAL_SPREADSHEET_ID",
        "worksheet_name": "THERMAL_WORKSHEET_NAME",
        "timezone": "THERMAL_TIMEZONE",
    }
    env: dict[str, str] = {}
    for option_name, env_name in required.items():
        value = options.get(option_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"option HAOS manquante ou vide: {option_name}")
        env[env_name] = value.strip()

    weather_entity = options.get("weather_entity", DEFAULT_WEATHER_ENTITY)
    if not isinstance(weather_entity, str) or not weather_entity.strip():
        weather_entity = DEFAULT_WEATHER_ENTITY
    env["THERMAL_WEATHER_ENTITY"] = weather_entity.strip()

    notification_service = options.get(
        "notification_service", DEFAULT_NOTIFICATION_SERVICE
    )
    if not isinstance(notification_service, str):
        notification_service = DEFAULT_NOTIFICATION_SERVICE
    env["THERMAL_NOTIFICATION_SERVICE"] = notification_service.strip()
    return env


def configure_from_options(path: str = "/data/options.json") -> None:
    options_path = Path(path)
    options = json.loads(options_path.read_text(encoding="utf-8"))
    os.environ.update(build_runtime_env(options))


def main() -> None:
    configure_from_options()
    os.execvp(
        "uvicorn",
        ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8099"],
    )


if __name__ == "__main__":
    main()
