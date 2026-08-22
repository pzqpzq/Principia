from __future__ import annotations

import builtins
from typing import Any, Literal

from ..domain import ScenarioEvent, ScenarioRecord, canonical_sha256, event_id, monotonic_ulid
from ..models import utc_now
from ..persistence import V14WorkspaceRepository


class ScenarioService:
    policy_version = "impact-v1"

    def __init__(self, repository: V14WorkspaceRepository, base_digest: str) -> None:
        self.repository = repository
        self.base_digest = base_digest

    def list(self) -> builtins.list[ScenarioRecord]:
        return self.repository.list_scenarios()

    def create(self, name: str, *, parent_scenario_id: str | None = None) -> ScenarioRecord:
        if parent_scenario_id and self.repository.scenario(parent_scenario_id) is None:
            raise KeyError(f"unknown parent scenario: {parent_scenario_id}")
        scenario = ScenarioRecord(
            scenario_id=f"scn:{monotonic_ulid()}",
            name=name,
            base_content_digest=self.base_digest,
            parent_scenario_id=parent_scenario_id,
        )
        self.repository.create_scenario(scenario)
        return scenario

    def append(
        self,
        scenario_id: str,
        event_type: Literal[
            "set_maturity",
            "set_support_pressure",
            "pin_version",
            "add_virtual_principle",
            "set_scope",
            "add_relation",
            "disable_relation",
        ],
        payload: dict[str, Any],
    ) -> ScenarioEvent:
        scenario = self.repository.scenario(scenario_id)
        if scenario is None:
            raise KeyError(f"unknown scenario: {scenario_id}")
        if scenario.status != "active":
            raise ValueError("discarded scenarios are immutable")
        sequence = len(self.repository.scenario_events(scenario_id)) + 1
        event = ScenarioEvent(
            event_id=event_id("sev"),
            scenario_id=scenario_id,
            sequence=sequence,
            event_type=event_type,
            payload=payload,
        )
        self.repository.append_scenario_event(event)
        return event

    def events(self, scenario_id: str) -> builtins.list[ScenarioEvent]:
        scenario = self.repository.scenario(scenario_id)
        if scenario is None:
            raise KeyError(f"unknown scenario: {scenario_id}")
        inherited: builtins.list[ScenarioEvent] = []
        if scenario.parent_scenario_id:
            inherited = self.events(scenario.parent_scenario_id)
        return inherited + self.repository.scenario_events(scenario_id)

    def replay(self, scenario_id: str) -> dict[str, Any]:
        overlay: dict[str, Any] = {
            "maturity": {},
            "support_pressure": {},
            "version_pins": {},
            "virtual_principles": {},
            "scope": {},
            "added_relations": [],
            "disabled_relations": [],
        }
        impacts: dict[str, set[str]] = {}
        for event in self.events(scenario_id):
            payload = event.payload
            principle_id = str(payload.get("principle_id") or payload.get("source") or "")
            if event.event_type == "set_maturity":
                overlay["maturity"][principle_id] = payload["maturity"]
                impacts.setdefault(principle_id, set()).add("needs_revalidation")
            elif event.event_type == "set_support_pressure":
                overlay["support_pressure"][principle_id] = payload["value"]
                impacts.setdefault(principle_id, set()).add("pressure_changed")
            elif event.event_type == "pin_version":
                overlay["version_pins"][principle_id] = payload["version"]
                impacts.setdefault(principle_id, set()).add("version_pinned")
            elif event.event_type == "add_virtual_principle":
                virtual = dict(payload)
                virtual_id = str(virtual.get("principle_id") or f"virtual:{event.event_id}")
                virtual["principle_id"] = virtual_id
                overlay["virtual_principles"][virtual_id] = virtual
                impacts.setdefault(virtual_id, set()).add("scenario_only")
            elif event.event_type == "set_scope":
                overlay["scope"][principle_id] = payload["scope"]
                impacts.setdefault(principle_id, set()).add("needs_revalidation")
            elif event.event_type == "add_relation":
                overlay["added_relations"].append(dict(payload))
                impacts.setdefault(principle_id, set()).add("relation_changed")
            elif event.event_type == "disable_relation":
                overlay["disabled_relations"].append(dict(payload))
                impacts.setdefault(principle_id, set()).add("relation_changed")
        overlay["added_relations"].sort(key=canonical_sha256)
        overlay["disabled_relations"].sort(key=canonical_sha256)
        impact_rows = [
            {"principle_id": key, "flags": sorted(value)} for key, value in sorted(impacts.items())
        ][:500]
        return {
            "scenario_id": scenario_id,
            "policy": self.policy_version,
            "base_content_digest": self.base_digest,
            "overlay": overlay,
            "impact": impact_rows,
            "overlay_digest": canonical_sha256(overlay),
            "depth": 2,
            "truncated": len(impacts) > 500,
        }

    def diff(self, scenario_id: str) -> dict[str, Any]:
        replay = self.replay(scenario_id)
        return {
            "scenario_id": scenario_id,
            "base_content_digest": replay["base_content_digest"],
            "overlay_digest": replay["overlay_digest"],
            "changes": [event.model_dump(mode="json") for event in self.events(scenario_id)],
            "impact": replay["impact"],
        }

    def compare(self, left: str, right: str) -> dict[str, Any]:
        left_replay = self.replay(left)
        right_replay = self.replay(right)
        return {
            "left": left,
            "right": right,
            "equal": left_replay["overlay_digest"] == right_replay["overlay_digest"],
            "left_digest": left_replay["overlay_digest"],
            "right_digest": right_replay["overlay_digest"],
            "left_overlay": left_replay["overlay"],
            "right_overlay": right_replay["overlay"],
        }

    def discard(self, scenario_id: str) -> None:
        self.repository.discard_scenario(scenario_id)

    def export(self, scenario_id: str) -> dict[str, Any]:
        scenario = self.repository.scenario(scenario_id)
        if scenario is None:
            raise KeyError(f"unknown scenario: {scenario_id}")
        return {
            "schema_version": "principia-scenario-v1",
            "scenario": scenario.model_dump(mode="json"),
            "events": [event.model_dump(mode="json") for event in self.events(scenario_id)],
            "exported_at": utc_now(),
        }
