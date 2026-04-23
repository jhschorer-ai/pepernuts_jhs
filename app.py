"""Campagne planner - multi-step Streamlit form.

Draaien:
    streamlit run app.py

6 stappen:
    1. Klant + campagne
    2. Periode
    3. Budget + uren
    4. Kanalen-selectie
    5. Tactieken (per kanaal: doelstelling, doelgroep, cpm, ctr_pct, budget)
    6. Preview & download plan-Excel
"""
from __future__ import annotations

import io
import re
import uuid
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from config.loader import list_klanten, load_klant_config
from generators.flight_planner import Flight, plan_tactieken
from generators.plan_excel import (
    PLAN_COLUMNS,
    PlanContext,
    PlanHeader,
    UrenPost,
    build_plan_rows,
    uren_from_klantconfig,
    write_plan_excel,
)
from generators.tactiek_id import build_tactiek_id
from validators.naming import validate_plan


# ---------- Page setup + state --------------------------------------------------

st.set_page_config(page_title="Campagne planner", layout="wide")

# Init session state
_defaults = {
    "step": 1,
    "klant_code": None,
    "cfg": None,
    "campagne": None,
    "jaar": None,
    "start": None,
    "eind": None,
    "totaal_incl_btw": 25_000,
    "btw_pct": 21.0,
    "uren_posten": [],
    "kanalen": [],
    "tactieken": [],
    "overlap_factor": 0.08,   # 8% default (klein-medium plan)
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

TOTAL_STEPS = 6


def _goto(step: int):
    st.session_state.step = max(1, min(TOTAL_STEPS, step))


# ---------- Header ---------------------------------------------------------------

st.title("Campagne planner")
st.caption("Genereer evaluatie-ready plan-Excel met afgedwongen naming-convention.")
st.progress(st.session_state.step / TOTAL_STEPS,
            text=f"Stap {st.session_state.step} van {TOTAL_STEPS}")


# ---------- STAP 1: Klant + campagne --------------------------------------------

if st.session_state.step == 1:
    st.header("1. Klant & campagne")
    klanten = list_klanten() or ["demo"]
    default_idx = klanten.index(st.session_state.klant_code) if st.session_state.klant_code in klanten else 0
    klant = st.selectbox("Klant", klanten, index=default_idx)

    try:
        cfg = load_klant_config(klant)
    except FileNotFoundError as e:
        st.error(str(e)); st.stop()

    campagnes = cfg.get("campagnes") or []
    # Dropdown met bekende campagnes + optie om zelf in te vullen
    NIEUW = "+ Zelf invullen..."
    labels = [f"{c['code']} - {c['naam']}" for c in campagnes] + [NIEUW]
    idx = st.selectbox("Campagne", range(len(labels)),
                       format_func=lambda i: labels[i])

    if idx < len(campagnes):
        # Bekende campagne gekozen
        campagne = campagnes[idx]
        st.caption(f"**{campagne['naam']}** - productlijn: {campagne.get('productlijn', '-')}, "
                   f"code: `{campagne['code']}`")
        jaar_opties = campagne.get("jaren") or [date.today().year]
        default_jaar_idx = len(jaar_opties) - 1
    else:
        # Custom campagne
        c1, c2 = st.columns([2, 1])
        naam_custom = c1.text_input(
            "Campagnenaam", placeholder="bv. Zomeractie Spaarders",
            value=st.session_state.get("custom_campagne_naam", ""),
        )
        # Productlijn: vrij tekstveld; dropdown alleen als klant-config er een lijst heeft
        productlijnen_cfg = list((cfg.get("productlijnen") or {}).keys())
        recent = st.session_state.get("recent_productlijnen", {})
        recent_voor_klant = recent.get(klant, [])
        if productlijnen_cfg:
            # Dropdown + tekstveld-optie
            NIEUW_PL = "+ eigen invoer..."
            opties = productlijnen_cfg + [NIEUW_PL]
            prev = st.session_state.get("custom_productlijn", "")
            sel_idx = opties.index(prev) if prev in opties else 0
            pl_sel = c2.selectbox("Productlijn (optioneel)", opties, index=sel_idx)
            if pl_sel == NIEUW_PL:
                pl_custom = c2.text_input("Eigen productlijn", value=prev if prev not in productlijnen_cfg else "")
            else:
                pl_custom = pl_sel
        else:
            # Geen productlijn-lijst beschikbaar -> vrij tekstveld met recente suggesties
            pl_custom = c2.text_input(
                "Productlijn (optioneel)",
                value=st.session_state.get("custom_productlijn", ""),
                placeholder=", ".join(recent_voor_klant[:3]) if recent_voor_klant else "bv. retail, zorg, saas",
            )
        st.session_state.custom_productlijn = pl_custom or ""

        # Code auto-afgeleid uit naam (UPPER, geen spaties)
        code_auto = re.sub(r"[^A-Z0-9]", "", (naam_custom or "").upper())[:10] or "CAMP"
        code_custom = st.text_input(
            "Campagne-code (auto)",
            value=st.session_state.get("custom_campagne_code") or code_auto,
            help="Wordt niet in de tactiek-id gebruikt, maar in meta-info",
        )
        if not naam_custom:
            st.info("Vul een campagnenaam in om verder te gaan.")

        # Onthoud voor deze sessie
        st.session_state.custom_campagne_naam = naam_custom or ""
        st.session_state.custom_campagne_code = code_custom or ""
        if pl_custom and pl_custom not in recent_voor_klant:
            recent.setdefault(klant, []).insert(0, pl_custom)
            recent[klant] = recent[klant][:5]
            st.session_state.recent_productlijnen = recent

        campagne = {
            "code": code_custom,
            "naam": naam_custom,
            "productlijn": pl_custom or "",
            "jaren": [date.today().year, date.today().year + 1],
            "_ad_hoc": True,
        } if naam_custom else None
        jaar_opties = [date.today().year, date.today().year + 1]
        default_jaar_idx = 0

    jaar = st.selectbox("Jaar", jaar_opties, index=default_jaar_idx)

    st.divider()
    can_next = campagne is not None and campagne.get("naam")
    if st.button("Volgende", type="primary", disabled=(not can_next)):
        st.session_state.klant_code = klant
        st.session_state.cfg = cfg
        st.session_state.campagne = campagne
        st.session_state.jaar = jaar
        _goto(2); st.rerun()


# ---------- STAP 2: Periode ------------------------------------------------------

elif st.session_state.step == 2:
    st.header("2. Campagneperiode")
    min_start = date.today() + timedelta(days=1)   # op z'n vroegst morgen
    default_start = st.session_state.start or min_start
    if default_start < min_start:
        default_start = min_start
    default_eind = st.session_state.eind or (default_start + timedelta(days=14))
    if default_eind < default_start:
        default_eind = default_start + timedelta(days=14)

    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("Startdatum", value=default_start, min_value=min_start,
                              help="Plannen zijn toekomstig - minimaal morgen.",
                              key="stap2_start")
    # Als de gekozen startdatum verder ligt dan de opgeslagen einddatum,
    # verschuiven we eind automatisch mee (anders crasht min_value-check).
    if default_eind < start:
        default_eind = start + timedelta(days=14)
    with col2:
        # Unieke key per start-datum zodat Streamlit de default herbouwt bij wijziging
        eind = st.date_input("Einddatum", value=default_eind, min_value=start,
                             help="Default = start + 14 dagen, aanpasbaar.",
                             key=f"stap2_eind_{start.isoformat()}")
    if eind < start:
        st.error("Einddatum ligt voor startdatum.")
    else:
        duur = (eind - start).days + 1
        st.caption(f"Campagneduur: **{duur} dagen**.")

    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("Vorige"):
        _goto(1); st.rerun()
    if c2.button("Volgende", type="primary", disabled=(eind < start)):
        st.session_state.start = start
        st.session_state.eind = eind
        _goto(3); st.rerun()


# ---------- STAP 3: Budget + uren -----------------------------------------------

elif st.session_state.step == 3:
    st.header("3. Budget & uren")
    cfg = st.session_state.cfg

    # BTW-modus: klanten waar BTW verrekenbaar is werken meestal met ex-BTW-budgetten;
    # banken (vrijgesteld) met incl-BTW. Vaste tarief 21%.
    klant_type = (cfg.get("klant") or {}).get("type", "").lower()
    default_modus = "incl" if klant_type == "bank" else "ex"
    if "btw_modus" not in st.session_state or st.session_state.btw_modus is None:
        st.session_state.btw_modus = default_modus

    col1, col2 = st.columns(2)
    with col1:
        btw_modus = st.radio(
            "Budget is:",
            options=["ex BTW", "incl BTW"],
            index=0 if st.session_state.btw_modus == "ex" else 1,
            horizontal=True,
            help="Banken (vrijgesteld) werken doorgaans incl BTW; overige klanten ex BTW.",
        )
        st.session_state.btw_modus = "ex" if btw_modus == "ex BTW" else "incl"
    with col2:
        bedrag_label = f"Totaalbudget {btw_modus} (EUR)"
        bedrag = st.number_input(
            bedrag_label,
            min_value=0, value=int(st.session_state.totaal_incl_btw), step=500,
        )
    # Vast BTW-percentage
    btw_pct = 21.0
    st.caption("BTW staat vast op 21%. Input bepaalt of we wel of niet moeten corrigeren.")

    # totaal_incl_btw is altijd het incl-bedrag intern (header rekent ex-btw uit dat incl)
    if st.session_state.btw_modus == "ex":
        totaal_incl_btw = round(bedrag * 1.21, 2)
    else:
        totaal_incl_btw = bedrag

    st.subheader("Uren-posten")
    default_posten = st.session_state.uren_posten or uren_from_klantconfig(cfg)
    uren = []
    for i, p in enumerate(default_posten):
        c1, c2, c3 = st.columns([3, 1, 1])
        naam = c1.text_input(f"post_{i}", value=p.categorie,
                             key=f"upn_{i}", label_visibility="collapsed")
        tar  = c2.number_input(f"tarief_{i}", 0.0, value=float(p.tarief),
                               step=5.0, key=f"upt_{i}", label_visibility="collapsed")
        uur  = c3.number_input(f"uren_{i}", 0.0, value=float(p.aantal_uren),
                               step=1.0, key=f"upu_{i}", label_visibility="collapsed")
        if naam and uur > 0:
            uren.append(UrenPost(naam, tar, uur))

    # Live preview budget-opbouw
    h_preview = PlanHeader(
        klant=(cfg.get("klant") or {}).get("naam", ""),
        campagne=st.session_state.campagne["naam"],
        start=st.session_state.start, eind=st.session_state.eind,
        totaal_incl_btw=float(totaal_incl_btw), btw_pct=float(btw_pct),
        uren_posten=uren,
    )
    uren_pct = (h_preview.uren_ex_btw / h_preview.totaal_ex_btw * 100.0) if h_preview.totaal_ex_btw > 0 else 0
    st.info(
        f"**Totaal ex BTW**: € {h_preview.totaal_ex_btw:,.0f}  |  "
        f"**Uren**: € {h_preview.uren_ex_btw:,.0f}  ({uren_pct:.0f}% van totaal)  |  "
        f"**Media ex BTW**: € {h_preview.media_ex_btw:,.0f}"
    )
    if h_preview.media_ex_btw <= 0:
        st.error("Media-budget <= 0 na aftrek uren. Verhoog totaalbudget of verlaag uren.")

    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("Vorige"):
        _goto(2); st.rerun()
    if c2.button("Volgende", type="primary",
                 disabled=(h_preview.media_ex_btw <= 0)):
        st.session_state.totaal_incl_btw = totaal_incl_btw
        st.session_state.btw_pct = btw_pct
        st.session_state.uren_posten = uren
        _goto(4); st.rerun()


# ---------- STAP 4: Kanalen -----------------------------------------------------

elif st.session_state.step == 4:
    st.header("4. Kanalen")
    cfg = st.session_state.cfg
    alle_kanalen = cfg.get("kanalen") or {}
    opties = list(alle_kanalen.keys())
    labels = {k: alle_kanalen[k].get("label", k) for k in opties}

    st.caption("Kies welke kanalen je in de planning wil opnemen.")
    default = st.session_state.kanalen or ["meta", "linkedin", "google_ads"]
    gekozen = st.multiselect(
        "Kanalen", opties,
        default=[k for k in default if k in opties],
        format_func=lambda k: labels.get(k, k),
    )
    if gekozen:
        st.success(f"{len(gekozen)} kanalen geselecteerd.")

    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("Vorige"):
        _goto(3); st.rerun()
    if c2.button("Volgende", type="primary", disabled=(not gekozen)):
        st.session_state.kanalen = gekozen
        # Initialiseer tactieken (1 per kanaal) met defaults uit klantconfig
        kpi_t = cfg.get("kpi_targets") or {}
        existing_by_kanaal = {t["kanaal"]: t for t in (st.session_state.tactieken or [])}
        new_tactieken = []
        for k in gekozen:
            prev = existing_by_kanaal.get(k, {})
            # Default doelstelling voor dit kanaal: kijk in benchmarks.kanaalsplit
            # welke fase dit kanaal het sterkst heeft; anders 'awareness'.
            split = (cfg.get("benchmarks") or {}).get("kanaalsplit") or {}
            best_fase = "awareness"; best_val = -1
            for fase, kanalen in split.items():
                v = kanalen.get(k, 0)
                if v and v > best_val:
                    best_val = v; best_fase = fase
            fase = prev.get("doelstelling", best_fase)
            fase_kpi = kpi_t.get(fase) or {}
            new_tactieken.append({
                "kanaal": k,
                "doelstelling": fase,
                "doelgroep": prev.get("doelgroep", ""),
                "cpm": prev.get("cpm", fase_kpi.get("cpm")),
                "ctr_pct": prev.get("ctr_pct", fase_kpi.get("ctr_pct")),
                "budget": prev.get("budget", 0.0),
            })
        st.session_state.tactieken = new_tactieken
        _goto(5); st.rerun()


# ---------- STAP 5: Tactieken -----------------------------------------------------

elif st.session_state.step == 5:
    st.header("5. Tactieken invullen")
    cfg = st.session_state.cfg
    fases = list((cfg.get("fases") or {}).keys()) or [
        "awareness", "consideratie", "conversie", "loyalty",
    ]
    alle_kanalen = cfg.get("kanalen") or {}
    gekozen_kanalen = st.session_state.kanalen
    kpi_t = cfg.get("kpi_targets") or {}
    split = (cfg.get("benchmarks") or {}).get("kanaalsplit") or {}

    # Media-budget (ex BTW) als target
    h_preview = PlanHeader(
        klant=(cfg.get("klant") or {}).get("naam", ""),
        campagne=st.session_state.campagne["naam"],
        start=st.session_state.start, eind=st.session_state.eind,
        totaal_incl_btw=float(st.session_state.totaal_incl_btw),
        btw_pct=float(st.session_state.btw_pct),
        uren_posten=st.session_state.uren_posten,
    )
    media_target = h_preview.media_ex_btw
    st.caption(f"Te verdelen media-budget: **€ {media_target:,.0f}** (ex BTW, ex uren)")

    def _default_doelstelling(kanaal: str) -> str:
        best_f, best_v = "awareness", -1
        for fase, kanalen in split.items():
            v = kanalen.get(kanaal, 0)
            if v and v > best_v:
                best_v, best_f = v, fase
        return best_f

    # Formaat-lijst + format-specifieke benchmarks
    FORMATEN = ["video", "audio", "static", "carousel",
                "native", "html5_hi", "html5_standard"]
    bpf = cfg.get("benchmarks_per_format") or {}
    bpf_combi = bpf.get("by_combi") or {}
    bpf_formaat = bpf.get("by_formaat") or {}
    bpf_kanaal = bpf.get("by_kanaal") or {}

    def _lookup_benchmarks(kanaal: str, formaat: str | None) -> dict:
        """Haal cpm/ctr_pct defaults in volgorde: combi > formaat > kanaal."""
        if kanaal and formaat:
            c = (bpf_combi.get(kanaal) or {}).get(formaat)
            if c:
                return c
        if formaat:
            f = bpf_formaat.get(formaat)
            if f:
                return f
        if kanaal:
            k = bpf_kanaal.get(kanaal)
            if k:
                return k
        return {}

    def _defaults_voor_tactiek(kanaal: str, formaat: str = None) -> dict:
        doel = _default_doelstelling(kanaal)
        fase_kpi = kpi_t.get(doel) or {}
        bm = _lookup_benchmarks(kanaal, formaat)
        return {
            "kanaal": kanaal, "formaat": formaat,
            "doelstelling": doel, "doelgroep": "",
            "cpm": bm.get("cpm", fase_kpi.get("cpm")),
            "cpc": fase_kpi.get("cpc"),
            "cpa": fase_kpi.get("cpa"),
            "ctr_pct": bm.get("ctr_pct", fase_kpi.get("ctr_pct")),
            "gcf": fase_kpi.get("gcf"),
            "budget_pct": None,
            "budget": 0.0,
        }

    # Init tactieken bij eerste binnenkomst: 1 per gekozen kanaal
    if not st.session_state.tactieken:
        st.session_state.tactieken = [_defaults_voor_tactiek(k) for k in gekozen_kanalen]

    # Filter weg wat niet meer bij gekozen kanalen hoort
    st.session_state.tactieken = [
        t for t in st.session_state.tactieken if t["kanaal"] in gekozen_kanalen
    ]

    st.markdown(
        "Vul de tactieken in. **Meerdere tactieken per kanaal mag** (bv. 2x Meta: "
        "awareness + conversie). Gebruik de **+** onderaan de tabel om rijen toe te voegen. "
        "**Budget**: vul ofwel EUR in (kolom `budget_eur`), of % van media-budget (kolom `budget_pct`) "
        "- de andere rekent automatisch mee bij het drukken op Volgende."
    )

    # Overlap-factor tussen kanalen (voor ontdubbelen bereik in totalen-rij)
    st.markdown("#### Verwachte overlap tussen kanalen")
    st.caption(
        "Iemand kan een uiting op meerdere kanalen zien; die overlap moet van het samengetelde "
        "bereik af. **Klein plan:** 1-6% • **Medium:** 12-19% • **Groot:** 28-32%."
    )
    overlap_factor = st.slider(
        "Overlap %", 0, 35,
        value=int(round((st.session_state.overlap_factor or 0.08) * 100)),
        step=1, help="Verlaagt het totaal-bereik in de Excel: netto = SUM * (1 - overlap).",
    ) / 100.0
    st.session_state.overlap_factor = overlap_factor

    # Initialiseer alle kolommen die de editor nodig heeft
    editor_df = pd.DataFrame(st.session_state.tactieken)
    for col in ("kanaal", "formaat", "doelstelling", "doelgroep",
                "budget_pct", "budget", "cpm", "cpc", "cpa", "ctr_pct", "gcf"):
        if col not in editor_df.columns:
            editor_df[col] = None
    editor_df = editor_df[[
        "kanaal", "formaat", "doelstelling", "doelgroep",
        "budget_pct", "budget", "cpm", "cpc", "cpa", "ctr_pct", "gcf",
    ]]

    edited = st.data_editor(
        editor_df,
        num_rows="dynamic",
        use_container_width=True,
        key="tactiek_editor",
        column_config={
            "kanaal": st.column_config.SelectboxColumn(
                "Kanaal", options=gekozen_kanalen, required=True),
            "formaat": st.column_config.SelectboxColumn(
                "Formaat", options=FORMATEN,
                help="Beinvloedt CPM/CTR-defaults (bv. native is goedkoper, html5_hi duurder)."),
            "doelstelling": st.column_config.SelectboxColumn(
                "Doelstelling", options=fases, required=True),
            "doelgroep": st.column_config.TextColumn(
                "Doelgroep", help="bv. 25-54, spaargeld-geinteresseerden"),
            "budget_pct": st.column_config.NumberColumn(
                "Budget %", format="%.1f%%", min_value=0.0, max_value=100.0, step=1.0,
                help="Percentage van totaal media-budget. Laat leeg als je EUR invult."),
            "budget": st.column_config.NumberColumn(
                "Budget", format="€ %d", min_value=0.0, step=100.0,
                help="EUR. Laat leeg als je een percentage invult."),
            "cpm": st.column_config.NumberColumn(
                "CPM", format="€ %.2f", min_value=0.0, step=0.5,
                help="Cost per mille - input voor impressies & bereik"),
            "cpc": st.column_config.NumberColumn(
                "CPC", format="€ %.2f", min_value=0.0, step=0.05,
                help="Cost per click - input voor clicks (of CTR als alternatief)"),
            "cpa": st.column_config.NumberColumn(
                "CPA", format="€ %.2f", min_value=0.0, step=1.0,
                help="Cost per acquisition - input voor conversies"),
            "ctr_pct": st.column_config.NumberColumn(
                "CTR %", format="%.2f%%", min_value=0.0, max_value=100.0, step=0.1,
                help="Click-through rate - alternatief voor CPC"),
            "gcf": st.column_config.NumberColumn(
                "GCF", format="%.1f", min_value=0.0, step=0.1,
                help="Gemiddelde contactfrequentie - impressies/bereik"),
        },
    )

    # Sync terug naar session_state: auto-apply benchmarks per (kanaal, formaat)
    # en budget-conversie tussen EUR en %.
    tactieken_new = []
    for _, row in edited.iterrows():
        k = row.get("kanaal")
        if pd.isna(k) or not k:
            continue
        formaat = row.get("formaat") if row.get("formaat") and not pd.isna(row.get("formaat")) else None

        def _g(key):
            v = row.get(key)
            return None if v is None or pd.isna(v) or v == 0 else float(v)

        cpm = _g("cpm"); cpc = _g("cpc"); cpa = _g("cpa")
        ctr_pct = _g("ctr_pct"); gcf = _g("gcf")

        # Auto-fill cpm/ctr uit benchmarks_per_format als leeg
        bm = _lookup_benchmarks(k, formaat)
        if cpm is None and bm.get("cpm"):
            cpm = float(bm["cpm"])
        if ctr_pct is None and bm.get("ctr_pct"):
            ctr_pct = float(bm["ctr_pct"])

        # Budget: ofwel pct ofwel EUR - pct wint als beide ingevuld
        bpct = _g("budget_pct")
        beur = _g("budget")
        if bpct is not None and bpct > 0:
            budget_eur = round(media_target * bpct / 100.0, 2)
        else:
            budget_eur = beur or 0.0
            if budget_eur and media_target > 0:
                bpct = round(budget_eur / media_target * 100.0, 2)

        tactieken_new.append({
            "kanaal": k, "formaat": formaat,
            "doelstelling": row.get("doelstelling") or _default_doelstelling(k),
            "doelgroep": row.get("doelgroep") or "",
            "cpm": cpm, "cpc": cpc, "cpa": cpa,
            "ctr_pct": ctr_pct, "gcf": gcf,
            "budget_pct": bpct,
            "budget": budget_eur,
        })

    # Running total
    tot = sum(t["budget"] for t in tactieken_new)
    diff = round(media_target - tot, 2)
    if abs(diff) < 0.5:
        st.success(f"Som budget: EUR {tot:,.0f}  klopt met media-budget")
    elif diff > 0:
        st.warning(f"Som budget: EUR {tot:,.0f}  -  nog EUR {diff:,.0f} te verdelen")
    else:
        st.error(f"Som budget: EUR {tot:,.0f}  -  EUR {-diff:,.0f} teveel!")

    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("Vorige"):
        st.session_state.tactieken = tactieken_new
        _goto(4); st.rerun()
    can_next = (len(tactieken_new) > 0
                and all(t["budget"] > 0 for t in tactieken_new))
    if c2.button("Volgende", type="primary", disabled=(not can_next)):
        st.session_state.tactieken = tactieken_new
        _goto(6); st.rerun()


# ---------- STAP 6: Preview + download ------------------------------------------

elif st.session_state.step == 6:
    st.header("6. Preview & download")
    cfg = st.session_state.cfg
    campagne = st.session_state.campagne
    klantcode = str((cfg.get("klant") or {}).get("code", "")).upper()

    h = PlanHeader(
        klant=(cfg.get("klant") or {}).get("naam", ""),
        campagne=campagne["naam"],
        start=st.session_state.start, eind=st.session_state.eind,
        totaal_incl_btw=float(st.session_state.totaal_incl_btw),
        btw_pct=float(st.session_state.btw_pct),
        uren_posten=st.session_state.uren_posten,
    )

    # Bouw plan-tactieken uit session_state.tactieken
    tactieken_plan = []
    for i, t in enumerate(st.session_state.tactieken, start=1):
        tid = build_tactiek_id(
            klantcode=klantcode,
            start=st.session_state.start,
            campagne_naam=campagne["naam"],
            nr=i, deel=None,
        )
        tactieken_plan.append({
            "tactiek_id": tid,
            "fase": t["doelstelling"],
            "kanaal": t["kanaal"],
            "format": t.get("formaat", ""),
            "doelgroep": t.get("doelgroep", ""),
            "cpm": t.get("cpm"), "cpc": t.get("cpc"), "cpa": t.get("cpa"),
            "ctr_pct": t.get("ctr_pct"), "gcf": t.get("gcf"),
            "budget": t["budget"],
            "flight_start": st.session_state.start,
            "flight_eind": st.session_state.eind,
        })

    ctx = PlanContext(
        klant_cfg=cfg,
        campagne={**campagne, "jaar": st.session_state.jaar},
        benchmarks_used=((cfg.get("benchmarks") or {}).get("kanaalsplit") or {}),
        keybeliefs_used=list(cfg.get("keybeliefs") or []),
        header=h,
        overlap_factor=float(st.session_state.overlap_factor or 0.08),
    )
    plan_df = build_plan_rows(tactieken_plan, ctx)

    # ---- Editable planning-blok + afgeleide verwachte-resultaten-blok ----
    st.subheader("Plan (editable)")
    st.caption("Pas cellen aan in de onderstaande tabel; afgeleide metrieken herrekenen zodra je op Vernieuwen klikt.")

    id_cols = [c for c in ["tactiek_id", "doelstelling", "kanaal", "format", "doelgroep",
                            "flight_start", "flight_eind"] if c in plan_df.columns]
    input_cols = [c for c in ["budget", "cpm", "cpc", "cpa", "ctr_pct", "gcf"]
                  if c in plan_df.columns]
    # Conditionele derived-kolommen: verberg wat niet relevant is voor deze planning.
    any_cpa = any(not pd.isna(v) and v for v in plan_df.get("cpa", pd.Series(dtype=float)))
    any_gcf = any(not pd.isna(v) and v for v in plan_df.get("gcf", pd.Series(dtype=float)))
    # eCPC bestaat als er clicks zijn (dwz cpc of (cpm+ctr) ingevuld)
    any_clicks_input = any(
        (not pd.isna(plan_df.at[i, "cpc"]) and plan_df.at[i, "cpc"])
        or (not pd.isna(plan_df.at[i, "cpm"]) and plan_df.at[i, "cpm"]
            and not pd.isna(plan_df.at[i, "ctr_pct"]) and plan_df.at[i, "ctr_pct"])
        for i in plan_df.index
    )
    derived_cols = []
    if any(not pd.isna(v) and v for v in plan_df.get("cpm", pd.Series(dtype=float))):
        derived_cols.append("impressies")
    if any_clicks_input:
        derived_cols.append("clicks")
        derived_cols.append("ecpc")
    if any_gcf:
        derived_cols.append("bereik")
    if any_cpa:
        derived_cols.append("conversies")

    editable_df = plan_df[id_cols + input_cols].copy()
    edited = st.data_editor(
        editable_df, use_container_width=True, height=280, key="preview_editor",
        disabled=["tactiek_id", "kanaal", "flight_start", "flight_eind"],
        column_config={
            "budget":  st.column_config.NumberColumn("Budget",  format="€ %d", min_value=0.0, step=100.0),
            "cpm":     st.column_config.NumberColumn("CPM",     format="€ %.2f"),
            "cpc":     st.column_config.NumberColumn("CPC",     format="€ %.2f"),
            "cpa":     st.column_config.NumberColumn("CPA",     format="€ %.2f"),
            "ctr_pct": st.column_config.NumberColumn("CTR %",   format="%.2f%%"),
            "gcf":     st.column_config.NumberColumn("GCF",     format="%.1f"),
        },
    )

    # Herbouw plan met edited inputs
    tacts_edited = []
    for _, row in edited.iterrows():
        if pd.isna(row.get("tactiek_id")) or not row.get("tactiek_id"):
            continue
        tacts_edited.append({
            "tactiek_id": row["tactiek_id"],
            "fase": row.get("doelstelling"),
            "kanaal": row.get("kanaal"),
            "doelgroep": row.get("doelgroep", "") or "",
            "cpm":     None if pd.isna(row.get("cpm"))     else float(row.get("cpm") or 0) or None,
            "cpc":     None if pd.isna(row.get("cpc"))     else float(row.get("cpc") or 0) or None,
            "cpa":     None if pd.isna(row.get("cpa"))     else float(row.get("cpa") or 0) or None,
            "ctr_pct": None if pd.isna(row.get("ctr_pct")) else float(row.get("ctr_pct") or 0) or None,
            "gcf":     None if pd.isna(row.get("gcf"))     else float(row.get("gcf") or 0) or None,
            "budget":  0.0 if pd.isna(row.get("budget"))   else float(row.get("budget") or 0),
            "flight_start": st.session_state.start,
            "flight_eind": st.session_state.eind,
        })
    plan_df = build_plan_rows(tacts_edited, ctx)

    # Verwachte resultaten (band-kop + data)
    # Filter inputs die niet gebruikt worden in derived (bv. cpa weg als niemand 'm invult)
    input_cols_shown = ["budget"]
    if "impressies" in derived_cols or any_clicks_input:
        input_cols_shown.append("cpm")
    if any(not pd.isna(plan_df.at[i, "cpc"]) and plan_df.at[i, "cpc"] for i in plan_df.index):
        input_cols_shown.append("cpc")
    if any_cpa:
        input_cols_shown.append("cpa")
    if any(not pd.isna(plan_df.at[i, "ctr_pct"]) and plan_df.at[i, "ctr_pct"] for i in plan_df.index):
        input_cols_shown.append("ctr_pct")
    if any_gcf:
        input_cols_shown.append("gcf")

    st.subheader("Verwachte resultaten")
    st.caption("Afgeleid uit budget en ingevulde kostenmetrieken: "
               "impressies = budget / CPM x 1000,  clicks = budget / CPC (of impressies x CTR%),  "
               "eCPC = budget / clicks,  bereik = impressies / GCF,  conversies = budget / CPA. "
               "Kolommen zonder relevante input worden automatisch verborgen.")
    preview_cols = ["tactiek_id"] + input_cols_shown + derived_cols
    st.dataframe(
        plan_df[[c for c in preview_cols if c in plan_df.columns]],
        use_container_width=True, height=260,
    )

    rep = validate_plan(plan_df.to_dict(orient="records"), cfg)
    if rep.ok:
        st.success(f"Plan is geldig ({len(plan_df)} tactieken).")
    else:
        st.error(f"{len(rep.issues)} issue(s):")
        st.dataframe(pd.DataFrame(rep.errors_as_df_rows()), use_container_width=True)

    st.divider()
    c1, c2 = st.columns([1, 2])
    if c1.button("Vorige"):
        _goto(5); st.rerun()
    if c2.button("Genereer plan-Excel", type="primary"):
        out = Path("/tmp") / f"plan_{klantcode}_{campagne['code']}_{st.session_state.jaar}.xlsx"
        write_plan_excel(out, plan_df=plan_df, ctx=ctx)
        buf = io.BytesIO(out.read_bytes())
        st.download_button(
            label=f"Download {out.name}",
            data=buf, file_name=out.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.success("Excel gegenereerd - klik hierboven om te downloaden.")

    st.divider()
    if st.button("Opnieuw beginnen"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
