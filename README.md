# DBD Planningsmachine

Campagne-planning met afgedwongen naming-conventies. Produceert een
plan-Excel dat de evaluatiemachine direct kan verwerken.

## Scope V0.1

1. **Tactiek-naming generator** - genereert tactiek_id's uit klant,
   productlijn, campagne, startdatum en volgnummer.
2. **Plan-Excel generator** - schrijft evaluatie-machine-compatible xlsx
   met tabbladen Plan, Flights, Budget, Benchmarks, Keybeliefs, Meta.
3. **Budget-splitter** - verdeelt totaalbudget over fases en kanalen op
   basis van historische benchmarks + keybelief-multipliers.
4. **Flight-planner** - plant sequentiele fase-flights binnen een
   campagneperiode (awareness -> consideratie -> conversie -> loyalty).
5. **Naming-validator** - check tactiek_id + plan-rijen tegen klantconfig.
6. **Streamlit UI** - planner vult input, download plan-Excel.

## Architectuur

Identieke conventies als evaluatiemachine:

- Klant-configs uit `../shared-data/klantconfig/config_{klant}.yaml`
  (cross-app), fallback naar repo-interne `config/klanten/` voor Cloud.
- Python + Streamlit + pandas + openpyxl.

```
planningsmachine/
├── app.py                        # Streamlit UI
├── config/
│   ├── loader.py                 # klant-config loader (shared-data + fallback)
│   └── klanten/                  # repo-kopie van klant-configs (Cloud-fallback)
│       └── config_nibc.yaml
├── generators/
│   ├── tactiek_id.py             # {KLANT}-{PL}-{YYYY}-{MM}-{Camp}-T{NN}
│   ├── plan_excel.py             # NIBC-plan-formaat (evaluatiemachine-ready)
│   ├── budget_split.py           # benchmark + keybelief verdeling
│   └── flight_planner.py         # sequentiele fase-flights
├── validators/
│   └── naming.py                 # tactiek_id + plan-rij validatie
└── tests/
    └── pilot_nibc_paasbonus_2026.py  # end-to-end pilot (draait groen)
```

## Tactiek-ID conventie

```
{KLANTCODE}-{PRODUCTLIJN}-{YYYY}-{MM}-{Campagne}-T{NN}
```

Voor deel-campagnes (meerdelige NIBC-campagnes):

```
{KLANTCODE}-{PRODUCTLIJN}-{YYYY}-{MM}-{Campagne}-D{D}T{NN}
```

Voorbeelden:

- `NIBC-BON-2026-04-Paasbonus-T01`
- `NIBC-SPR-2026-03-Termijndeposito-D1T01` (hoofdcampagne)
- `NIBC-SPR-2026-03-Termijndeposito-D3T02` (verlenging)

### Belangrijk

Het tactiek_id bevat geen fase of kanaal - het volgnummer moet dus
**globaal oplopend** zijn over alle fases heen binnen een campagne,
anders krijg je dubbele IDs. `validators/naming.validate_plan` vangt
dit af met een "Dubbele tactiek_id"-issue.

## Plan-Excel tabbladen

| Tabblad | Inhoud |
| --- | --- |
| Plan | 1 rij per tactiek, 33 kolommen (hoofdinput evaluatiemachine) |
| Flights | 1 rij per fase met start/eind, KPI, warmup/cooldown-vlaggen |
| Budget | Fase x kanaal split-result (pct + EUR) |
| Benchmarks | Gebruikte benchmark-percentages (auditspoor) |
| Keybeliefs | Toegepaste multipliers (auditspoor) |
| Meta | Klant, campagne, auteur, gegenereerd op, versie |

## Lokaal draaien

```powershell
cd planningsmachine
pip install -r requirements.txt
python tests/pilot_nibc_paasbonus_2026.py   # end-to-end smoke-test
streamlit run app.py
```

## Pilot status

**Pilot**: NIBC Paasbonus 2026, totaalbudget EUR 120.000, 15 maart - 20 april 2026.
End-to-end test draait groen: 19 tactieken over 4 fases, validatie OK,
evaluatie-machine-compatible Excel gegenereerd.
