# Planningsmachine

Campagne-planning met afgedwongen naming-conventies. Produceert een
plan-Excel dat de evaluatiemachine direct kan verwerken.

## Scope V0.1

1. **Tactiek-naming generator** - genereert tactiek_id's uit klant,
   campagne, startdatum en volgnummer.
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
├── generators/
│   ├── tactiek_id.py             # {KLANT}-{YYYY}-{MM}-{Camp}-T{NN}
│   ├── plan_excel.py             # plan-formaat (evaluatiemachine-ready)
│   ├── budget_split.py           # benchmark + keybelief verdeling
│   └── flight_planner.py         # sequentiele fase-flights
├── validators/
│   └── naming.py                 # tactiek_id + plan-rij validatie
└── tests/
    └── pilot_*.py                # end-to-end smoke-tests
```

## Tactiek-ID conventie

```
{KLANTCODE}-{YYYY}-{MM}-{Campagne}-T{NN}
```

Voor deel-campagnes (meerdelige campagnes):

```
{KLANTCODE}-{YYYY}-{MM}-{Campagne}-D{D}T{NN}
```

Voorbeelden:

- `KLANT-2026-04-Voorjaar-T01`
- `KLANT-2026-03-Termijndeposito-D1T01` (hoofdcampagne)
- `KLANT-2026-03-Termijndeposito-D3T02` (verlenging)

### Belangrijk

Het tactiek_id bevat geen fase of kanaal - het volgnummer moet dus
**globaal oplopend** zijn over alle fases heen binnen een campagne,
anders krijg je dubbele IDs. `validators/naming.validate_plan` vangt
dit af met een "Dubbele tactiek_id"-issue.

## Plan-Excel tabbladen

| Tabblad | Inhoud |
| --- | --- |
| Plan | 1 rij per tactiek (hoofdinput evaluatiemachine) |
| Flights | 1 rij per fase met start/eind, KPI, warmup/cooldown-vlaggen |
| Budget | Fase x kanaal split-result (pct + EUR) |
| Benchmarks | Gebruikte benchmark-percentages (auditspoor) |
| Keybeliefs | Toegepaste multipliers (auditspoor) |
| Meta | Klant, campagne, auteur, gegenereerd op, versie |

## Lokaal draaien

```powershell
cd planningsmachine
pip install -r requirements.txt
streamlit run app.py
```
