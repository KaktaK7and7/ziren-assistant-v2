from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from app.config.settings import DESKTOP_TOKEN_ENV
from app.modules.registry import create_default_registry


MANIFEST_VERSION = 1


def build_web_manifest(*, include_authenticated: bool = True) -> dict[str, Any]:
    previous_token = os.environ.get(DESKTOP_TOKEN_ENV)
    try:
        # Social actions are registered only for an authenticated Desktop Core.
        # The public product catalog should still document those real actions,
        # so manifest export supplies a non-secret placeholder token locally.
        if include_authenticated and not previous_token:
            os.environ[DESKTOP_TOKEN_ENV] = "manifest-export-only"

        registry = create_default_registry()
        features: list[dict[str, Any]] = []

        for feature in registry.get_public_capabilities():
            actions = []
            for action in feature.get("actions", []):
                action_id = str(action.get("action_id") or "").strip()
                if not action_id:
                    continue
                triggers = [
                    " ".join(str(trigger).split())
                    for trigger in action.get("triggers", [])
                    if isinstance(trigger, str) and trigger.strip()
                ]
                actions.append(
                    {
                        "id": action_id,
                        "title": str(action.get("display_name") or action_id),
                        "example": triggers[0] if triggers else "",
                        "snake": bool(action.get("snake_triggers", True)),
                        "melissa": bool(action.get("melissa_semantic", False)),
                        "argument_hint": str(action.get("argument_hint") or ""),
                    }
                )

            if not actions:
                continue

            features.append(
                {
                    "feature_id": str(feature.get("feature_id") or ""),
                    "title": str(feature.get("display_name") or feature.get("feature_id") or ""),
                    "plan": str(feature.get("plan") or "free"),
                    # Readiness is intentionally NOT inferred here. The release
                    # matrix owns READY/TESTING state; existence in registry only
                    # proves that the action contract exists.
                    "status": "testing",
                    "snake": any(action["snake"] for action in actions),
                    "melissa": any(action["melissa"] for action in actions),
                    "actions": actions,
                }
            )

        return {
            "schema_version": MANIFEST_VERSION,
            "generated_from": "ziren-assistant-v2:ModuleRegistry",
            "modes": {
                "snake": {
                    "title": "Змея",
                    "badge": "LOCAL · FREE",
                    "description": "Локальные команды по точным и пользовательским триггерам. Нейросеть не участвует.",
                },
                "melissa": {
                    "title": "Мелисса",
                    "badge": "SMART · PLUS / PRO",
                    "description": "Понимает естественную формулировку через AI, выбирает только разрешённую capability, а действие выполняет локальный Core.",
                },
            },
            "features": features,
        }
    finally:
        if previous_token is None:
            os.environ.pop(DESKTOP_TOKEN_ENV, None)
        else:
            os.environ[DESKTOP_TOKEN_ENV] = previous_token


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export the website capability manifest from the real Core ModuleRegistry.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write JSON to this file instead of stdout.",
    )
    args = parser.parse_args()

    payload = json.dumps(build_web_manifest(), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
