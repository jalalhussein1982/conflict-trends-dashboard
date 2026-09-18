"""Deterministic synthetic conflict events with the ``acled_events`` schema.

No ACLED data is redistributed in this repository. This generator produces events that have
the same columns, the same taxonomy of event types, real first-level administrative regions
(public geography) and invented actors, so the server, its tests and the Inspector all work
with nothing to download and nothing to license.

The geography is coarse on purpose: each admin-1 region gets one centroid and a jitter radius,
so spatial tools return sensible neighbours without pretending to be a real event map.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

SEED = 20260918

# ACLED event taxonomy (public documentation), used verbatim so tool outputs read naturally.
EVENT_TYPES: dict[str, list[str]] = {
    "Battles": ["Armed clash", "Government regains territory", "Non-state actor overtakes territory"],
    "Explosions/Remote violence": ["Remote explosive/landmine/IED", "Air/drone strike", "Shelling/artillery/missile attack"],
    "Violence against civilians": ["Attack", "Abduction/forced disappearance", "Sexual violence"],
    "Protests": ["Peaceful protest", "Protest with intervention"],
    "Riots": ["Violent demonstration", "Mob violence"],
    "Strategic developments": ["Looting/property destruction", "Arrests", "Change to group/activity"],
}
DISORDER: dict[str, str] = {
    "Battles": "Political violence", "Explosions/Remote violence": "Political violence",
    "Violence against civilians": "Political violence", "Protests": "Demonstrations",
    "Riots": "Demonstrations", "Strategic developments": "Strategic developments",
}

# admin1 → (lat, lon) centroids, approximate, public geography.
REGIONS: dict[str, dict[str, tuple[float, float]]] = {
    "Mali": {
        "Gao": (16.27, -0.04), "Kidal": (18.44, 1.41), "Menaka": (15.92, 2.40), "Mopti": (14.50, -4.20),
        "Timbuktu": (16.77, -3.01), "Segou": (13.44, -6.27), "Sikasso": (11.32, -5.67),
        "Koulikoro": (12.86, -7.56), "Kayes": (14.45, -11.44), "Bamako": (12.64, -8.00),
    },
    "Burkina Faso": {
        "Sahel": (14.03, -0.03), "Est": (12.06, 0.36), "Centre-Nord": (13.08, -1.08), "Nord": (13.58, -2.42),
        "Boucle du Mouhoun": (12.25, -3.42), "Centre-Est": (11.78, -0.37), "Cascades": (10.63, -4.77),
        "Hauts-Bassins": (11.18, -4.29), "Centre": (12.37, -1.52), "Sud-Ouest": (10.33, -3.19),
    },
    "Niger": {
        "Tillaberi": (14.21, 1.45), "Tahoua": (14.89, 5.26), "Diffa": (13.32, 12.61), "Agadez": (16.97, 7.99),
        "Zinder": (13.80, 8.99), "Maradi": (13.50, 7.10), "Dosso": (13.05, 3.19), "Niamey": (13.51, 2.11),
    },
}
ISO = {"Mali": 466, "Burkina Faso": 854, "Niger": 562}

# Regions with more activity in the synthetic series (Liptako-Gourma tri-border and Lake Chad).
HOT = {"Gao", "Menaka", "Mopti", "Timbuktu", "Sahel", "Est", "Centre-Nord", "Nord", "Tillaberi", "Tahoua", "Diffa"}

ACTORS_ARMED = [f"Synthetic Armed Group {c}" for c in "ABCDE"]
ACTORS_STATE = {"Mali": "Military Forces of Country M", "Burkina Faso": "Military Forces of Country B",
                "Niger": "Military Forces of Country N"}
ACTORS_CIVIL = ["Civilians", "Protesters", "Rioters"]


def generate(n: int = 6000, seed: int = SEED, start: date = date(2020, 1, 1), end: date = date(2026, 8, 31)) -> list[dict]:
    """Return ``n`` synthetic events, sorted by date, as dicts keyed like ``acled_events``."""
    rng = random.Random(seed)
    span = (end - start).days
    countries = list(REGIONS)
    events: list[dict] = []
    for i in range(n):
        country = rng.choices(countries, weights=[4, 4, 3])[0]
        regions = list(REGIONS[country])
        weights = [3.0 if r in HOT else 1.0 for r in regions]
        admin1 = rng.choices(regions, weights=weights)[0]
        lat0, lon0 = REGIONS[country][admin1]
        # a mild upward trend over the years, like the real series
        t = rng.random() ** 0.8
        d = start + timedelta(days=int(t * span))
        etype = rng.choices(list(EVENT_TYPES), weights=[30, 18, 28, 10, 5, 9])[0]
        sub = rng.choice(EVENT_TYPES[etype])
        if etype in ("Protests", "Riots"):
            a1, a2, inter1, inter2 = rng.choice(ACTORS_CIVIL[1:]), None, "6", None
            fatal = 0 if etype == "Protests" else rng.choice([0, 0, 0, 1, 2])
        elif etype == "Violence against civilians":
            a1, a2, inter1, inter2 = rng.choice(ACTORS_ARMED), "Civilians", "2", "7"
            fatal = max(0, int(rng.expovariate(1 / 3)))
        elif etype == "Battles":
            a1 = rng.choice(ACTORS_ARMED + [ACTORS_STATE[country]])
            a2 = ACTORS_STATE[country] if a1 != ACTORS_STATE[country] else rng.choice(ACTORS_ARMED)
            inter1, inter2 = ("2", "1") if a1 != ACTORS_STATE[country] else ("1", "2")
            fatal = max(0, int(rng.expovariate(1 / 6)))
        elif etype == "Explosions/Remote violence":
            a1 = rng.choice(ACTORS_ARMED + [ACTORS_STATE[country]])
            a2 = rng.choice(["Civilians", ACTORS_STATE[country], rng.choice(ACTORS_ARMED)])
            inter1, inter2 = "2", "7"
            fatal = max(0, int(rng.expovariate(1 / 4)))
        else:
            a1, a2, inter1, inter2 = rng.choice(ACTORS_ARMED + [ACTORS_STATE[country]]), None, "2", None
            fatal = 0
        events.append({
            "event_id_cnty": f"SYN{i + 1:06d}",
            "event_date": d.isoformat(),
            "year": d.year,
            "time_precision": rng.choice([1, 1, 1, 2]),
            "disorder_type": DISORDER[etype],
            "event_type": etype,
            "sub_event_type": sub,
            "actor1": a1, "assoc_actor_1": None, "inter1": inter1,
            "actor2": a2, "assoc_actor_2": None, "inter2": inter2,
            "interaction": f"{inter1}{inter2}" if inter2 else inter1,
            "civilian_targeting": "Civilian targeting" if a2 == "Civilians" else None,
            "iso": ISO[country], "region": "Western Africa", "country": country,
            "admin1": admin1, "admin2": None, "admin3": None,
            "location": f"{admin1} locality {rng.randint(1, 40)}",
            "latitude": round(lat0 + rng.uniform(-0.9, 0.9), 4),
            "longitude": round(lon0 + rng.uniform(-0.9, 0.9), 4),
            "geo_precision": rng.choice([1, 1, 2, 3]),
            "source": "Synthetic", "source_scale": "Synthetic",
            "notes": None,
            "fatalities": fatal,
            "tags": None,
            "timestamp": 1_577_836_800 + int(t * span) * 86_400,
            "population_best": None, "population_1km": None, "population_2km": None, "population_5km": None,
        })
    events.sort(key=lambda e: (e["event_date"], e["event_id_cnty"]))
    return events
