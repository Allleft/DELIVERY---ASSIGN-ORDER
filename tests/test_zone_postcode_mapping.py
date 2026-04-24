from __future__ import annotations

import csv
import json
import subprocess
import unittest
from pathlib import Path


RAW_ZONE_POSTCODE_CSV = Path("data/raw/zone-postcode-raw-data.csv")


class ZonePostcodeMappingTest(unittest.TestCase):
    def test_frontend_builtin_zone_mapping_covers_raw_csv(self) -> None:
        raw_mapping = self._read_raw_mapping()
        app_mapping = self._load_js_mapping("frontend/app.js", "buildAppBuiltinZoneByPostcode", with_dom_stub=True)
        override_mapping = self._load_js_mapping(
            "frontend/overrides.js",
            "buildBuiltinZoneByPostcode",
            required=False,
        )

        self.assertEqual(raw_mapping, app_mapping)
        if override_mapping is not None:
            self.assertEqual(raw_mapping, override_mapping)

    def _read_raw_mapping(self) -> dict[str, str]:
        with RAW_ZONE_POSTCODE_CSV.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            result: dict[str, str] = {}
            for row in reader:
                zone_code_key = "zone_code"
                if zone_code_key not in row and row:
                    zone_code_key = next((key for key in row.keys() if key and key.lstrip("\ufeff") == "zone_code"), zone_code_key)
                postcode = str(row["postcode"]).strip().zfill(4)
                zone_code = str(row[zone_code_key]).strip()
                if postcode and zone_code:
                    result[postcode] = zone_code
        return result

    def _load_js_mapping(
        self,
        path: str,
        function_name: str,
        with_dom_stub: bool = False,
        required: bool = True,
    ) -> dict[str, str] | None:
        path_literal = json.dumps(path)
        function_literal = json.dumps(function_name)
        dom_stub = """
context.document = {
  addEventListener: () => {},
  createElement: () => ({ click: () => {} }),
  body: { appendChild: () => {}, removeChild: () => {} },
};
context.URL = { createObjectURL: () => '', revokeObjectURL: () => {} };
context.Blob = function Blob() {};
""" if with_dom_stub else ""

        script = f"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync({path_literal}, 'utf8');
const context = {{ console }};
{dom_stub}
context.window = context;
vm.createContext(context);
vm.runInContext(source, context, {{ filename: {path_literal} }});
const fn = context[{function_literal}];
if (typeof fn !== 'function') {{
  process.stdout.write('__MISSING_FUNCTION__');
}} else {{
  process.stdout.write(JSON.stringify(fn()));
}}
"""
        completed = subprocess.run(
            ["node", "-e", script],
            check=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        output = (completed.stdout or "").strip()
        if output == "__MISSING_FUNCTION__":
            if required:
                self.fail(f"Mapping builder not found: {function_name} in {path}")
            return None
        parsed = json.loads(output or "{}")
        return {str(key).zfill(4): str(value) for key, value in parsed.items()}


if __name__ == "__main__":
    unittest.main()
