import json
from datetime import timedelta

import httpx
import pytest
from tram.infrastructure.geo_import import read_geojson
from tram.infrastructure.sources import ExternalSources
from tram_ml.context import context_features

from tests.support import NOW
from tests.test_api import api as api
from tests.test_api import checked


def command(provider="open-meteo"):
    return {
        "provider": provider,
        "latitude": 55.75,
        "longitude": 37.62,
        "from": NOW.isoformat(),
        "to": (NOW + timedelta(days=2)).isoformat(),
    }


def test_weather_normalization_and_credentials_redacted():
    calls = []

    def response(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "hourly": {
                    "time": [int(NOW.timestamp())],
                    "temperature_2m": [12],
                    "precipitation": [0.2],
                    "wind_speed_10m": [8],
                }
            },
        )

    data = ExternalSources(transport=httpx.MockTransport(response)).fetch(command())
    assert data["records"][0]["temperature_c"] == 12
    assert calls[0].url.params["timeformat"] == "unixtime"

    def denied(request):
        return httpx.Response(403, text="secret-key-is-here")

    failure = ExternalSources(
        weather_key="secret-key-is-here", transport=httpx.MockTransport(denied)
    ).fetch(command("weatherapi"))
    assert failure["status"] == "unavailable"
    assert "secret-key" not in json.dumps(failure)
    assert failure["records"] == []


def test_kudago_occurrences_and_missing_coordinates():
    def response(request):
        return httpx.Response(
            200,
            json={
                "next": "https://example.invalid/next",
                "results": [
                    {
                        "id": 1,
                        "title": "Festival",
                        "dates": [{"start": 100, "end": 200}],
                        "place": None,
                        "site_url": "https://kudago.com/msk/event/test",
                        "categories": [],
                    }
                ],
            },
        )

    data = ExternalSources(transport=httpx.MockTransport(response)).fetch(command("kudago"))
    assert data["records"][0]["coordinates"] is None
    assert "More provider pages exist" in data["warnings"]


def test_context_excludes_later_snapshot_and_uses_latest_known_version():
    def snapshot(identity, available, temperature):
        return {
            "id": identity,
            "provider": "open-meteo",
            "status": "succeeded",
            "kind": "weather",
            "available_at": available.isoformat(),
            "records": [
                {
                    "time": NOW.isoformat(),
                    "coordinates": [37.62, 55.75],
                    "temperature_c": temperature,
                }
            ],
        }

    result = context_features(
        [
            snapshot("older", NOW - timedelta(hours=2), 10),
            snapshot("known", NOW - timedelta(hours=1), 12),
            snapshot("future", NOW + timedelta(seconds=1), 99),
        ],
        NOW,
        NOW,
        [37.62, 55.75],
    )
    assert result["weather"]["temperature_c"] == 12
    assert result["snapshot_ids"] == ["known"]


def test_geo_import_rejects_bad_coordinates_and_preserves_provenance(tmp_path):
    path = tmp_path / "export.geojson"
    feature = {
        "type": "Feature",
        "properties": {"id": "station-1", "name": "Station"},
        "geometry": {"type": "Point", "coordinates": [37.6, 55.7]},
    }

    def write():
        path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}))

    write()
    data = read_geojson(path, "https://data.mos.ru/opendata/example", "metro", "id", "name")
    assert data["records"][0]["category"] == "metro"
    feature["geometry"]["coordinates"] = [37.6, 155.7]
    write()
    with pytest.raises(ValueError):
        read_geojson(path, "https://data.mos.ru/opendata/example", "metro", "id", "name")


def test_context_api_retains_unavailable_snapshot(api):
    response = checked(
        api, "POST", "/context/refresh", role="operator", json=command("weatherapi")
    ).json()
    assert response["status"] == "unavailable"
    checked(api, "GET", "/context/snapshots/" + response["id"])
    assert checked(api, "GET", "/context/snapshots").json()["items"][0]["record_count"] == 0
    checked(
        api,
        "POST",
        "/context/refresh",
        role="operator",
        json={**command(), "to": NOW.isoformat()},
        status=422,
    )


def test_timepad_normalizes_offsets_and_rejects_naive_provider_times():
    event = {
        "id": 42,
        "name": "Local event",
        "starts_at": "2026-09-20T12:00:00+03:00",
        "ends_at": "2026-09-20T13:00:00+03:00",
        "url": "https://timepad.ru/event/42",
    }

    def response(request):
        assert request.url.params["cities[]"] == "Москва"
        return httpx.Response(200, json={"values": [event]})

    provider = ExternalSources(transport=httpx.MockTransport(response))
    result = provider.fetch(command("timepad"))
    assert result["records"][0]["start"] == "2026-09-20T09:00:00+00:00"
    event["starts_at"] = "2026-09-20T12:00:00"
    assert provider.fetch(command("timepad"))["status"] == "unavailable"
