"""
Data loader for FSG producer.
Loads pipeline, products catalog, persona, eeat vault, navigation.
"""

import json
import yaml
from pathlib import Path
from datetime import date
from typing import Optional

ROOT = Path(__file__).parent.parent


def load_pipeline() -> list[dict]:
    with open(ROOT / "data/pipeline.json") as f:
        return json.load(f)


def load_products() -> dict:
    """Returns dict keyed by product slug."""
    with open(ROOT / "content/products/products.yaml") as f:
        raw = yaml.safe_load(f)
    # Normalise: convert date objects to strings
    products = {}
    for key, p in raw.items():
        p["key"] = key
        if isinstance(p.get("last_verified"), date):
            p["last_verified"] = p["last_verified"].isoformat()
        products[key] = p
    return products


def load_persona() -> dict:
    with open(ROOT / "site.config.yaml") as f:
        cfg = yaml.safe_load(f)
    persona_path = ROOT / cfg["persona"]["config_path"]
    with open(persona_path) as f:
        return yaml.safe_load(f)


def load_eeat_vault() -> dict:
    with open(ROOT / "data/eeat-vault.json") as f:
        return json.load(f)


def load_navigation() -> dict:
    with open(ROOT / "config/navigation.yaml") as f:
        return yaml.safe_load(f)


def load_site_config() -> dict:
    with open(ROOT / "site.config.yaml") as f:
        return yaml.safe_load(f)


def get_pending_articles(pipeline: list[dict]) -> list[dict]:
    return [a for a in pipeline if a.get("status") == "pending"]


def get_article_by_id(pipeline: list, article_id: int) -> Optional[dict]:
    return next((a for a in pipeline if a["id"] == article_id), None)


def get_article_by_slug(pipeline: list, slug: str) -> Optional[dict]:
    return next((a for a in pipeline if a["slug"] == slug), None)


def get_eeat_for_cluster(vault: dict, cluster: str) -> dict:
    """Pull relevant EEAT entries for a given cluster."""
    experiences = [
        e for e in vault.get("product_experiences", [])
        if cluster in e.get("clusters", [])
    ]
    failures = [
        f for f in vault.get("failures", [])
        if cluster in f.get("clusters", [])
    ]
    opinions = [
        o for o in vault.get("strong_opinions", [])
        if cluster in o.get("clusters", [])
    ]
    return {
        "experiences": experiences[:3],
        "failures": failures[:2],
        "opinions": opinions[:2],
    }


def save_pipeline(pipeline: list[dict]) -> None:
    path = ROOT / "data/pipeline.json"
    tmp = path.with_suffix(".json.tmp")
    bak = path.with_suffix(".json.bak")
    with open(tmp, "w") as f:
        json.dump(pipeline, f, indent=2)
    if path.exists():
        import shutil
        shutil.copy2(path, bak)
    import os
    os.replace(tmp, path)
