"""Flight-planner.

Flights zijn expliciete tijdvensters (user-defined) met elk een eigen
fase-mix. Elke flight krijgt een D-prefix in de tactiek-id:

    NIBC-BON-2026-03-Paasbonus-D1T01    (flight 1, tactiek 1)
    NIBC-BON-2026-03-Paasbonus-D2T05    (flight 2, tactiek 5)

Gebruik
-------
    from datetime import date
    from generators.flight_planner import Flight, plan_tactieken

    flights = [
        Flight(1, "Launch", date(2026, 3, 1),  date(2026, 3, 15),
               fase_budget_pct={"awareness": 30}),
        Flight(2, "Main",   date(2026, 3, 16), date(2026, 3, 31),
               fase_budget_pct={"consideratie": 25, "conversie": 20}),
        Flight(3, "Wrap",   date(2026, 4, 1),  date(2026, 4, 10),
               fase_budget_pct={"conversie": 20, "loyalty": 5}),
    ]

    plan_rows = plan_tactieken(flights, media_budget_eur=16481, klant_cfg=cfg)
    # -> list[dict] met flight_nr, flight_naam, flight_start, flight_eind,
    #    fase, kanaal, budget_eur_media, tactiek_seq_in_flight

De som van alle fase_budget_pct over alle flights moet (ongeveer) 100 zijn.
Als dat niet klopt, wordt genormaliseerd en een warning gelogd.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from generators.budget_split import split_fase_to_kanalen


# -----------------------------------------------------------------------------
#  Flight-dataclass (expliciete tijdvensters)
# -----------------------------------------------------------------------------

@dataclass
class Flight:
    nr: int                              # 1, 2, 3 ... -> wordt D-prefix
    naam: str                            # "Launch", "Main", "Wrap"
    start: date
    eind: date
    # {fase: pct_of_media_totaal}, bv. {"awareness": 30}
    fase_budget_pct: dict = field(default_factory=dict)

    @property
    def dagen(self) -> int:
        return (self.eind - self.start).days + 1

    @property
    def totaal_pct(self) -> float:
        return float(sum(v for v in self.fase_budget_pct.values() if v))

    @property
    def actieve_fases(self) -> list:
        return [f for f, p in self.fase_budget_pct.items() if p and p > 0]


def _as_date(d) -> date:
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, str):
        return date.fromisoformat(d[:10])
    raise TypeError(f"Kan {d!r} niet naar date converteren")


def _validate_flights(flights: list) -> list:
    """Basis-sanity: nummering, overlap, volgorde. Return lijst warnings."""
    warnings = []
    nrs = [f.nr for f in flights]
    if len(set(nrs)) != len(nrs):
        warnings.append(f"Dubbele flight-nummers: {nrs}")
    sorted_flights = sorted(flights, key=lambda f: f.start)
    for a, b in zip(sorted_flights, sorted_flights[1:]):
        if a.eind >= b.start:
            warnings.append(
                f"Flight {a.nr} ({a.start}-{a.eind}) overlapt met flight {b.nr} ({b.start}-{b.eind})."
            )
    for f in flights:
        if f.eind < f.start:
            warnings.append(f"Flight {f.nr}: eind {f.eind} ligt voor start {f.start}.")
        if not f.actieve_fases:
            warnings.append(f"Flight {f.nr} ({f.naam}): geen actieve fases in fase_budget_pct.")
    return warnings


# -----------------------------------------------------------------------------
#  Plan-tactieken per flight
# -----------------------------------------------------------------------------

def plan_tactieken(
    flights: list,
    media_budget_eur: float,
    klant_cfg: dict,
    extra_keybeliefs: list = None,
) -> dict:
    """Produceer tactiek-rijen per (flight, fase, kanaal).

    Parameters
    ----------
    flights          : list[Flight] - expliciete tijdvensters met fase-mix.
    media_budget_eur : totaal media-budget (ex btw, ex uren).
    klant_cfg        : geladen klant-config (voor benchmarks + keybeliefs).
    extra_keybeliefs : aanvullende keybeliefs (bovenop cfg.keybeliefs).

    Returns
    -------
    dict met:
        rows      : list[dict] - 1 rij per (flight, fase, kanaal) met
                    flight_nr, flight_naam, flight_start, flight_eind,
                    fase, kanaal, pct_totaal_media, budget_eur_media
        flights   : list[dict] - per-flight samenvatting (nr, naam, dagen,
                    totaal_pct, budget_eur)
        warnings  : list[str]
    """
    warnings = list(_validate_flights(flights))
    if media_budget_eur <= 0:
        warnings.append("media_budget_eur is 0 of negatief.")
        return {"rows": [], "flights": [], "warnings": warnings}

    # Normaliseer fase_budget_pct naar 100% over alle flights heen
    totaal = sum(f.totaal_pct for f in flights)
    if totaal <= 0:
        warnings.append("Geen budget-verdeling in flights (sum fase_budget_pct = 0).")
        return {"rows": [], "flights": [], "warnings": warnings}
    if abs(totaal - 100.0) > 0.5:
        warnings.append(
            f"Sum fase_budget_pct = {totaal:.1f}% (verwacht ~100). Wordt genormaliseerd."
        )
    factor = 100.0 / totaal

    rows = []
    flight_summary = []
    grand_total = 0.0

    for fl in flights:
        fl_budget_total = 0.0
        # Volgnummer per flight voor latere tactiek-nummering (T01, T02, ...)
        seq_in_flight = 0
        for fase, pct in fl.fase_budget_pct.items():
            if not pct or pct <= 0:
                continue
            fase_budget = round(media_budget_eur * pct * factor / 100.0, 2)
            kan_rows = split_fase_to_kanalen(
                fase, fase_budget, klant_cfg, extra_keybeliefs,
            )
            for k in kan_rows:
                seq_in_flight += 1
                rows.append({
                    "flight_nr": fl.nr,
                    "flight_naam": fl.naam,
                    "flight_start": fl.start,
                    "flight_eind": fl.eind,
                    "fase": fase,
                    "kanaal": k["kanaal"],
                    "pct_van_fase": round(k["share"] * 100, 2),
                    "pct_totaal_media": round(pct * factor, 2),
                    "budget_eur_media": k["budget_eur"],
                    "seq_in_flight": seq_in_flight,
                })
                fl_budget_total += k["budget_eur"]
        flight_summary.append({
            "flight_nr": fl.nr,
            "flight_naam": fl.naam,
            "flight_start": fl.start.isoformat(),
            "flight_eind": fl.eind.isoformat(),
            "dagen": fl.dagen,
            "actieve_fases": ", ".join(fl.actieve_fases),
            "pct_totaal_media": round(fl.totaal_pct * factor, 2),
            "budget_eur_media": round(fl_budget_total, 2),
        })
        grand_total += fl_budget_total

    # Afrondings-sanity: corrigeer totaal op grootste rij
    diff = round(media_budget_eur - grand_total, 2)
    if abs(diff) > 0.01 and rows:
        biggest = max(rows, key=lambda r: r["budget_eur_media"])
        biggest["budget_eur_media"] = round(biggest["budget_eur_media"] + diff, 2)
        # Recompute flight summary budgets
        per_flight = {}
        for r in rows:
            per_flight[r["flight_nr"]] = per_flight.get(r["flight_nr"], 0.0) + r["budget_eur_media"]
        for fs in flight_summary:
            fs["budget_eur_media"] = round(per_flight.get(fs["flight_nr"], 0.0), 2)

    return {"rows": rows, "flights": flight_summary, "warnings": warnings}


# -----------------------------------------------------------------------------
#  Convenience: auto-flights uit fasesplit_default
# -----------------------------------------------------------------------------

def auto_flights(
    start,
    eind,
    klant_cfg: dict,
) -> list:
    """Genereer 1 flight per fase op basis van cfg.flight_defaults.fase_duur_aandeel.

    Handig voor simpele campagnes waar je geen expliciete bursts wil tekenen.
    Retourneert list[Flight], 1 flight per actieve fase, sequentieel.
    """
    start = _as_date(start)
    eind = _as_date(eind)
    if eind < start:
        raise ValueError(f"eind ({eind}) ligt voor start ({start})")

    defaults = (klant_cfg or {}).get("flight_defaults") or {}
    volgorde = defaults.get("fase_volgorde") or [
        "awareness", "consideratie", "conversie", "loyalty",
    ]
    aandelen = defaults.get("fase_duur_aandeel") or {}
    fase_pct = (klant_cfg.get("benchmarks") or {}).get("fasesplit_default") or {}

    # Actieve fases: die met > 0 in fasesplit_default
    actief = [f for f in volgorde if (fase_pct.get(f) or 0) > 0]
    if not actief:
        return []

    # Verdeel dagen over fases
    totaal_dagen = (eind - start).days + 1
    shares_in = {f: float(aandelen.get(f, 0) or 0) for f in actief}
    if all(v == 0 for v in shares_in.values()):
        shares_in = {f: 1.0 for f in actief}
    total_share = sum(shares_in.values())
    shares = {k: v / total_share for k, v in shares_in.items() if v > 0}

    dagen_per_fase = {}
    toegewezen = 0
    for i, f in enumerate(actief):
        if i < len(actief) - 1:
            d = max(1, int(round(totaal_dagen * shares[f])))
            dagen_per_fase[f] = d
            toegewezen += d
        else:
            dagen_per_fase[f] = max(1, totaal_dagen - toegewezen)

    flights = []
    cursor = start
    for i, f in enumerate(actief, start=1):
        d = dagen_per_fase[f]
        eind_fase = min(cursor + timedelta(days=d - 1), eind)
        flights.append(Flight(
            nr=i,
            naam=f.capitalize(),
            start=cursor,
            eind=eind_fase,
            fase_budget_pct={f: float(fase_pct.get(f) or 0)},
        ))
        cursor = eind_fase + timedelta(days=1)
        if cursor > eind:
            break
    return flights


# -----------------------------------------------------------------------------
#  Excel-hulp
# -----------------------------------------------------------------------------

def flights_summary_to_rows(flight_summary: list) -> list:
    """Alias voor consistency; flight_summary is al in rij-vorm."""
    return list(flight_summary)
