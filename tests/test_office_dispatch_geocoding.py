from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.services.geocoding import StaticAddressGeocoder


class StaticAddressGeocoderTest(unittest.TestCase):
    def test_static_geocoder_loads_utf8_bom_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            geocoder_path = Path(temp_dir) / "geocoder-bom.json"
            geocoder_path.write_text(
                json.dumps(
                    {
                        "Depot": [-37.7800, 144.9300],
                        "98-102 Hume Hwy, Somerton VIC 3062, Australia": [-37.6461, 144.9525],
                    }
                ),
                encoding="utf-8-sig",
            )

            geocoder = StaticAddressGeocoder(json_path=geocoder_path)
            depot = geocoder.geocode("Depot")
            somerton = geocoder.geocode("98-102 Hume Hwy, Somerton VIC 3062, Australia")

            self.assertIsNotNone(depot)
            self.assertIsNotNone(somerton)
            assert depot is not None
            assert somerton is not None
            self.assertAlmostEqual(-37.7800, depot["lat"], places=4)
            self.assertAlmostEqual(144.9300, depot["lng"], places=4)
            self.assertAlmostEqual(-37.6461, somerton["lat"], places=4)
            self.assertAlmostEqual(144.9525, somerton["lng"], places=4)

    def test_static_geocoder_still_loads_plain_utf8_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            geocoder_path = Path(temp_dir) / "geocoder-plain.json"
            geocoder_path.write_text(
                json.dumps(
                    {
                        "Depot": [-37.7800, 144.9300],
                    }
                ),
                encoding="utf-8",
            )

            geocoder = StaticAddressGeocoder(json_path=geocoder_path)
            point = geocoder.geocode("   depOt   ")

            self.assertIsNotNone(point)
            assert point is not None
            self.assertAlmostEqual(-37.7800, point["lat"], places=4)
            self.assertAlmostEqual(144.9300, point["lng"], places=4)


if __name__ == "__main__":
    unittest.main()
