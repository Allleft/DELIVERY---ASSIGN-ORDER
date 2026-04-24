from __future__ import annotations

import json
import logging
import math
import os
import socket
import time
from enum import Enum
from pathlib import Path
from typing import Any, Protocol
from urllib import error as urllib_error
from urllib import request as urllib_request

from .models import LocationRef


class Geocoder(Protocol):
    def geocode(self, address: str) -> LocationRef | None:
        ...


class TravelTimeProvider(Protocol):
    def travel_minutes(self, origin: LocationRef, destination: LocationRef) -> int:
        ...


class TravelTimeErrorType(str, Enum):
    CONFIG = "CONFIG"
    AUTH = "AUTH"
    RETRYABLE = "RETRYABLE"
    NON_RETRYABLE = "NON_RETRYABLE"


class TravelTimeProviderError(RuntimeError):
    def __init__(
        self,
        error_type: TravelTimeErrorType,
        message: str,
        status_code: int | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.status_code = status_code
        self.cause = cause


class StaticGeocoder:
    def __init__(self, mapping: dict[str, tuple[float, float]]):
        self.mapping = mapping

    def geocode(self, address: str) -> LocationRef | None:
        point = self.mapping.get(address)
        if point is None:
            return None
        return LocationRef(address=address, lat=point[0], lng=point[1])


class HaversineTravelTimeProvider:
    def __init__(self, average_speed_kph: float = 35.0, minimum_minutes: int = 3):
        self.average_speed_kph = average_speed_kph
        self.minimum_minutes = minimum_minutes

    def travel_minutes(self, origin: LocationRef, destination: LocationRef) -> int:
        distance_km = self._haversine_km(origin.lat, origin.lng, destination.lat, destination.lng)
        if distance_km == 0:
            return 0
        raw_minutes = math.ceil((distance_km / self.average_speed_kph) * 60)
        return max(raw_minutes, self.minimum_minutes)

    @staticmethod
    def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        radius_km = 6371.0
        lat1_r = math.radians(lat1)
        lat2_r = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lng = math.radians(lng2 - lng1)

        a = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(delta_lng / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return radius_km * c


class DictTravelTimeProvider:
    def __init__(self, mapping: dict[tuple[str, str], int], default_minutes: int = 30):
        self.mapping = mapping
        self.default_minutes = default_minutes

    def travel_minutes(self, origin: LocationRef, destination: LocationRef) -> int:
        if (origin.address, destination.address) in self.mapping:
            return self.mapping[(origin.address, destination.address)]
        if (destination.address, origin.address) in self.mapping:
            return self.mapping[(destination.address, origin.address)]
        return self.default_minutes


class CachedTravelTimeProvider:
    def __init__(self, delegate: TravelTimeProvider, cache_path: str | Path):
        self.delegate = delegate
        self.cache_path = Path(cache_path)
        self._cache = self._load_cache()
        self.cache_hits = 0
        self.cache_misses = 0

    def travel_minutes(self, origin: LocationRef, destination: LocationRef) -> int:
        key = self._key(origin, destination)
        if key in self._cache:
            self.cache_hits += 1
            return int(self._cache[key])
        self.cache_misses += 1
        self._cache[key] = int(self.delegate.travel_minutes(origin, destination))
        self._persist()
        return int(self._cache[key])

    def prefetch_pairs(self, pairs: list[tuple[LocationRef, LocationRef]]) -> dict[str, int]:
        unique_pairs: list[tuple[LocationRef, LocationRef]] = []
        seen_keys: set[str] = set()
        for origin, destination in pairs:
            key = self._key(origin, destination)
            if key in seen_keys or key in self._cache:
                continue
            seen_keys.add(key)
            unique_pairs.append((origin, destination))

        if not unique_pairs:
            return {}

        prefetched: dict[str, int] = {}
        delegate_prefetch = getattr(self.delegate, "prefetch_pairs", None)
        if callable(delegate_prefetch):
            delegate_result = delegate_prefetch(unique_pairs)
            if isinstance(delegate_result, dict):
                for key, value in delegate_result.items():
                    self._cache[key] = int(value)
                    prefetched[key] = int(value)
        else:
            for origin, destination in unique_pairs:
                key = self._key(origin, destination)
                self._cache[key] = int(self.delegate.travel_minutes(origin, destination))
                prefetched[key] = int(self._cache[key])

        if prefetched:
            self._persist()
        return prefetched

    def _load_cache(self) -> dict[str, int]:
        if not self.cache_path.exists():
            return {}
        return json.loads(self.cache_path.read_text(encoding="utf-8"))

    def _persist(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self._cache, indent=2), encoding="utf-8")

    def _key(self, origin: LocationRef, destination: LocationRef) -> str:
        cache_key_fn = getattr(self.delegate, "cache_key", None)
        if callable(cache_key_fn):
            return str(cache_key_fn(origin, destination))
        return f"{origin.address}::{destination.address}"

    def stats(self) -> dict[str, Any]:
        delegate_stats_fn = getattr(self.delegate, "stats", None)
        delegate_stats = delegate_stats_fn() if callable(delegate_stats_fn) else {}
        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "delegate": delegate_stats,
        }


class GoogleRoutesTravelTimeProvider:
    DEFAULT_BASE_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
    DEFAULT_FIELD_MASK = "originIndex,destinationIndex,duration,status,condition"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        routing_preference: str = "TRAFFIC_AWARE",
        departure_time_strategy: str = "CURRENT_BUCKET",
        departure_time_bucket_minutes: int = 15,
        request_timeout_seconds: float = 8.0,
        max_retries: int = 2,
        backoff_seconds: float = 0.5,
        coordinate_precision: int = 5,
        prefetch_max_pairs_total: int = 120,
        prefetch_batch_size: int = 25,
    ):
        self.api_key = (api_key or os.getenv("GOOGLE_ROUTES_API_KEY", "")).strip()
        self.base_url = (base_url or self.DEFAULT_BASE_URL).strip()
        self.routing_preference = routing_preference.strip().upper()
        self.departure_time_strategy = departure_time_strategy.strip().upper()
        self.departure_time_bucket_minutes = max(int(departure_time_bucket_minutes), 1)
        self.request_timeout_seconds = max(float(request_timeout_seconds), 1.0)
        self.max_retries = max(int(max_retries), 0)
        self.backoff_seconds = max(float(backoff_seconds), 0.0)
        self.coordinate_precision = max(int(coordinate_precision), 0)
        self.prefetch_max_pairs_total = max(int(prefetch_max_pairs_total), 0)
        self.prefetch_batch_size = max(int(prefetch_batch_size), 1)
        self.external_api_calls = 0
        self.error_count_by_type: dict[str, int] = {
            error_type.value: 0 for error_type in TravelTimeErrorType
        }
        self._logger = logging.getLogger("dispatch_optimizer.providers")

    def travel_minutes(self, origin: LocationRef, destination: LocationRef) -> int:
        self._validate_configuration()
        entries = self._request_matrix(origins=[origin], destinations=[destination])
        duration_seconds = self._extract_duration(entries, origin_index=0, destination_index=0)
        return self._seconds_to_minutes(duration_seconds)

    def prefetch_pairs(self, pairs: list[tuple[LocationRef, LocationRef]]) -> dict[str, int]:
        if not pairs or self.prefetch_max_pairs_total <= 0:
            return {}
        self._validate_configuration()
        trimmed_pairs = pairs[: self.prefetch_max_pairs_total]
        if len(pairs) > self.prefetch_max_pairs_total:
            self._logger.warning(
                "Google Routes prefetch truncated from %s to %s pairs.",
                len(pairs),
                len(trimmed_pairs),
            )

        grouped: dict[str, tuple[LocationRef, list[LocationRef]]] = {}
        for origin, destination in trimmed_pairs:
            origin_key = self._location_signature(origin)
            if origin_key not in grouped:
                grouped[origin_key] = (origin, [])
            grouped[origin_key][1].append(destination)

        prefetched: dict[str, int] = {}
        for origin, destinations in grouped.values():
            for chunk_start in range(0, len(destinations), self.prefetch_batch_size):
                destination_chunk = destinations[chunk_start : chunk_start + self.prefetch_batch_size]
                try:
                    entries = self._request_matrix(origins=[origin], destinations=destination_chunk)
                except TravelTimeProviderError as exc:
                    self._logger.warning(
                        "Google Routes prefetch degraded for origin %s: %s",
                        origin.address,
                        exc,
                    )
                    continue
                for destination_index, destination in enumerate(destination_chunk):
                    seconds = self._extract_duration(entries, origin_index=0, destination_index=destination_index)
                    if seconds is None:
                        continue
                    prefetched[self.cache_key(origin, destination)] = self._seconds_to_minutes(seconds)
        return prefetched

    def cache_key(self, origin: LocationRef, destination: LocationRef) -> str:
        departure_bucket = self._departure_bucket_key()
        origin_sig = self._location_signature(origin)
        destination_sig = self._location_signature(destination)
        return (
            "google_routes"
            f"|origin:{origin_sig}"
            f"|destination:{destination_sig}"
            f"|routing:{self.routing_preference}"
            f"|departure_bucket:{departure_bucket}"
        )

    def stats(self) -> dict[str, Any]:
        return {
            "external_api_calls": self.external_api_calls,
            "error_count_by_type": dict(self.error_count_by_type),
            "routing_preference": self.routing_preference,
            "departure_time_strategy": self.departure_time_strategy,
        }

    def _validate_configuration(self) -> None:
        if not self.api_key:
            self._raise_error(
                TravelTimeErrorType.CONFIG,
                "Google Routes API key is missing.",
            )
        if not self.base_url.lower().startswith("https://"):
            self._raise_error(
                TravelTimeErrorType.CONFIG,
                f"Google Routes base URL is invalid: {self.base_url}",
            )

    def _request_matrix(self, origins: list[LocationRef], destinations: list[LocationRef]) -> list[dict[str, Any]]:
        if not origins or not destinations:
            return []

        request_body: dict[str, Any] = {
            "origins": [self._to_waypoint(origin) for origin in origins],
            "destinations": [self._to_waypoint(destination) for destination in destinations],
            "travelMode": "DRIVE",
            "routingPreference": self.routing_preference,
        }
        departure_time = self._departure_time_iso()
        if departure_time is not None:
            request_body["departureTime"] = departure_time

        attempt = 0
        while True:
            try:
                return self._request_matrix_once(request_body)
            except TravelTimeProviderError as exc:
                if exc.error_type is TravelTimeErrorType.RETRYABLE and attempt < self.max_retries:
                    sleep_for = self.backoff_seconds * (2**attempt)
                    if sleep_for > 0:
                        time.sleep(sleep_for)
                    attempt += 1
                    continue
                raise

    def _request_matrix_once(self, request_body: dict[str, Any]) -> list[dict[str, Any]]:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": self.DEFAULT_FIELD_MASK,
        }
        request_bytes = json.dumps(request_body).encode("utf-8")
        request = urllib_request.Request(
            self.base_url,
            data=request_bytes,
            headers=headers,
            method="POST",
        )

        try:
            self.external_api_calls += 1
            with urllib_request.urlopen(request, timeout=self.request_timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            if exc.code in (401, 403):
                self._raise_error(
                    TravelTimeErrorType.AUTH,
                    f"Google Routes authentication failed with HTTP {exc.code}.",
                    status_code=exc.code,
                    cause=exc,
                )
            if exc.code == 429 or 500 <= exc.code < 600:
                self._raise_error(
                    TravelTimeErrorType.RETRYABLE,
                    f"Google Routes temporary error HTTP {exc.code}.",
                    status_code=exc.code,
                    cause=exc,
                )
            self._raise_error(
                TravelTimeErrorType.NON_RETRYABLE,
                f"Google Routes returned HTTP {exc.code}.",
                status_code=exc.code,
                cause=exc,
            )
        except urllib_error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, (TimeoutError, socket.timeout)):
                self._raise_error(
                    TravelTimeErrorType.RETRYABLE,
                    "Google Routes request timed out.",
                    cause=exc,
                )
            self._raise_error(
                TravelTimeErrorType.RETRYABLE,
                f"Google Routes network error: {exc}",
                cause=exc,
            )
        except TimeoutError as exc:
            self._raise_error(
                TravelTimeErrorType.RETRYABLE,
                "Google Routes request timed out.",
                cause=exc,
            )
        except Exception as exc:  # pragma: no cover - defensive branch
            self._raise_error(
                TravelTimeErrorType.NON_RETRYABLE,
                f"Google Routes unexpected error: {exc}",
                cause=exc,
            )

        try:
            return self._parse_matrix_response(payload)
        except json.JSONDecodeError as exc:
            self._raise_error(
                TravelTimeErrorType.NON_RETRYABLE,
                "Google Routes response is not valid JSON.",
                cause=exc,
            )
        except Exception as exc:  # pragma: no cover - defensive branch
            self._raise_error(
                TravelTimeErrorType.NON_RETRYABLE,
                f"Google Routes response parse error: {exc}",
                cause=exc,
            )

    def _parse_matrix_response(self, payload: str) -> list[dict[str, Any]]:
        trimmed = payload.strip()
        if not trimmed:
            return []
        if trimmed.startswith("["):
            parsed = json.loads(trimmed)
            return parsed if isinstance(parsed, list) else [parsed]
        entries: list[dict[str, Any]] = []
        for line in trimmed.splitlines():
            if line.strip():
                parsed_line = json.loads(line)
                if isinstance(parsed_line, dict):
                    entries.append(parsed_line)
        return entries

    def _extract_duration(
        self,
        entries: list[dict[str, Any]],
        origin_index: int,
        destination_index: int,
    ) -> int | None:
        for entry in entries:
            if int(entry.get("originIndex", -1)) != origin_index:
                continue
            if int(entry.get("destinationIndex", -1)) != destination_index:
                continue

            status = entry.get("status")
            if isinstance(status, dict) and int(status.get("code", 0) or 0) != 0:
                self._raise_error(
                    TravelTimeErrorType.NON_RETRYABLE,
                    f"Google Routes matrix entry status not OK: {status}",
                )
            condition = str(entry.get("condition", "ROUTE_EXISTS"))
            if condition and condition != "ROUTE_EXISTS":
                self._raise_error(
                    TravelTimeErrorType.NON_RETRYABLE,
                    f"Google Routes matrix entry condition is {condition}.",
                )

            duration_text = entry.get("duration")
            if isinstance(duration_text, str) and duration_text.endswith("s"):
                return max(int(math.ceil(float(duration_text[:-1]))), 0)
            if isinstance(duration_text, (int, float)):
                return max(int(math.ceil(float(duration_text))), 0)
        return None

    def _raise_error(
        self,
        error_type: TravelTimeErrorType,
        message: str,
        status_code: int | None = None,
        cause: Exception | None = None,
    ) -> None:
        self.error_count_by_type[error_type.value] = self.error_count_by_type.get(error_type.value, 0) + 1
        raise TravelTimeProviderError(error_type=error_type, message=message, status_code=status_code, cause=cause)

    def _to_waypoint(self, location: LocationRef) -> dict[str, Any]:
        return {
            "waypoint": {
                "location": {
                    "latLng": {
                        "latitude": location.lat,
                        "longitude": location.lng,
                    }
                }
            }
        }

    def _location_signature(self, location: LocationRef) -> str:
        lat = round(float(location.lat), self.coordinate_precision)
        lng = round(float(location.lng), self.coordinate_precision)
        return f"{lat:.{self.coordinate_precision}f},{lng:.{self.coordinate_precision}f}"

    def _departure_time_iso(self) -> str | None:
        if self.departure_time_strategy == "NONE":
            return None
        bucket = self._departure_bucket_key()
        if bucket == "none":
            return None
        epoch_seconds = int(bucket) * self.departure_time_bucket_minutes * 60
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch_seconds))

    def _departure_bucket_key(self) -> str:
        if self.departure_time_strategy == "NONE":
            return "none"
        bucket_seconds = self.departure_time_bucket_minutes * 60
        now_epoch = int(time.time())
        return str(now_epoch // bucket_seconds)

    @staticmethod
    def _seconds_to_minutes(seconds: int) -> int:
        if seconds <= 0:
            return 0
        return max(int(math.ceil(seconds / 60)), 1)


class FallbackTravelTimeProvider:
    def __init__(self, primary: TravelTimeProvider, fallback: TravelTimeProvider):
        self.primary = primary
        self.fallback = fallback
        self.fallback_count = 0
        self.error_count_by_type: dict[str, int] = {
            error_type.value: 0 for error_type in TravelTimeErrorType
        }
        self._logger = logging.getLogger("dispatch_optimizer.providers")

    def travel_minutes(self, origin: LocationRef, destination: LocationRef) -> int:
        try:
            return int(self.primary.travel_minutes(origin, destination))
        except TravelTimeProviderError as exc:
            self._record_fallback(exc.error_type, exc)
            return int(self.fallback.travel_minutes(origin, destination))
        except Exception as exc:  # pragma: no cover - defensive branch
            self._record_fallback(
                TravelTimeErrorType.NON_RETRYABLE,
                TravelTimeProviderError(
                    error_type=TravelTimeErrorType.NON_RETRYABLE,
                    message=f"Unexpected primary travel provider error: {exc}",
                    cause=exc,
                ),
            )
            return int(self.fallback.travel_minutes(origin, destination))

    def prefetch_pairs(self, pairs: list[tuple[LocationRef, LocationRef]]) -> dict[str, int]:
        prefetch = getattr(self.primary, "prefetch_pairs", None)
        if not callable(prefetch):
            return {}
        try:
            result = prefetch(pairs)
            return result if isinstance(result, dict) else {}
        except TravelTimeProviderError as exc:
            self._record_fallback(exc.error_type, exc, prefetch_mode=True)
            return {}
        except Exception as exc:  # pragma: no cover - defensive branch
            self._record_fallback(
                TravelTimeErrorType.NON_RETRYABLE,
                TravelTimeProviderError(
                    error_type=TravelTimeErrorType.NON_RETRYABLE,
                    message=f"Unexpected prefetch error: {exc}",
                    cause=exc,
                ),
                prefetch_mode=True,
            )
            return {}

    def stats(self) -> dict[str, Any]:
        primary_stats_fn = getattr(self.primary, "stats", None)
        fallback_stats_fn = getattr(self.fallback, "stats", None)
        primary_stats = primary_stats_fn() if callable(primary_stats_fn) else {}
        fallback_stats = fallback_stats_fn() if callable(fallback_stats_fn) else {}
        return {
            "fallback_count": self.fallback_count,
            "error_count_by_type": dict(self.error_count_by_type),
            "primary": primary_stats,
            "fallback": fallback_stats,
        }

    def _record_fallback(
        self,
        error_type: TravelTimeErrorType,
        error: TravelTimeProviderError,
        prefetch_mode: bool = False,
    ) -> None:
        self.fallback_count += 1
        self.error_count_by_type[error_type.value] = self.error_count_by_type.get(error_type.value, 0) + 1
        context = "prefetch" if prefetch_mode else "travel"
        if error_type in (TravelTimeErrorType.CONFIG, TravelTimeErrorType.AUTH):
            self._logger.error(
                "Primary travel provider %s error (%s). Falling back to Haversine. detail=%s",
                context,
                error_type.value,
                error,
            )
        else:
            self._logger.warning(
                "Primary travel provider %s degraded (%s). Falling back to Haversine. detail=%s",
                context,
                error_type.value,
                error,
            )
