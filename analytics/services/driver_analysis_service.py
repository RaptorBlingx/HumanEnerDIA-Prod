"""Driver analysis service for SEU baseline explainability.

Provides a dedicated contract for driver-focused questions from OVOS and
other clients. This keeps route handlers thin and centralizes the logic for:
- learned drivers from trained baseline models
- candidate drivers when a baseline is missing
- factory-wide aggregation across SEUs
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from uuid import UUID

from database import db, get_active_baseline_model
from services.baseline_service import baseline_service
from services.feature_discovery import feature_discovery
from services.model_explainer import model_explainer

logger = logging.getLogger(__name__)


class DriverAnalysisService:
    """Service for driver-centric baseline analysis."""

    _CANDIDATE_DRIVER_EXCLUSIONS = {
        "consumption_kwh",
        "consumption_m3",
        "consumption_kg",
        "avg_power_kw",
        "max_power_kw",
        "avg_current_a",
        "avg_voltage_v",
        "avg_power_factor",
    }

    _FEATURE_PRIORITY = {
        "production_count": 100,
        "total_production": 95,
        "avg_throughput": 92,
        "outdoor_temp_c": 90,
        "heating_degree_days": 88,
        "cooling_degree_days": 88,
        "pressure_bar": 86,
        "avg_pressure_bar": 86,
        "operating_hours": 84,
        "avg_load_factor": 82,
        "indoor_temp_c": 78,
        "machine_temp_c": 76,
        "outdoor_humidity_percent": 72,
        "avg_dewpoint_c": 70,
        "good_units_count": 68,
        "defect_units_count": 64,
        "avg_cycle_time_sec": 60,
    }

    _DRIVER_ALIASES = {
        "temperature": [
            "temperature",
            "ambient temperature",
            "outdoor temperature",
            "indoor temperature",
            "machine temperature",
            "weather",
        ],
        "outdoor temperature": [
            "outdoor temperature",
            "ambient temperature",
            "weather",
            "temperature",
        ],
        "indoor temperature": [
            "indoor temperature",
            "room temperature",
            "temperature",
        ],
        "machine temperature": [
            "machine temperature",
            "equipment temperature",
            "temperature",
        ],
        "production": [
            "production",
            "production count",
            "production volume",
            "output",
            "throughput",
            "units",
            "load",
        ],
        "pressure": [
            "pressure",
            "operating pressure",
            "steam pressure",
            "air pressure",
        ],
        "load factor": [
            "load factor",
            "load",
            "utilization",
        ],
        "operating hours": [
            "operating hours",
            "runtime",
            "run time",
            "hours",
        ],
        "humidity": [
            "humidity",
            "outdoor humidity",
        ],
        "heating degree days": [
            "heating degree days",
            "hdd",
        ],
        "cooling degree days": [
            "cooling degree days",
            "cdd",
        ],
        "dewpoint": [
            "dewpoint",
            "dew point",
            "air dewpoint",
        ],
    }

    @staticmethod
    def _normalize_text(value: Optional[str]) -> str:
        if not value:
            return ""
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    def _driver_search_terms(self, requested_driver: Optional[str]) -> List[str]:
        normalized = self._normalize_text(requested_driver)
        if not normalized:
            return []

        search_terms = {normalized}
        for canonical_name, aliases in self._DRIVER_ALIASES.items():
            normalized_aliases = {self._normalize_text(alias) for alias in aliases}
            normalized_canonical = self._normalize_text(canonical_name)
            if normalized == normalized_canonical or normalized in normalized_aliases:
                search_terms.add(normalized_canonical)
                search_terms.update(normalized_aliases)

        return sorted(term for term in search_terms if term)

    def _matches_requested_driver(self, requested_driver: Optional[str], *candidate_values: Optional[str]) -> bool:
        search_terms = self._driver_search_terms(requested_driver)
        if not search_terms:
            return False

        candidate_terms = {
            self._normalize_text(candidate)
            for candidate in candidate_values
            if self._normalize_text(candidate)
        }

        for search_term in search_terms:
            for candidate_term in candidate_terms:
                if (
                    search_term == candidate_term
                    or search_term in candidate_term
                    or candidate_term in search_term
                ):
                    return True

        return False

    async def _get_seu_by_name_and_energy_source(
        self,
        seu_name: str,
        energy_source: str,
    ) -> Optional[Dict[str, Any]]:
        query = """
            SELECT
                s.id,
                s.name,
                s.description,
                s.energy_source_id,
                s.machine_ids,
                es.name AS energy_source_name,
                es.unit AS energy_unit
            FROM seus s
            JOIN energy_sources es ON s.energy_source_id = es.id
            WHERE LOWER(s.name) = LOWER($1)
              AND LOWER(es.name) = LOWER($2)
              AND s.is_active = true
            LIMIT 1
        """

        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, seu_name, energy_source)
            return dict(row) if row else None

    async def _get_active_model_for_seu(self, seu: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for machine_id in seu.get("machine_ids", []):
            model = await get_active_baseline_model(machine_id, seu.get("energy_source_id"))
            if model:
                return model
        return None

    def _feature_priority(self, feature_name: str) -> int:
        return self._FEATURE_PRIORITY.get(feature_name, 10)

    def _is_candidate_driver(self, feature_name: str) -> bool:
        normalized = self._normalize_text(feature_name)
        if not normalized:
            return False

        if feature_name in self._CANDIDATE_DRIVER_EXCLUSIONS:
            return False

        if normalized.startswith("consumption"):
            return False

        if normalized.startswith("avg power") or normalized.startswith("max power"):
            return False

        return True

    async def _build_candidate_drivers(
        self,
        energy_source_id: UUID,
        top_n: int,
    ) -> List[Dict[str, Any]]:
        features = await feature_discovery.get_available_features(
            energy_source_id,
            regression_only=True,
        )

        candidates: List[Dict[str, Any]] = []
        for feature in features:
            if not self._is_candidate_driver(feature.feature_name):
                continue

            candidates.append({
                "feature": feature.feature_name,
                "human_name": model_explainer._humanize_feature_name(feature.feature_name),
                "description": feature.description,
                "rank": 0,
                "absolute_impact": None,
                "direction": None,
                "driver_type": "candidate",
            })

        candidates.sort(
            key=lambda item: (-self._feature_priority(item["feature"]), item["human_name"])
        )

        limited = candidates[: max(top_n, 5)]
        for index, candidate in enumerate(limited, start=1):
            candidate["rank"] = index

        return limited

    def _match_driver(
        self,
        requested_driver: Optional[str],
        drivers: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not requested_driver:
            return None

        for driver in drivers:
            if self._matches_requested_driver(
                requested_driver,
                driver.get("feature"),
                driver.get("human_name"),
                driver.get("description"),
            ):
                return driver

        return None

    async def get_seu_driver_analysis(
        self,
        seu_name: str,
        energy_source: str,
        requested_driver: Optional[str] = None,
        top_n: int = 3,
    ) -> Dict[str, Any]:
        seu = await self._get_seu_by_name_and_energy_source(seu_name, energy_source)
        if not seu:
            raise ValueError(
                f"Could not find SEU '{seu_name}' with energy source '{energy_source}'"
            )

        active_model = await self._get_active_model_for_seu(seu)
        if not active_model:
            candidate_drivers = await self._build_candidate_drivers(
                seu["energy_source_id"],
                top_n=top_n,
            )
            matched_candidate = self._match_driver(requested_driver, candidate_drivers)

            return {
                "response_mode": "training_required",
                "scope": "seu",
                "seu_name": seu["name"],
                "energy_source": seu["energy_source_name"],
                "energy_unit": seu.get("energy_unit"),
                "has_baseline": False,
                "needs_training": True,
                "requested_driver_name": requested_driver,
                "matched_candidate_driver": matched_candidate,
                "candidate_drivers": candidate_drivers,
                "training_prompt": (
                    f"Train a baseline for {seu['name']} using {seu['energy_source_name']} data "
                    "to confirm the learned drivers."
                ),
            }

        model_details = await baseline_service.get_model_details(active_model["id"])
        if not model_details:
            raise ValueError(f"Baseline model details unavailable for model {active_model['id']}")

        explanation = model_explainer.explain_model(model_details)
        top_drivers = explanation.get("key_drivers", [])[:top_n]
        matched_driver = self._match_driver(requested_driver, explanation.get("key_drivers", []))

        return {
            "response_mode": "trained_baseline",
            "scope": "seu",
            "seu_name": seu["name"],
            "machine_name": model_details.get("machine_name") or seu["name"],
            "energy_source": seu["energy_source_name"],
            "energy_unit": seu.get("energy_unit"),
            "has_baseline": True,
            "needs_training": False,
            "model_id": str(model_details["id"]),
            "model_version": model_details.get("model_version"),
            "r_squared": model_details.get("r_squared"),
            "accuracy_explanation": explanation.get("accuracy_explanation"),
            "voice_summary": explanation.get("voice_summary"),
            "formula_explanation": explanation.get("formula_explanation"),
            "impact_summary": explanation.get("impact_summary"),
            "requested_driver_name": requested_driver,
            "matched_driver": matched_driver,
            "requested_driver_supported": matched_driver is not None if requested_driver else None,
            "top_drivers": top_drivers,
            "driver_count": len(explanation.get("key_drivers", [])),
        }

    async def get_factory_driver_analysis(
        self,
        energy_source: Optional[str] = None,
        requested_driver: Optional[str] = None,
        top_n: int = 5,
    ) -> Dict[str, Any]:
        query = """
            SELECT
                s.id AS seu_id,
                s.name AS seu_name,
                es.name AS energy_source_name,
                es.unit AS energy_unit,
                eb.id AS model_id,
                eb.machine_id,
                eb.model_version,
                eb.r_squared,
                eb.coefficients,
                eb.intercept,
                eb.feature_names,
                m.name AS machine_name
            FROM seus s
            JOIN energy_sources es ON s.energy_source_id = es.id
            JOIN LATERAL (
                SELECT
                    id,
                    machine_id,
                    model_version,
                    r_squared,
                    coefficients,
                    intercept,
                    feature_names
                FROM energy_baselines
                WHERE machine_id = ANY(s.machine_ids)
                  AND energy_source_id = s.energy_source_id
                  AND is_active = TRUE
                ORDER BY model_version DESC
                LIMIT 1
            ) eb ON TRUE
            LEFT JOIN machines m ON eb.machine_id = m.id
            WHERE s.is_active = TRUE
        """

        params: List[Any] = []
        if energy_source:
            query += " AND LOWER(es.name) = LOWER($1)"
            params.append(energy_source)

        query += " ORDER BY s.name"

        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        if not rows:
            return {
                "response_mode": "training_required",
                "scope": "factory",
                "energy_source": energy_source,
                "seus_analyzed": 0,
                "top_drivers": [],
                "requested_driver_name": requested_driver,
                "matched_driver": None,
                "training_prompt": "No active baselines are available yet. Train SEU baselines to analyze learned drivers.",
            }

        aggregated: Dict[str, Dict[str, Any]] = {}

        for row in rows:
            row_dict = dict(row)
            explanation = model_explainer.explain_model(row_dict)
            for driver in explanation.get("key_drivers", []):
                key = driver.get("feature") or driver.get("human_name")
                summary = aggregated.setdefault(
                    key,
                    {
                        "feature": driver.get("feature"),
                        "human_name": driver.get("human_name"),
                        "total_impact": 0.0,
                        "seu_names": [],
                        "machines": [],
                        "energy_sources": [],
                        "examples": [],
                    },
                )
                summary["total_impact"] += float(driver.get("absolute_impact") or 0.0)
                summary["seu_names"].append(row_dict["seu_name"])
                summary["machines"].append(row_dict.get("machine_name") or row_dict["seu_name"])
                summary["energy_sources"].append(row_dict["energy_source_name"])
                summary["examples"].append(
                    {
                        "seu_name": row_dict["seu_name"],
                        "machine_name": row_dict.get("machine_name") or row_dict["seu_name"],
                        "energy_source": row_dict["energy_source_name"],
                        "absolute_impact": driver.get("absolute_impact"),
                        "direction": driver.get("direction"),
                        "rank": driver.get("rank"),
                    }
                )

        top_drivers: List[Dict[str, Any]] = []
        for summary in aggregated.values():
            unique_seus = sorted(set(summary["seu_names"]))
            unique_machines = sorted(set(summary["machines"]))
            unique_sources = sorted(set(summary["energy_sources"]))
            examples = sorted(
                summary["examples"],
                key=lambda item: item.get("absolute_impact") or 0.0,
                reverse=True,
            )

            top_drivers.append(
                {
                    "feature": summary["feature"],
                    "human_name": summary["human_name"],
                    "total_impact": round(summary["total_impact"], 4),
                    "seu_count": len(unique_seus),
                    "machine_count": len(unique_machines),
                    "energy_source_count": len(unique_sources),
                    "seu_names": unique_seus,
                    "machines": unique_machines,
                    "energy_sources": unique_sources,
                    "examples": examples[:3],
                }
            )

        top_drivers.sort(
            key=lambda item: (item["seu_count"], item["total_impact"]),
            reverse=True,
        )

        limited = top_drivers[:top_n]
        for index, driver in enumerate(limited, start=1):
            driver["rank"] = index

        matched_driver = self._match_driver(requested_driver, top_drivers)

        return {
            "response_mode": "factory_wide",
            "scope": "factory",
            "energy_source": energy_source,
            "seus_analyzed": len(rows),
            "requested_driver_name": requested_driver,
            "matched_driver": matched_driver,
            "top_drivers": limited,
            "driver_count": len(top_drivers),
        }


driver_analysis_service = DriverAnalysisService()