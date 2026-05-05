from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.services.service_factory import (
    _resolve_candidate_route_time_limit_seconds_from_env,
    build_runtime_dispatch_service_from_env,
)


class ServiceFactoryCandidateRouteLimitTest(unittest.TestCase):
    def test_env_missing_candidate_route_time_limit_falls_back_to_default(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(0.25, _resolve_candidate_route_time_limit_seconds_from_env())

    def test_env_empty_candidate_route_time_limit_falls_back_to_default(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"OFFICE_DISPATCH_CANDIDATE_ROUTE_TIME_LIMIT_SECONDS": "   "},
            clear=True,
        ):
            self.assertEqual(0.25, _resolve_candidate_route_time_limit_seconds_from_env())

    def test_env_invalid_candidate_route_time_limit_falls_back_to_default(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"OFFICE_DISPATCH_CANDIDATE_ROUTE_TIME_LIMIT_SECONDS": "invalid"},
            clear=True,
        ):
            with self.assertLogs("backend.services.service_factory", level="WARNING") as captured:
                value = _resolve_candidate_route_time_limit_seconds_from_env()

        self.assertEqual(0.25, value)
        self.assertIn("Invalid OFFICE_DISPATCH_CANDIDATE_ROUTE_TIME_LIMIT_SECONDS", "\n".join(captured.output))

    def test_env_non_positive_candidate_route_time_limit_falls_back_to_default(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"OFFICE_DISPATCH_CANDIDATE_ROUTE_TIME_LIMIT_SECONDS": "0"},
            clear=True,
        ):
            with self.assertLogs("backend.services.service_factory", level="WARNING") as captured:
                value = _resolve_candidate_route_time_limit_seconds_from_env()

        self.assertEqual(0.25, value)
        self.assertIn("Non-positive OFFICE_DISPATCH_CANDIDATE_ROUTE_TIME_LIMIT_SECONDS", "\n".join(captured.output))

    def test_runtime_service_env_override_sets_candidate_route_time_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "runtime.sqlite3"
            service = None
            with mock.patch.dict(
                "os.environ",
                {
                    "OFFICE_DISPATCH_DB_PATH": str(db_path),
                    "OFFICE_DISPATCH_CANDIDATE_ROUTE_TIME_LIMIT_SECONDS": "2.0",
                },
                clear=True,
            ):
                service = build_runtime_dispatch_service_from_env()

            self.assertIsNotNone(service)
            assert service is not None
            self.assertEqual(2.0, service.engine_config.candidate_route_time_limit_seconds)
            close_repo = getattr(service.repository, "close", None)
            if callable(close_repo):
                close_repo()


if __name__ == "__main__":
    unittest.main()
