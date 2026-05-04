from __future__ import annotations

import unittest

from backend.db.repository import InMemoryDispatchRepository


class InMemoryDispatchRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = InMemoryDispatchRepository()

    def test_replace_and_list_drivers(self) -> None:
        self.repo.replace_drivers(
            [
                {
                    "driver_id": 1,
                    "shift_start": "07:00",
                    "shift_end": "17:00",
                    "is_available": True,
                    "start_location": "Depot",
                    "end_location": "Depot",
                },
                {
                    "driver_id": 2,
                    "shift_start": "07:00",
                    "shift_end": "17:00",
                    "is_available": False,
                    "start_location": "Depot",
                    "end_location": "Depot",
                },
            ]
        )

        all_drivers = self.repo.list_drivers()
        active_drivers = self.repo.list_active_drivers()

        self.assertEqual(2, len(all_drivers))
        self.assertEqual([1], [driver["driver_id"] for driver in active_drivers])

    def test_replace_and_list_vehicles(self) -> None:
        self.repo.replace_vehicles(
            [
                {
                    "vehicle_id": 10,
                    "vehicle_type": "van",
                    "is_available": True,
                },
                {
                    "vehicle_id": 20,
                    "vehicle_type": "medium",
                    "is_available": False,
                },
            ]
        )

        all_vehicles = self.repo.list_vehicles()
        active_vehicles = self.repo.list_active_vehicles()

        self.assertEqual(2, len(all_vehicles))
        self.assertEqual([10], [vehicle["vehicle_id"] for vehicle in active_vehicles])

    def test_seed_helpers_remain_compatible(self) -> None:
        self.repo.seed_driver(
            {
                "driver_id": 9,
                "shift_start": "07:00",
                "shift_end": "17:00",
                "is_available": True,
                "start_location": "Depot",
                "end_location": "Depot",
            }
        )
        self.repo.seed_vehicle(
            {
                "vehicle_id": 99,
                "vehicle_type": "van",
                "is_available": True,
            }
        )

        self.assertEqual([9], [driver["driver_id"] for driver in self.repo.list_active_drivers()])
        self.assertEqual([99], [vehicle["vehicle_id"] for vehicle in self.repo.list_active_vehicles()])


if __name__ == "__main__":
    unittest.main()
