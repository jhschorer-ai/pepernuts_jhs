"""Tactiek-ID generator.

Conventie (v0.2, productlijn eruit):
    {KLANTCODE}-{YYYY}-{MM}-{Campagne}-T{NN}                     (single flight)
    {KLANTCODE}-{YYYY}-{MM}-{Campagne}-D{D}T{NN}                 (multi-flight)

Voorbeelden:
    KLANT-2026-04-Voorjaar-T01                  (1 doorlopende campagneperiode)
    KLANT-2026-03-Voorjaar-D1T01                (flight 1 van meerdere)
    KLANT-2026-03-Voorjaar-D3T05                (flight 3)

Productlijn (BON, SPR, ...) zit NIET in de id; evaluatiemachine leest
die uit de `productlijn_code`-kolom van de plan-Excel - handig als tag,
niet als naming-dimensie.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional


_SLUG_STRIP = re.compile(r"[^A-Za-z0-9]+")


def _slug_campagne(naam: str) -> str:
    """CamelCase-achtige slug: 'Voorjaar 2026' -> 'Voorjaar2026'."""
    tokens = [t for t in _SLUG_STRIP.split(naam or "") if t]
    return "".join(t[:1].upper() + t[1:] for t in tokens)


def _as_date(d) -> date:
    if isinstance(d, str):
        return date.fromisoformat(d[:10])
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    raise TypeError(f"Kan {d!r} niet naar date converteren")


def build_tactiek_id(
    klantcode: str,
    start,
    campagne_naam: str,
    nr: int,
    deel: Optional[int] = None,
) -> str:
    """Bouw 1 tactiek_id.

    Parameters
    ----------
    klantcode     : klant-code uit config (bv. ABCD).
    start         : startdatum - yyyy-mm worden eruit afgeleid.
    campagne_naam : vrije tekst (slugify naar PascalCase).
    nr            : volgnummer 1..99 binnen de flight (of globaal bij single).
    deel          : flight-nummer (1..9). None = single-flight, geen D-prefix.
    """
    if not klantcode:
        raise ValueError("klantcode ontbreekt")
    if nr < 1 or nr > 99:
        raise ValueError(f"tactiek-nr moet 1..99 zijn, kreeg {nr}")

    d = _as_date(start)
    campagne = _slug_campagne(campagne_naam)
    if not campagne:
        raise ValueError("campagne-naam leeg na slugify")

    t_suffix = f"T{nr:02d}"
    if deel is not None:
        if deel < 1 or deel > 9:
            raise ValueError(f"deel moet 1..9 zijn, kreeg {deel}")
        t_suffix = f"D{deel}T{nr:02d}"

    return f"{klantcode.upper()}-{d:%Y}-{d:%m}-{campagne}-{t_suffix}"


def build_tactiek_ids(
    klantcode: str,
    start,
    campagne_naam: str,
    aantal: int,
    deel: Optional[int] = None,
    start_nr: int = 1,
) -> list:
    """Reeks tactiek_id's met oplopende volgnummers."""
    return [
        build_tactiek_id(klantcode, start, campagne_naam, n, deel)
        for n in range(start_nr, start_nr + aantal)
    ]


def derive_productlijn_code(klant_cfg: dict, productlijn_naam: str) -> str:
    """Zoek de 3-letter-code voor een productlijn op in klant_cfg.

    Productlijn zit niet meer in het tactiek_id, maar we gebruiken 'm nog
    voor de `productlijn_code`-tag op plan-rijen (evaluatiemachine-compat).

    Ondersteunt zowel lijst- als dict-vorm (dict-format).
    """
    productlijnen = (klant_cfg or {}).get("productlijnen") or []
    needle = (productlijn_naam or "").strip()
    if not needle:
        return ""
    if isinstance(productlijnen, list):
        for item in productlijnen:
            if isinstance(item, dict):
                code = str(item.get("code", "")).upper()
                if code and code == needle.upper():
                    return code
                if str(item.get("naam", "")).lower() == needle.lower():
                    return code
    if isinstance(productlijnen, dict):
        for key, val in productlijnen.items():
            if str(key).lower() == needle.lower():
                code = str((val or {}).get("code", "")).upper() if isinstance(val, dict) else ""
                if code:
                    return code
        for key, val in productlijnen.items():
            if isinstance(val, dict):
                code = str(val.get("code", "")).upper()
                if code and code == needle.upper():
                    return code
    if re.fullmatch(r"[A-Za-z]{2,4}", needle):
        return needle.upper()
    return ""
