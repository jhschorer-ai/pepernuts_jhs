"""Klant-config loader voor de planningsmachine.

Identieke logica als evaluatiemachine/config/loader.py: leest
klant-configs uit shared-data/klantconfig/ met fallback naar
repo-interne config/klanten/ (voor Streamlit Cloud).
"""
from __future__ import annotations
from pathlib import Path
import yaml


def _repo_root() -> Path:
    # config/loader.py -> config/ -> planningsmachine/
    return Path(__file__).resolve().parent.parent


def _candidate_paths(klant_code: str) -> list[Path]:
    repo = _repo_root()
    return [
        # Lokaal: shared-data naast planningsmachine-folder
        repo.parent / "shared-data" / "klantconfig" / f"config_{klant_code}.yaml",
        # Repo-kopie voor Cloud
        repo / "config" / "klanten" / f"config_{klant_code}.yaml",
        # Legacy zonder prefix
        repo / "config" / "klanten" / f"{klant_code}.yaml",
    ]


def load_klant_config(klant_code: str, base_dir: Path | None = None) -> dict:
    if base_dir is not None:
        path = Path(base_dir) / f"{klant_code}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Geen klant-config gevonden voor '{klant_code}': {path}")
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    for p in _candidate_paths(klant_code):
        if p.exists():
            with open(p, "r", encoding="utf-8") as fh:
                return yaml.safe_load(fh)

    tried = "\n  - ".join(str(p) for p in _candidate_paths(klant_code))
    raise FileNotFoundError(
        f"Geen klant-config gevonden voor '{klant_code}'. Geprobeerd:\n  - {tried}"
    )


def list_klanten(base_dir: Path | None = None) -> list[str]:
    if base_dir is not None:
        return sorted(p.stem for p in Path(base_dir).glob("*.yaml"))

    repo = _repo_root()
    folders = [
        repo.parent / "shared-data" / "klantconfig",
        repo / "config" / "klanten",
    ]
    codes: set[str] = set()
    for folder in folders:
        try:
            if not folder.exists():
                continue
            for p in folder.glob("*.yaml"):
                stem = p.stem
                if stem.startswith("config_"):
                    codes.add(stem[len("config_"):])
                else:
                    codes.add(stem)
        except Exception:
            continue
    return sorted(codes)
