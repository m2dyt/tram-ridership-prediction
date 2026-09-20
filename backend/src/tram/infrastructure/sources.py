"""Read-only clients with fixed hosts, bounded responses and credential-safe errors."""

import math
from datetime import UTC, datetime

import httpx

from tram.domain.time import parse_time
from tram.infrastructure.contract import strict_json


def finite(value):
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite source value")
    return number


def coordinates(lon, lat):
    lon, lat = finite(lon), finite(lat)
    if lon is None or lat is None:
        return None
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError("Invalid coordinates")
    return [lon, lat]


def utc_epoch(value):
    return datetime.fromtimestamp(float(value), UTC).isoformat()


class ExternalSources:
    def __init__(self, weather_key="", timepad_token="", transport=None):
        self.weather_key, self.timepad_token, self.transport = weather_key, timepad_token, transport

    def get(self, url, params, headers=None):
        # New client per acquisition: no global sockets and no shared mutable credentials.
        with httpx.Client(  # noqa: SIM117
            timeout=httpx.Timeout(12, connect=5), transport=self.transport, follow_redirects=False
        ) as client:
            with client.stream(
                "GET",
                url,
                params=params,
                headers={"User-Agent": "TramResearch/0.1", **(headers or {})},
            ) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 5_000_000:
                        raise ValueError("Provider response exceeds 5 MB")
                return strict_json(body)

    def fetch(self, command):
        provider = command["provider"]
        kind = "weather" if provider in ("open-meteo", "weatherapi") else "events"
        try:
            result = {
                "open-meteo": self.open_meteo,
                "weatherapi": self.weatherapi,
                "kudago": self.kudago,
                "timepad": self.timepad,
            }[provider](command)
            return {
                "status": "succeeded",
                "kind": kind,
                "record_count": len(result["records"]),
                **result,
            }
        except (
            httpx.HTTPError,
            ValueError,
            KeyError,
            TypeError,
            OverflowError,
            AttributeError,
            IndexError,
        ) as error:
            # Never persist HTTP exception strings: request URLs can contain API keys.
            code = (
                f"http_{error.response.status_code}"
                if isinstance(error, httpx.HTTPStatusError)
                else type(error).__name__
            )
            return {
                "status": "unavailable",
                "kind": kind,
                "records": [],
                "record_count": 0,
                "warnings": ["Provider unavailable: " + code],
                "attribution": provider,
                "source_url": None,
            }

    def open_meteo(self, command):
        url = "https://api.open-meteo.com/v1/forecast"
        data = self.get(
            url,
            {
                "latitude": command["latitude"],
                "longitude": command["longitude"],
                "hourly": "temperature_2m,precipitation,wind_speed_10m",
                "forecast_days": 3,
                "timezone": "UTC",
                "timeformat": "unixtime",
            },
        )
        hourly = data["hourly"]
        rows = [
            {
                "time": utc_epoch(at),
                "coordinates": [command["longitude"], command["latitude"]],
                "temperature_c": finite(temp),
                "precipitation_mm": finite(rain),
                "wind_kmh": finite(wind),
            }
            for at, temp, rain, wind in zip(
                hourly["time"],
                hourly["temperature_2m"],
                hourly["precipitation"],
                hourly["wind_speed_10m"],
                strict=True,
            )
        ]
        return {
            "records": rows,
            "warnings": [
                "Forecast context; retrieval time is availability, not model initialization"
            ],
            "attribution": "Weather data by Open-Meteo.com (CC BY 4.0)",
            "source_url": "https://open-meteo.com/",
        }

    def weatherapi(self, command):
        if not self.weather_key:
            raise ValueError("WeatherAPI key is not configured")
        data = self.get(
            "https://api.weatherapi.com/v1/forecast.json",
            {
                "key": self.weather_key,
                "q": f"{command['latitude']},{command['longitude']}",
                "days": 3,
            },
        )
        rows = [
            {
                "time": utc_epoch(h["time_epoch"]),
                "coordinates": [command["longitude"], command["latitude"]],
                "temperature_c": finite(h["temp_c"]),
                "precipitation_mm": finite(h["precip_mm"]),
                "wind_kmh": finite(h["wind_kph"]),
            }
            for day in data["forecast"]["forecastday"]
            for h in day["hour"]
        ]
        return {
            "records": rows,
            "warnings": [],
            "attribution": "Powered by WeatherAPI.com",
            "source_url": "https://www.weatherapi.com/",
        }

    def kudago(self, command):
        data = self.get(
            "https://kudago.com/public-api/v1.4/events/",
            {
                "location": "msk",
                "page_size": 100,
                "fields": "id,title,dates,place,categories,site_url",
                "expand": "place,dates",
                "actual_since": int(datetime.fromisoformat(command["from"]).timestamp()),
                "actual_until": int(datetime.fromisoformat(command["to"]).timestamp()),
            },
        )
        rows = []
        for event in data["results"]:
            xy = (event.get("place") or {}).get("coords") or {}
            point = coordinates(xy.get("lon"), xy.get("lat"))
            for index, date in enumerate(event.get("dates") or []):
                if (
                    date.get("start") is None
                    or date.get("end") is None
                    or date["end"] <= date["start"]
                ):
                    continue
                rows.append(
                    {
                        "id": f"{event['id']}:{index}",
                        "title": event["title"],
                        "start": utc_epoch(date["start"]),
                        "end": utc_epoch(date["end"]),
                        "coordinates": point,
                        "source_url": event.get("site_url"),
                        "categories": event.get("categories") or [],
                    }
                )
        return {
            "records": rows,
            "warnings": [
                "Catalogue sample, not attendance; at most 100 events",
                *(["More provider pages exist"] if data.get("next") else []),
            ],
            "attribution": "KudaGo — links to event pages must be retained",
            "source_url": "https://kudago.com/msk/",
        }

    def timepad(self, command):
        headers = {"Authorization": "Bearer " + self.timepad_token} if self.timepad_token else {}
        data = self.get(
            "https://api.timepad.ru/v1/events",
            {
                "cities[]": "Москва",
                "limit": 100,
                "starts_at_min": command["from"],
                "starts_at_max": command["to"],
            },
            headers,
        )
        rows = []
        for event in data["values"]:
            start, end = event.get("starts_at"), event.get("ends_at")
            if not start or not end:
                continue
            start, end = parse_time(start), parse_time(end)
            if end <= start:
                continue
            rows.append(
                {
                    "id": str(event["id"]),
                    "title": event["name"],
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "coordinates": None,
                    "source_url": event.get("url"),
                    "categories": [],
                }
            )
        return {
            "records": rows,
            "warnings": [
                "Catalogue sample, not attendance; geocoding is not inferred",
                "At most 100 events",
            ],
            "attribution": "Timepad",
            "source_url": "https://timepad.ru/",
        }
