import json
from pathlib import Path
from tram.application.errors import ApplicationError

def list_models(models_root: Path):
    active_version = None
    active_path = models_root / "active_version.txt"
    if active_path.exists():
        active_version = active_path.read_text().strip()

    items = []
    if models_root.exists():
        for d in models_root.iterdir():
            if not d.is_dir():
                continue
            manifest_path = d / "manifest.json"
            if not manifest_path.exists():
                continue
            
            config_path = d / "config.json"
            config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
            
            metrics_path = d / "metrics.json"
            metrics = {}
            if metrics_path.exists():
                metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            
            items.append({
                "id": d.name,
                "version": d.name,
                "method": config.get("model_type", "unknown"),
                "is_active": d.name == active_version,
                "is_baseline": config.get("model_type") == "baseline",
                "metrics": metrics
            })
    return {"items": items, "page": {"has_more": False, "next_cursor": None}}

def get_model(models_root: Path, model_id: str):
    active_version = None
    active_path = models_root / "active_version.txt"
    if active_path.exists():
        active_version = active_path.read_text().strip()

    model_dir = models_root / model_id
    manifest_path = model_dir / "manifest.json"
    if not manifest_path.exists():
        raise ApplicationError("NOT_FOUND", "Model not found")
    
    config_path = model_dir / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}

    metrics_path = model_dir / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
    card_path = model_dir / "model-card.md"
    card = card_path.read_text(encoding="utf-8") if card_path.exists() else ""

    return {
        "id": model_id,
        "version": model_id,
        "method": config.get("model_type", "unknown"),
        "is_active": model_id == active_version,
        "is_baseline": config.get("model_type") == "baseline",
        "metrics": metrics,
        "config": config,
        "card": card
    }
