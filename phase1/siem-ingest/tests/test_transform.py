from __future__ import annotations

import unittest
from datetime import date

from siem_ingest.transform import normalize_event


class NormalizeEventTests(unittest.TestCase):
    def test_normalize_event_casts_fields_and_duplicates_coordinates(self) -> None:
        raw_event = {
            "event_id_cnty": "EVT00001",
            "event_date": "2025-11-15",
            "year": "2025",
            "time_precision": "1",
            "disorder_type": "Political violence",
            "event_type": "Battles",
            "sub_event_type": "Armed clash",
            "actor1": "Country X Armed Forces",
            "assoc_actor_1": None,
            "inter1": "8",
            "actor2": "Group Y",
            "assoc_actor_2": None,
            "inter2": "2",
            "interaction": "28",
            "civilian_targeting": None,
            "iso": "999",
            "region": "Region One",
            "country": "Country X",
            "admin1": "Province A",
            "admin2": "District B",
            "admin3": None,
            "location": "Townsville",
            "latitude": "10.5000",
            "longitude": "-2.5000",
            "geo_precision": "1",
            "source": "ExampleSource",
            "source_scale": "National",
            "notes": "Test note",
            "fatalities": "12",
            "tags": None,
            "timestamp": "1712169600",
            "population_best": "1200",
            "population_1km": "1100",
            "population_2km": "1300",
            "population_5km": "1800",
        }

        normalized = normalize_event(raw_event)

        self.assertEqual(normalized[0], "EVT00001")
        self.assertEqual(normalized[1], date(2025, 11, 15))
        self.assertEqual(normalized[2], 2025)
        self.assertEqual(normalized[3], 1)
        self.assertEqual(normalized[22], 10.5000)
        self.assertEqual(normalized[23], -2.5000)
        self.assertEqual(normalized[28], 12)
        self.assertIsNone(normalized[29])
        self.assertEqual(normalized[30], 1712169600)
        self.assertEqual(normalized[31], 1200)
        self.assertEqual(normalized[34], 1800)
        self.assertEqual(normalized[-2:], (-2.5000, 10.5000))

    def test_normalize_event_preserves_missing_optional_values(self) -> None:
        raw_event = {
            "event_id_cnty": "EVT00002",
            "event_date": "2024-01-03",
            "year": 2024,
            "disorder_type": "Political violence",
            "event_type": "Strategic developments",
            "country": "Country Z",
            "location": "Riverton",
            "latitude": None,
            "longitude": None,
            "fatalities": None,
            "timestamp": None,
        }

        normalized = normalize_event(raw_event)

        self.assertEqual(normalized[1], date(2024, 1, 3))
        self.assertEqual(normalized[22], None)
        self.assertEqual(normalized[23], None)
        self.assertEqual(normalized[28], 0)
        self.assertEqual(normalized[-2:], (None, None))


if __name__ == "__main__":
    unittest.main()
