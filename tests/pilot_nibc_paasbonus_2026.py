"""Pilot-test: NIBC Paasbonus 2026 met 3 expliciete flights.

    Flight 1 - Launch : 2026-03-01 .. 2026-03-15  -> awareness 30%
    Flight 2 - Main   : 2026-03-16 .. 2026-03-31  -> consideratie 25% + conversie 20%
    Flight 3 - Wrap   : 2026-04-01 .. 2026-04-10  -> conversie 20% + loyalty 5%

Tactiek-IDs gebruiken D-prefix voor flight-nummer (D1T01, D2T01, D3T01).
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config.loader import load_klant_config
from generators.flight_planner import Flight, plan_tactieken
from generators.plan_excel import (
    PlanContext,
    PlanHeader,
    build_plan_rows,
    uren_from_klantconfig,
    write_plan_excel,
)
from generators.tactiek_id import build_tactiek_id, derive_productlijn_code
from validators.naming import validate_plan


def main() -> int:
    cfg = load_klant_config("nibc")
    campagne = next(c for c in (cfg.get("campagnes") or []) if c["code"] == "PAASBONUS")
    jaar = 2026

    totaal_incl_btw = 25_000.0
    btw_pct = float((cfg.get("financieel") or {}).get("btw_pct", 21.0))

    # Expliciete flights zoals besproken met Jacob
    flights = [
        Flight(
            nr=1, naam="Launch",
            start=date(2026, 3, 1),  eind=date(2026, 3, 15),
            fase_budget_pct={"awareness": 30},
        ),
        Flight(
            nr=2, naam="Main",
            start=date(2026, 3, 16), eind=date(2026, 3, 31),
            fase_budget_pct={"consideratie": 25, "conversie": 20},
        ),
        Flight(
            nr=3, naam="Wrap",
            start=date(2026, 4, 1),  eind=date(2026, 4, 10),
            fase_budget_pct={"conversie": 20, "loyalty": 5},
        ),
    ]
    start = min(f.start for f in flights)
    eind = max(f.eind for f in flights)

    # Header bouwen
    uren_posten = uren_from_klantconfig(cfg)
    header = PlanHeader(
        klant=(cfg.get("klant") or {}).get("naam") or "NIBC",
        campagne=campagne["naam"],
        start=start,
        eind=eind,
        totaal_incl_btw=totaal_incl_btw,
        btw_pct=btw_pct,
        uren_posten=uren_posten,
    )
    print(f"[header] totaal_ex_btw  = EUR {header.totaal_ex_btw:>10,.2f}")
    print(f"[header] uren_ex_btw    = EUR {header.uren_ex_btw:>10,.2f}")
    print(f"[header] media_ex_btw   = EUR {header.media_ex_btw:>10,.2f}")

    media_budget = header.media_ex_btw
    if media_budget <= 0:
        print("[fout] media-budget <= 0 na aftrek uren, stop.")
        return 2

    # Plan tactieken per flight
    pt = plan_tactieken(flights, media_budget, cfg)
    for w in pt["warnings"]:
        print(f"[flights][warn] {w}")
    print(f"[flights] {len(pt['flights'])} flights, {len(pt['rows'])} (flight, fase, kanaal)-rijen")
    for fs in pt["flights"]:
        print(
            f"  flight {fs['flight_nr']} ({fs['flight_naam']:<8}) "
            f"{fs['flight_start']} - {fs['flight_eind']}  "
            f"dagen={fs['dagen']:>3}  "
            f"budget=EUR {fs['budget_eur_media']:>9,.2f}  "
            f"fases: {fs['actieve_fases']}"
        )

    # Tactiek-IDs toekennen (D{flight_nr}T{nr_in_flight})
    pl_code = derive_productlijn_code(cfg, campagne["productlijn"])
    klantcode = str((cfg.get("klant") or {}).get("code", "")).upper()
    per_flight_nr = {}
    tactieken = []
    for row in pt["rows"]:
        fnr = row["flight_nr"]
        per_flight_nr[fnr] = per_flight_nr.get(fnr, 0) + 1
        nr_in_flight = per_flight_nr[fnr]
        tid = build_tactiek_id(
            klantcode=klantcode,
            
            start=row["flight_start"],
            campagne_naam=campagne["naam"],
            nr=nr_in_flight,
            deel=fnr,                 # <-- flight als D-prefix
        )
        tactieken.append({
            "tactiek_id": tid,
            "flight_nr": row["flight_nr"],
            "flight_naam": row["flight_naam"],
            "fase": row["fase"],
            "kanaal": row["kanaal"],
            "budget_eur_media": row["budget_eur_media"],
            "flight_start": row["flight_start"],
            "flight_eind": row["flight_eind"],
        })
    print(f"[tactiek] {len(tactieken)} tactieken, voorbeelden:")
    for t in [tactieken[0], tactieken[len(tactieken)//2], tactieken[-1]]:
        print(f"  {t['tactiek_id']:<40} {t['fase']:<13} {t['kanaal']}")

    # Plan-df + Excel
    ctx = PlanContext(
        klant_cfg=cfg,
        campagne={**campagne, "jaar": jaar},
        benchmarks_used=((cfg.get("benchmarks") or {}).get("kanaalsplit") or {}),
        keybeliefs_used=list(cfg.get("keybeliefs") or []),
        header=header,
    )
    plan_df = build_plan_rows(tactieken, ctx)
    print(f"[plan] {len(plan_df)} plan-rijen, {len(plan_df.columns)} kolommen")

    rep = validate_plan(plan_df.to_dict(orient="records"), cfg)
    if rep.ok:
        print(f"[validatie] OK, alle {len(plan_df)} rijen geldig")
    else:
        print(f"[validatie] {len(rep.issues)} issues:")
        for issue in rep.issues[:10]:
            print(f"  row {issue.row_index} {issue.field}: {issue.issue}")

    flights_df = pd.DataFrame(pt["flights"])
    budget_df = pd.DataFrame([
        {"flight_nr": r["flight_nr"], "flight_naam": r["flight_naam"],
         "fase": r["fase"], "kanaal": r["kanaal"],
         "pct_totaal_media": r["pct_totaal_media"],
         "budget_eur": r["budget_eur_media"]}
        for r in pt["rows"]
    ])

    out = Path(__file__).resolve().parent / "_output" / "plan_nibc_PAASBONUS_2026.xlsx"
    write_plan_excel(
        out,
        plan_df=plan_df,
        flights_df=flights_df,
        budget_df=budget_df,
        ctx=ctx,
    )
    print(f"[excel] geschreven naar: {out}")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
