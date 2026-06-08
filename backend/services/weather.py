"""Weather service — fetches current conditions from open-meteo.com.

No API key required. Latitude/longitude are configurable via environment
variables (defaults to Lisbon). Returns a compact string like
'22°C, partly cloudy, 14 km/h wind' or an empty string on any failure
so callers can include it unconditionally.
"""

from __future__ import annotations

import logging
import os

import httpx

_API = "https://api.open-meteo.com/v1/forecast"
_log = logging.getLogger(__name__)

# WMO weather interpretation codes (subset used in forecasts)
_WMO: dict[int, str] = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "icy fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "rain showers",
    81: "heavy showers",
    82: "violent showers",
    85: "snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm w/ hail",
    99: "heavy thunderstorm",
}


async def current(lat: str | None = None, lon: str | None = None) -> str:
    """Return a compact current-conditions string or '' on failure.

    ``lat`` and ``lon`` override the env-var defaults, allowing per-request
    location (e.g. from the frontend settings panel).
    """
    lat = lat or os.getenv("WEATHER_LAT", "38.71")
    lon = lon or os.getenv("WEATHER_LON", "-9.14")
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(
                _API,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,weathercode,windspeed_10m",
                    "wind_speed_unit": "kmh",
                    "timezone": "auto",
                },
            )
            r.raise_for_status()
            c = r.json().get("current", {})
            temp = c.get("temperature_2m")
            if temp is None:
                return ""
            parts: list[str] = [f"{temp:.0f}°C"]
            desc = _WMO.get(int(c.get("weathercode", -1)), "")
            if desc:
                parts.append(desc)
            wind = c.get("windspeed_10m")
            if wind is not None and float(wind) >= 10:
                parts.append(f"{wind:.0f} km/h wind")
            return ", ".join(parts)
    except Exception:
        _log.debug("weather.current() failed", exc_info=True)
        return ""
