from __future__ import annotations

import json
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
from urllib.error import HTTPError

from dispatch_optimizer.models import LocationRef
from dispatch_optimizer.providers import (
    CachedTravelTimeProvider,
    FallbackTravelTimeProvider,
    GoogleRoutesTravelTimeProvider,
    HaversineTravelTimeProvider,
)


class _FakeHTTPResponse:
    def __init__(self, payload: str):
        self._payload = payload.encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class GoogleRoutesTravelTimeProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.origin = LocationRef(address="Origin", lat=-37.8101, lng=144.9629)
        self.destination = LocationRef(address="Destination", lat=-37.8255, lng=145.0210)

    @staticmethod
    def _cache_path(test_name: str) -> Path:
        base = Path("tests/.tmp")
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{test_name}-{uuid4().hex}.json"

    def test_google_provider_returns_minutes_from_matrix_response(self) -> None:
        def fake_urlopen(request, timeout):  # noqa: ANN001
            self.assertGreater(timeout, 0)
            body = json.loads(request.data.decode("utf-8"))
            self.assertEqual("DRIVE", body["travelMode"])
            line = {"originIndex": 0, "destinationIndex": 0, "duration": "420s", "condition": "ROUTE_EXISTS"}
            return _FakeHTTPResponse(json.dumps(line))

        provider = GoogleRoutesTravelTimeProvider(
            api_key="test-key",
            departure_time_strategy="NONE",
            max_retries=0,
            backoff_seconds=0,
        )
        with patch("dispatch_optimizer.providers.urllib_request.urlopen", side_effect=fake_urlopen):
            minutes = provider.travel_minutes(self.origin, self.destination)

        self.assertEqual(7, minutes)
        self.assertEqual(1, provider.external_api_calls)

    def test_retryable_error_falls_back_to_haversine(self) -> None:
        provider = GoogleRoutesTravelTimeProvider(
            api_key="test-key",
            departure_time_strategy="NONE",
            max_retries=0,
            backoff_seconds=0,
        )
        cache_path = self._cache_path("retryable-fallback")
        chain = FallbackTravelTimeProvider(
            primary=CachedTravelTimeProvider(provider, cache_path),
            fallback=HaversineTravelTimeProvider(average_speed_kph=40, minimum_minutes=1),
        )
        with patch(
            "dispatch_optimizer.providers.urllib_request.urlopen",
            side_effect=HTTPError(url="x", code=503, msg="busy", hdrs=None, fp=None),
        ):
            minutes = chain.travel_minutes(self.origin, self.destination)

        self.assertGreater(minutes, 0)
        self.assertEqual(1, chain.fallback_count)
        self.assertEqual(1, chain.error_count_by_type["RETRYABLE"])

    def test_auth_error_logs_and_counts(self) -> None:
        provider = GoogleRoutesTravelTimeProvider(
            api_key="test-key",
            departure_time_strategy="NONE",
            max_retries=0,
            backoff_seconds=0,
        )
        cache_path = self._cache_path("auth-fallback")
        chain = FallbackTravelTimeProvider(
            primary=CachedTravelTimeProvider(provider, cache_path),
            fallback=HaversineTravelTimeProvider(average_speed_kph=40, minimum_minutes=1),
        )
        with (
            patch(
                "dispatch_optimizer.providers.urllib_request.urlopen",
                side_effect=HTTPError(url="x", code=403, msg="denied", hdrs=None, fp=None),
            ),
            self.assertLogs("dispatch_optimizer.providers", level="ERROR") as captured_logs,
        ):
            _ = chain.travel_minutes(self.origin, self.destination)

        self.assertEqual(1, chain.error_count_by_type["AUTH"])
        self.assertTrue(any("AUTH" in message for message in captured_logs.output))

    def test_missing_api_key_logs_config_error_and_falls_back(self) -> None:
        provider = GoogleRoutesTravelTimeProvider(
            api_key="",
            departure_time_strategy="NONE",
        )
        cache_path = self._cache_path("missing-key")
        chain = FallbackTravelTimeProvider(
            primary=CachedTravelTimeProvider(provider, cache_path),
            fallback=HaversineTravelTimeProvider(average_speed_kph=40, minimum_minutes=1),
        )
        with self.assertLogs("dispatch_optimizer.providers", level="ERROR") as captured_logs:
            minutes = chain.travel_minutes(self.origin, self.destination)

        self.assertGreater(minutes, 0)
        self.assertEqual(1, chain.error_count_by_type["CONFIG"])
        self.assertTrue(any("CONFIG" in message for message in captured_logs.output))

    def test_cached_provider_does_not_repeat_external_calls(self) -> None:
        call_counter = {"count": 0}

        def fake_urlopen(request, timeout):  # noqa: ANN001
            _ = request
            _ = timeout
            call_counter["count"] += 1
            line = {"originIndex": 0, "destinationIndex": 0, "duration": "180s", "condition": "ROUTE_EXISTS"}
            return _FakeHTTPResponse(json.dumps(line))

        provider = GoogleRoutesTravelTimeProvider(
            api_key="test-key",
            departure_time_strategy="NONE",
            max_retries=0,
            backoff_seconds=0,
        )
        cache_path = self._cache_path("cache-hit")
        cached = CachedTravelTimeProvider(provider, cache_path)
        with patch("dispatch_optimizer.providers.urllib_request.urlopen", side_effect=fake_urlopen):
            self.assertEqual(3, cached.travel_minutes(self.origin, self.destination))
            self.assertEqual(3, cached.travel_minutes(self.origin, self.destination))

        self.assertEqual(1, call_counter["count"])
        self.assertEqual(1, cached.cache_hits)
        self.assertEqual(1, cached.cache_misses)

    def test_cache_key_uses_rounded_coordinates_routing_and_departure_bucket(self) -> None:
        provider = GoogleRoutesTravelTimeProvider(
            api_key="test-key",
            routing_preference="TRAFFIC_AWARE",
            departure_time_strategy="CURRENT_BUCKET",
            coordinate_precision=4,
        )
        provider_optimal = GoogleRoutesTravelTimeProvider(
            api_key="test-key",
            routing_preference="TRAFFIC_AWARE_OPTIMAL",
            departure_time_strategy="CURRENT_BUCKET",
            coordinate_precision=4,
        )
        origin_same_coord = LocationRef(address="Different Origin Label", lat=self.origin.lat, lng=self.origin.lng)
        destination_same_coord = LocationRef(
            address="Different Destination Label",
            lat=self.destination.lat,
            lng=self.destination.lng,
        )

        with patch.object(provider, "_departure_bucket_key", return_value="100"):
            key_a = provider.cache_key(self.origin, self.destination)
            key_b = provider.cache_key(origin_same_coord, destination_same_coord)
        with patch.object(provider, "_departure_bucket_key", return_value="101"):
            key_c = provider.cache_key(self.origin, self.destination)
        with patch.object(provider_optimal, "_departure_bucket_key", return_value="100"):
            key_d = provider_optimal.cache_key(self.origin, self.destination)

        self.assertEqual(key_a, key_b)
        self.assertNotEqual(key_a, key_c)
        self.assertNotEqual(key_a, key_d)

    def test_prefetch_pairs_has_rate_limit_and_batching(self) -> None:
        def fake_urlopen(request, timeout):  # noqa: ANN001
            _ = timeout
            body = json.loads(request.data.decode("utf-8"))
            destinations = body["destinations"]
            lines = []
            for idx, _ in enumerate(destinations):
                lines.append(
                    json.dumps(
                        {
                            "originIndex": 0,
                            "destinationIndex": idx,
                            "duration": f"{(idx + 1) * 60}s",
                            "condition": "ROUTE_EXISTS",
                        }
                    )
                )
            return _FakeHTTPResponse("\n".join(lines))

        provider = GoogleRoutesTravelTimeProvider(
            api_key="test-key",
            departure_time_strategy="NONE",
            prefetch_max_pairs_total=3,
            prefetch_batch_size=2,
            max_retries=0,
            backoff_seconds=0,
        )
        destinations = [
            LocationRef(address=f"D{index}", lat=-37.82 + index * 0.001, lng=145.01 + index * 0.001)
            for index in range(6)
        ]
        pairs = [(self.origin, destination) for destination in destinations]
        with patch("dispatch_optimizer.providers.urllib_request.urlopen", side_effect=fake_urlopen):
            prefetched = provider.prefetch_pairs(pairs)

        self.assertEqual(3, len(prefetched))
        self.assertEqual(2, provider.external_api_calls)


if __name__ == "__main__":
    unittest.main()
