"""Beheer klant-configs.

Streamlit-tool waarmee specialisten een bestaande klant-config kunnen
aanpassen of een nieuwe kunnen aanmaken. Output is een YAML-bestand dat
de specialist downloadt en committed naar de repo (config/klanten/).
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from config.loader import list_klanten, load_klant_config


st.set_page_config(page_title="Beheer klant-configs", layout="wide")
st.title("Beheer klant-configs")
st.caption(
    "Bewerk bestaande klant-configs of maak een nieuwe. Onderaan download "
    "je het YAML-bestand. Commit daarna naar de repo in `config/klanten/` "
    "en push om de Cloud-deploy up-to-date te zetten."
)


# ---------- 1. Klant kiezen / nieuw ------------------------------------------

st.header("1. Klant")
klanten = list_klanten() or []
NIEUW = "+ Nieuwe klant..."
opties = klanten + [NIEUW]
sel = st.selectbox(
    "Kies een bestaande klant of maak een nieuwe",
    opties, index=0 if klanten else 0,
)

if sel == NIEUW:
    cfg = {
        "klant": {"code": "", "naam": "", "type": ""},
        "financieel": {"btw_pct": 21.0, "valuta": "EUR", "agency_fee_pct": 0.0},
        "kanalen": {},
        "fases": {
            "awareness":    {"label": "Awareness",    "default_kpi": "reach"},
            "consideratie": {"label": "Consideratie", "default_kpi": "ctr"},
            "conversie":    {"label": "Conversie",    "default_kpi": "cpa"},
            "loyalty":      {"label": "Loyalty",      "default_kpi": "open_rate"},
        },
        "kpi_targets": {},
        "benchmarks_per_format": {"by_kanaal": {}, "by_formaat": {}, "by_combi": {}},
        "campagnes": [],
        "keybeliefs": [],
        "uren_defaults": {
            "tarief": 110,
            "posten": {
                "setup campagne":     8,
                "beheer campagne":    12,
                "reporting campagne": 12,
                "project management":  6,
            },
        },
    }
    klant_code_default = ""
else:
    try:
        cfg = load_klant_config(sel)
    except FileNotFoundError as e:
        st.error(str(e)); st.stop()
    klant_code_default = sel


# ---------- 2. Klant-basis ---------------------------------------------------

st.header("2. Basis")
c1, c2, c3 = st.columns(3)
klant = cfg.get("klant") or {}
with c1:
    code = st.text_input("Klantcode", value=klant.get("code") or klant_code_default,
                         help="Kort, UPPERCASE in tactiek-id. Bv. 'ACME', 'DEMOKLANT'.")
with c2:
    naam = st.text_input("Klantnaam", value=klant.get("naam", ""))
with c3:
    type_ = st.selectbox(
        "Type", ["", "bank", "retail", "zorg", "saas", "onderwijs", "overig"],
        index=["", "bank", "retail", "zorg", "saas", "onderwijs", "overig"].index(
            klant.get("type", "")) if klant.get("type") in
            ["", "bank", "retail", "zorg", "saas", "onderwijs", "overig"] else 0,
        help="Banken zijn vrijgesteld van BTW-verrekening.",
    )

cfg["klant"] = {"code": code.lower() if code else "", "naam": naam, "type": type_}


# ---------- 3. Uren-defaults -------------------------------------------------

st.header("3. Uren-defaults")
ud = cfg.get("uren_defaults") or {}
c1, c2 = st.columns([1, 3])
with c1:
    tarief = st.number_input("Uurtarief (€)", min_value=0.0,
                              value=float(ud.get("tarief", 110)), step=5.0)
posten_items = list((ud.get("posten") or {}).items())
posten_df = pd.DataFrame(
    posten_items or [("setup campagne", 8)],
    columns=["post", "uren"],
)
posten_edited = st.data_editor(
    posten_df, num_rows="dynamic", use_container_width=True,
    key="posten_editor",
    column_config={
        "post": st.column_config.TextColumn("Post", required=True),
        "uren": st.column_config.NumberColumn("Uren", min_value=0.0, step=1.0, required=True),
    },
)
posten_new = {}
for _, row in posten_edited.iterrows():
    if not pd.isna(row.get("post")) and row.get("post"):
        posten_new[str(row["post"])] = float(row.get("uren") or 0)
cfg["uren_defaults"] = {"tarief": tarief, "posten": posten_new}


# ---------- 4. Kanalen --------------------------------------------------------

st.header("4. Kanalen")
st.caption("De kanalen waar de planner uit kan kiezen. Key is wat in de plan-Excel komt.")
kanalen = cfg.get("kanalen") or {}
kanalen_rows = [
    {"key": k, "label": (v or {}).get("label", k), "type": (v or {}).get("type", "")}
    for k, v in kanalen.items()
]
if not kanalen_rows:
    kanalen_rows = [{"key": "meta", "label": "Meta (FB/IG)", "type": "betaald_social"}]
kanalen_df = pd.DataFrame(kanalen_rows)
kanalen_edited = st.data_editor(
    kanalen_df, num_rows="dynamic", use_container_width=True,
    key="kanalen_editor",
    column_config={
        "key": st.column_config.TextColumn("Key", required=True,
            help="Interne id, lowercase, geen spaties. Bv. 'meta', 'google_ads'."),
        "label": st.column_config.TextColumn("Label", required=True,
            help="Wat de planner ziet in de dropdown."),
        "type": st.column_config.SelectboxColumn("Type",
            options=["betaald_social", "sea", "display", "video", "audio",
                     "ooh", "print", "owned", "other"]),
    },
)
kanalen_new = {}
for _, row in kanalen_edited.iterrows():
    k = row.get("key")
    if pd.isna(k) or not k:
        continue
    kanalen_new[str(k)] = {
        "label": row.get("label") or str(k),
        "type":  row.get("type") or "other",
    }
cfg["kanalen"] = kanalen_new


# ---------- 5. KPI-targets per fase ------------------------------------------

st.header("5. KPI-targets per fase")
st.caption("Defaults voor kostenmetrieken per funnel-fase. Planner kan per tactiek overschrijven.")
kpi_t = cfg.get("kpi_targets") or {}
fases = cfg.get("fases") or {}
rows = []
for fase_key in (fases.keys() or ["awareness", "consideratie", "conversie", "loyalty"]):
    v = kpi_t.get(fase_key) or {}
    rows.append({
        "fase": fase_key,
        "primary": v.get("primary", (fases.get(fase_key) or {}).get("default_kpi", "")),
        "cpm": v.get("cpm"), "cpc": v.get("cpc"), "cpa": v.get("cpa"),
        "ctr_pct": v.get("ctr_pct"), "gcf": v.get("gcf"),
    })
kpi_df = pd.DataFrame(rows)
kpi_edited = st.data_editor(
    kpi_df, num_rows="fixed", use_container_width=True,
    key="kpi_editor",
    column_config={
        "fase": st.column_config.TextColumn("Fase", disabled=True),
        "primary": st.column_config.SelectboxColumn("Primaire KPI",
            options=["reach", "ctr", "cpa", "open_rate", "conversies", "aanvragen"]),
        "cpm": st.column_config.NumberColumn("CPM", format="€ %.2f", min_value=0.0),
        "cpc": st.column_config.NumberColumn("CPC", format="€ %.2f", min_value=0.0),
        "cpa": st.column_config.NumberColumn("CPA", format="€ %.2f", min_value=0.0),
        "ctr_pct": st.column_config.NumberColumn("CTR %", format="%.2f%%", min_value=0.0, max_value=100.0),
        "gcf": st.column_config.NumberColumn("GCF", format="%.1f", min_value=0.0),
    },
)
kpi_new = {}
def _nn(v):
    return None if pd.isna(v) or not v else float(v)
for _, row in kpi_edited.iterrows():
    fase_key = row.get("fase")
    if not fase_key:
        continue
    entry = {"primary": row.get("primary") or None}
    for m in ("cpm", "cpc", "cpa", "ctr_pct", "gcf"):
        v = _nn(row.get(m))
        if v is not None and v > 0:
            entry[m] = v
    kpi_new[str(fase_key)] = {k: v for k, v in entry.items() if v is not None}
cfg["kpi_targets"] = kpi_new


# ---------- 6. Benchmarks per (kanaal, formaat) ------------------------------

st.header("6. Benchmarks per (kanaal, formaat)")
st.caption("Lookup bij de tactiek-invoer: by_combi > by_formaat > by_kanaal.")

bpf = cfg.get("benchmarks_per_format") or {}
FORMATEN = ["video", "audio", "static", "carousel", "native", "html5_hi", "html5_standard"]

# 6a. Per kanaal
st.subheader("By kanaal (platform-default)")
by_kanaal = bpf.get("by_kanaal") or {}
rows_k = [{"kanaal": k, "cpm": v.get("cpm"), "ctr_pct": v.get("ctr_pct")}
          for k, v in by_kanaal.items()] or [{"kanaal": "", "cpm": None, "ctr_pct": None}]
kanaal_opts = list(cfg["kanalen"].keys())
by_kanaal_edited = st.data_editor(
    pd.DataFrame(rows_k), num_rows="dynamic", use_container_width=True,
    key="bpf_kanaal",
    column_config={
        "kanaal": st.column_config.SelectboxColumn("Kanaal", options=kanaal_opts),
        "cpm": st.column_config.NumberColumn("CPM", format="€ %.2f", min_value=0.0),
        "ctr_pct": st.column_config.NumberColumn("CTR %", format="%.2f%%", min_value=0.0, max_value=100.0),
    },
)

# 6b. Per formaat
st.subheader("By formaat (alle kanalen, bv. 'native')")
by_formaat = bpf.get("by_formaat") or {}
rows_f = [{"formaat": k, "cpm": v.get("cpm"), "ctr_pct": v.get("ctr_pct")}
          for k, v in by_formaat.items()] or [{"formaat": "", "cpm": None, "ctr_pct": None}]
by_formaat_edited = st.data_editor(
    pd.DataFrame(rows_f), num_rows="dynamic", use_container_width=True,
    key="bpf_formaat",
    column_config={
        "formaat": st.column_config.SelectboxColumn("Formaat", options=FORMATEN),
        "cpm": st.column_config.NumberColumn("CPM", format="€ %.2f", min_value=0.0),
        "ctr_pct": st.column_config.NumberColumn("CTR %", format="%.2f%%", min_value=0.0, max_value=100.0),
    },
)

# 6c. Specifieke combinaties
st.subheader("By combi (specifiek: kanaal + formaat)")
by_combi = bpf.get("by_combi") or {}
rows_c = []
for k, per_f in by_combi.items():
    for f, v in (per_f or {}).items():
        rows_c.append({"kanaal": k, "formaat": f, "cpm": v.get("cpm"), "ctr_pct": v.get("ctr_pct")})
if not rows_c:
    rows_c = [{"kanaal": "", "formaat": "", "cpm": None, "ctr_pct": None}]
by_combi_edited = st.data_editor(
    pd.DataFrame(rows_c), num_rows="dynamic", use_container_width=True,
    key="bpf_combi",
    column_config={
        "kanaal": st.column_config.SelectboxColumn("Kanaal", options=kanaal_opts),
        "formaat": st.column_config.SelectboxColumn("Formaat", options=FORMATEN),
        "cpm": st.column_config.NumberColumn("CPM", format="€ %.2f", min_value=0.0),
        "ctr_pct": st.column_config.NumberColumn("CTR %", format="%.2f%%", min_value=0.0, max_value=100.0),
    },
)

# Sync benchmarks_per_format terug
def _nn(v):
    return None if pd.isna(v) or not v else float(v)
bpf_new = {"by_kanaal": {}, "by_formaat": {}, "by_combi": {}}
for _, r in by_kanaal_edited.iterrows():
    k = r.get("kanaal")
    if pd.isna(k) or not k: continue
    e = {}
    for m in ("cpm", "ctr_pct"):
        v = _nn(r.get(m))
        if v is not None: e[m] = v
    if e: bpf_new["by_kanaal"][str(k)] = e
for _, r in by_formaat_edited.iterrows():
    f = r.get("formaat")
    if pd.isna(f) or not f: continue
    e = {}
    for m in ("cpm", "ctr_pct"):
        v = _nn(r.get(m))
        if v is not None: e[m] = v
    if e: bpf_new["by_formaat"][str(f)] = e
for _, r in by_combi_edited.iterrows():
    k, f = r.get("kanaal"), r.get("formaat")
    if pd.isna(k) or not k or pd.isna(f) or not f: continue
    e = {}
    for m in ("cpm", "ctr_pct"):
        v = _nn(r.get(m))
        if v is not None: e[m] = v
    if e:
        bpf_new["by_combi"].setdefault(str(k), {})[str(f)] = e
cfg["benchmarks_per_format"] = bpf_new


# ---------- 7. Campagnes (optioneel) -----------------------------------------

st.header("7. Campagnes (optioneel)")
st.caption("Voor-gedefinieerde campagnes waar de planner uit kan kiezen. Ad-hoc campagnes kunnen altijd.")
camps = cfg.get("campagnes") or []
camp_rows = [{
    "code": c.get("code", ""),
    "naam": c.get("naam", ""),
    "productlijn": c.get("productlijn", ""),
    "jaren": ",".join(str(j) for j in (c.get("jaren") or [])),
} for c in camps] or [{"code": "", "naam": "", "productlijn": "", "jaren": ""}]
camp_edited = st.data_editor(
    pd.DataFrame(camp_rows), num_rows="dynamic", use_container_width=True,
    key="camp_editor",
    column_config={
        "code": st.column_config.TextColumn("Code", help="UPPERCASE, geen spaties"),
        "naam": st.column_config.TextColumn("Naam"),
        "productlijn": st.column_config.TextColumn("Productlijn (optioneel)"),
        "jaren": st.column_config.TextColumn("Jaren", help="Comma-separated, bv. 2025,2026"),
    },
)
camps_new = []
for _, r in camp_edited.iterrows():
    if pd.isna(r.get("code")) or not r.get("code"): continue
    jaren_str = r.get("jaren", "") or ""
    jaren = []
    for j in re.split(r"[,\s]+", jaren_str):
        if j.strip().isdigit():
            jaren.append(int(j.strip()))
    camps_new.append({
        "code": str(r["code"]).upper(),
        "naam": str(r.get("naam") or ""),
        "productlijn": str(r.get("productlijn") or ""),
        "jaren": jaren or [],
    })
cfg["campagnes"] = camps_new


# ---------- 8. Keybeliefs (optioneel) ----------------------------------------

st.header("8. Keybeliefs (optioneel)")
st.caption("Multipliers op benchmark-split. 1.0 = neutraal, 0.0 = kanaal uit, >1 = extra gewicht.")
kb = cfg.get("keybeliefs") or []
kb_rows = kb or [{"kanaal": "", "fase": "", "multiplier": 1.0, "reden": ""}]
kb_edited = st.data_editor(
    pd.DataFrame(kb_rows), num_rows="dynamic", use_container_width=True,
    key="kb_editor",
    column_config={
        "kanaal": st.column_config.SelectboxColumn("Kanaal", options=kanaal_opts),
        "fase": st.column_config.SelectboxColumn("Fase",
            options=list(fases.keys()) or ["awareness", "consideratie", "conversie", "loyalty"]),
        "multiplier": st.column_config.NumberColumn("Multiplier", min_value=0.0, max_value=5.0, step=0.05),
        "reden": st.column_config.TextColumn("Reden"),
    },
)
kb_new = []
for _, r in kb_edited.iterrows():
    if pd.isna(r.get("kanaal")) or not r.get("kanaal"): continue
    kb_new.append({
        "kanaal": str(r["kanaal"]),
        "fase": str(r.get("fase") or ""),
        "multiplier": float(r.get("multiplier") or 1.0),
        "reden": str(r.get("reden") or ""),
    })
cfg["keybeliefs"] = kb_new


# ---------- 9. BTW ------------------------------------------------------------

st.header("9. Financieel (BTW)")
fin = cfg.get("financieel") or {}
c1, c2 = st.columns(2)
with c1:
    btw_pct = st.number_input(
        "BTW %", 0.0, 30.0, value=float(fin.get("btw_pct", 21.0)), step=1.0,
        help="21 voor standaard, 0 voor vrijgesteld (bv. banken).",
    )
with c2:
    valuta = st.text_input("Valuta", value=fin.get("valuta", "EUR"))
cfg["financieel"] = {
    "btw_pct": btw_pct, "valuta": valuta,
    "agency_fee_pct": float(fin.get("agency_fee_pct", 0.0)),
}


# ---------- 10. YAML preview + download --------------------------------------

st.header("10. YAML preview + download")

# Verwijder lege secties voor schone output
def _clean(d):
    if isinstance(d, dict):
        return {k: _clean(v) for k, v in d.items()
                if v not in (None, {}, [], "") and _clean(v) not in (None, {}, [], "")}
    if isinstance(d, list):
        return [_clean(i) for i in d if i not in (None, {}, [], "")]
    return d
cfg_clean = _clean(cfg)

yaml_str = yaml.dump(cfg_clean, allow_unicode=True, sort_keys=False, default_flow_style=False)
st.code(yaml_str, language="yaml")

# Validatie
issues = []
if not cfg["klant"].get("code"):
    issues.append("klant.code ontbreekt")
if not cfg["klant"].get("naam"):
    issues.append("klant.naam ontbreekt")
if not cfg.get("kanalen"):
    issues.append("Minstens 1 kanaal toevoegen")
if issues:
    st.error("Nog niet af: " + " | ".join(issues))
else:
    st.success(f"Config is compleet ({len(cfg.get('kanalen', {}))} kanalen, "
               f"{len(cfg.get('kpi_targets', {}))} fases, "
               f"{len(cfg.get('campagnes', []))} campagnes)")

klant_code_save = cfg["klant"].get("code") or "klant"
fname = f"config_{klant_code_save.lower()}.yaml"
st.download_button(
    label=f"Download {fname}",
    data=yaml_str.encode("utf-8"),
    file_name=fname,
    mime="application/x-yaml",
    disabled=bool(issues),
)
st.caption(f"Commit het bestand daarna naar **`config/klanten/{fname}`** in de repo "
           "en push naar GitHub — Streamlit Cloud deploy't automatisch opnieuw.")
