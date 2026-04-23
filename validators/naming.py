"""Validator voor de DBD tactiek-id naming-convention (v0.2).

Conventie (zie generators/tactiek_id.py):
    {KLANTCODE}-{YYYY}-{MM}-{Campagne}-T{NN}
    {KLANTCODE}-{YYYY}-{MM}-{Campagne}-D{D}T{NN}
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

TACTIEK_ID_RE = re.compile(
    r"^"
    r"(?P<klant>[A-Z]{2,8})-"
    r"(?P<yyyy>20\d{2})-"
    r"(?P<mm>0[1-9]|1[0-2])-"
    r"(?P<campagne>[A-Z][A-Za-z0-9]{1,39})-"
    r"(?:D(?P<deel>[1-9])T(?P<nr_deel>\d{2})|T(?P<nr>\d{2}))"
    r"$"
)


@dataclass
class RowIssue:
    row_index: int
    field: str
    issue: str
    value: Any = None


@dataclass
class ValidationReport:
    issues: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def errors_as_df_rows(self) -> list:
        return [
            {"row": i.row_index, "field": i.field, "issue": i.issue, "value": i.value}
            for i in self.issues
        ]


def validate_tactiek_id(tid, klant_cfg=None):
    if not isinstance(tid, str) or not tid:
        return "tactiek_id is leeg"
    m = TACTIEK_ID_RE.match(tid)
    if not m:
        return (
            "Komt niet overeen met patroon "
            "{KLANT}-{YYYY}-{MM}-{Campagne}-T{NN} (of D{d}T{nn})."
        )
    if klant_cfg:
        expected_klant = str((klant_cfg.get("klant") or {}).get("code", "")).upper()
        if expected_klant and m.group("klant") != expected_klant:
            return f"Klantcode {m.group('klant')!r} != config-klant {expected_klant!r}."
        jaar = int(m.group("yyyy"))
        today_year = date.today().year
        if jaar < today_year - 2 or jaar > today_year + 5:
            return f"Jaar {jaar} lijkt buiten de plausibele range (nu={today_year})."
    return None


def validate_plan_row(row, klant_cfg=None, row_index=0):
    issues = []
    tid = row.get("tactiek_id")
    err = validate_tactiek_id(tid, klant_cfg)
    if err:
        issues.append(RowIssue(row_index, "tactiek_id", err, tid))

    # Budget > 0
    budget_fields = ("budget", "budget_eur_totaal", "budget_eur_media", "budget_eur")
    b = next((row[f] for f in budget_fields if row.get(f) is not None), None)
    if b is None or (isinstance(b, (int, float)) and b <= 0):
        issues.append(RowIssue(row_index, "budget", "Budget moet > 0 zijn.", b))

    # Datums logisch
    s, e = row.get("flight_start"), row.get("flight_eind")
    try:
        if s and e:
            sd = date.fromisoformat(str(s)[:10])
            ed = date.fromisoformat(str(e)[:10])
            if ed < sd:
                issues.append(RowIssue(row_index, "flight_eind",
                    f"flight_eind < flight_start ({ed} < {sd})."))
    except Exception as exc:
        issues.append(RowIssue(row_index, "flight_start/eind", f"Datum-parse-fout: {exc}"))

    # Kanaal bekend
    if klant_cfg and row.get("kanaal"):
        kanalen = klant_cfg.get("kanalen") or {}
        if isinstance(kanalen, dict) and row["kanaal"] not in kanalen:
            issues.append(RowIssue(row_index, "kanaal",
                f"Kanaal {row['kanaal']!r} niet in klant-config.kanalen.",
                row["kanaal"]))

    # Doelstelling bekend (was: fase)
    doel = row.get("fase") or row.get("fase")
    if klant_cfg and doel:
        fases = klant_cfg.get("fases") or {}
        if isinstance(fases, dict) and doel not in fases:
            issues.append(RowIssue(row_index, "fase",
                f"Fase {doel!r} niet in klant-config.fases.", doel))
    return issues


def validate_plan(rows, klant_cfg=None):
    rep = ValidationReport()
    seen = set()
    for i, row in enumerate(rows):
        rep.issues.extend(validate_plan_row(row, klant_cfg, row_index=i))
        tid = row.get("tactiek_id")
        if tid:
            if tid in seen:
                rep.issues.append(RowIssue(i, "tactiek_id", "Dubbele tactiek_id.", tid))
            seen.add(tid)
    return rep
