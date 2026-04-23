"""Budget-splitter.

Twee publieke entrypoints:

1. `split_budget(...)`        : grof, fase x kanaal op totaal-media
                                 (voor simpele auto-mode zonder expliciete flights).
2. `split_fase_to_kanalen(...)`: split een enkel fase-budget over kanalen
                                 (gebruikt door flight_planner als er expliciete
                                 flights met een fase-mix zijn).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BudgetSplitResult:
    total_budget_eur: float
    rows: list = field(default_factory=list)
    per_fase: dict = field(default_factory=dict)
    per_kanaal: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


def _normalize(d: dict) -> dict:
    """Normalize positieve waarden naar shares die tot 1.0 optellen."""
    total = sum(v for v in d.values() if v and v > 0)
    if total <= 0:
        return {k: 0.0 for k in d}
    return {k: (v / total) for k, v in d.items() if v and v > 0}


def _apply_keybeliefs(
    kanaalsplit: dict,
    keybeliefs: list,
) -> dict:
    """Past multipliers toe op benchmark-split (kopie, in-place-safe)."""
    out = {fase: dict(kanalen) for fase, kanalen in kanaalsplit.items()}
    for kb in keybeliefs or []:
        fase = kb.get("fase")
        kanaal = kb.get("kanaal")
        mult = kb.get("multiplier", 1.0)
        if fase not in out:
            continue
        if kanaal not in out[fase]:
            out[fase][kanaal] = 0.0
        out[fase][kanaal] = out[fase][kanaal] * mult
    return out


def split_fase_to_kanalen(
    fase: str,
    fase_budget_eur: float,
    klant_cfg: dict,
    extra_keybeliefs: list = None,
) -> list:
    """Verdeel 1 fase-budget over kanalen op basis van benchmarks + keybeliefs.

    Returns:
        list[dict(kanaal, share, budget_eur)]
        De budget_eur-sommen zijn exact afgerond op fase_budget_eur.
    """
    if fase_budget_eur <= 0:
        return []
    kanaalsplit = (klant_cfg.get("benchmarks") or {}).get("kanaalsplit") or {}
    base = kanaalsplit.get(fase) or {}
    if not base:
        return []
    kb = list(klant_cfg.get("keybeliefs") or []) + list(extra_keybeliefs or [])
    adjusted = _apply_keybeliefs({fase: base}, kb).get(fase, {})
    shares = _normalize(adjusted)
    if not shares:
        return []
    rows = []
    for kanaal, share in shares.items():
        rows.append({
            "kanaal": kanaal,
            "share": share,
            "budget_eur": round(fase_budget_eur * share, 2),
        })
    # Corrigeer afrondingsrest: grootste kanaal krijgt de diff
    diff = round(fase_budget_eur - sum(r["budget_eur"] for r in rows), 2)
    if diff != 0 and rows:
        biggest = max(rows, key=lambda r: r["budget_eur"])
        biggest["budget_eur"] = round(biggest["budget_eur"] + diff, 2)
    return rows


def split_budget(
    total_budget_eur: float,
    klant_cfg: dict,
    fase_override: dict = None,
    extra_keybeliefs: list = None,
) -> BudgetSplitResult:
    """Simpele auto-mode: totaal -> fase via fasesplit_default -> kanaal."""
    res = BudgetSplitResult(total_budget_eur=float(total_budget_eur))
    if total_budget_eur <= 0:
        res.warnings.append("total_budget_eur is 0 of negatief.")
        return res

    benchmarks = (klant_cfg or {}).get("benchmarks") or {}
    kanaalsplit = benchmarks.get("kanaalsplit") or {}
    fasesplit_default = benchmarks.get("fasesplit_default") or {}
    if not kanaalsplit:
        res.warnings.append("Geen benchmarks.kanaalsplit in klant-config.")
        return res

    fase_pct = fase_override if fase_override else fasesplit_default
    if not fase_pct:
        res.warnings.append("Geen fasesplit beschikbaar - val terug op gelijke verdeling.")
        fase_pct = {fase: 1.0 for fase in kanaalsplit}
    fase_share = _normalize({k: float(v) for k, v in fase_pct.items() if k in kanaalsplit})

    for fase, share in fase_share.items():
        fase_budget = total_budget_eur * share
        kanalen_rows = split_fase_to_kanalen(fase, fase_budget, klant_cfg, extra_keybeliefs)
        for r in kanalen_rows:
            res.rows.append({
                "fase": fase,
                "kanaal": r["kanaal"],
                "pct_binnen_fase": round(r["share"] * 100, 2),
                "pct_totaal": round(share * r["share"] * 100, 2),
                "budget_eur": r["budget_eur"],
            })
        res.per_fase[fase] = round(sum(r["budget_eur"] for r in kanalen_rows), 2)

    for r in res.rows:
        res.per_kanaal[r["kanaal"]] = round(
            res.per_kanaal.get(r["kanaal"], 0.0) + r["budget_eur"], 2
        )

    total = round(sum(r["budget_eur"] for r in res.rows), 2)
    if abs(total - total_budget_eur) > 0.1:
        res.warnings.append(
            f"Totaal na split {total:.2f} wijkt af van ingevoerd budget {total_budget_eur:.2f}."
        )
    return res
