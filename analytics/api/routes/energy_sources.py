"""
Energy Sources & Features API Routes

Provides endpoints for querying available energy sources and their features.
Critical for OVOS dynamic feature discovery.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Any
from uuid import UUID
import logging

from database import db
from services.feature_discovery import FeatureDiscoveryService

logger = logging.getLogger(__name__)
router = APIRouter()
feature_discovery = FeatureDiscoveryService()


@router.get("/energy-sources", tags=["Energy Sources"])
async def list_energy_sources(
    is_active: Optional[bool] = Query(None, description="Filter by active status")
):
    """
    List all available energy sources.
    
    Returns energy sources with metadata (unit, cost, carbon factor).
    Used by OVOS to discover available energy source types.
    
    **Example:**
    ```
    GET /api/v1/energy-sources
    GET /api/v1/energy-sources?is_active=true
    ```
    """
    try:
        async with db.pool.acquire() as conn:
            query = """
                SELECT 
                    id, name, unit, cost_per_unit, 
                    carbon_factor, description, is_active,
                    created_at
                FROM energy_sources
            """
            params = []
            
            if is_active is not None:
                query += " WHERE is_active = $1"
                params.append(is_active)
            
            query += " ORDER BY name"
            
            rows = await conn.fetch(query, *params)
            
            return [
                {
                    "id": str(row["id"]),
                    "name": row["name"],
                    "unit": row["unit"],
                    "cost_per_unit": float(row["cost_per_unit"]),
                    "carbon_factor": float(row["carbon_factor"]),
                    "description": row["description"],
                    "is_active": row["is_active"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Error listing energy sources: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list energy sources: {str(e)}")


@router.get("/energy-sources/{energy_source_name}", tags=["Energy Sources"])
async def get_energy_source(energy_source_name: str):
    """
    Get a single energy source by name.
    
    **Example:**
    ```
    GET /api/v1/energy-sources/electricity
    GET /api/v1/energy-sources/natural_gas
    ```
    """
    try:
        async with db.pool.acquire() as conn:
            query = """
                SELECT 
                    id, name, unit, cost_per_unit, 
                    carbon_factor, description, is_active,
                    created_at
                FROM energy_sources
                WHERE LOWER(name) = LOWER($1)
            """
            
            row = await conn.fetchrow(query, energy_source_name)
            
            if not row:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Energy source '{energy_source_name}' not found"
                )
            
            return {
                "id": str(row["id"]),
                "name": row["name"],
                "unit": row["unit"],
                "cost_per_unit": float(row["cost_per_unit"]),
                "carbon_factor": float(row["carbon_factor"]),
                "description": row["description"],
                "is_active": row["is_active"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting energy source {energy_source_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get energy source: {str(e)}")


@router.get("/features/{energy_source_name}", tags=["Features"])
async def list_features_for_energy_source(
    energy_source_name: str,
    regression_only: bool = Query(False, description="Return only features suitable for regression")
):
    """
    List all available features for a specific energy source.
    
    Returns feature metadata including source table, column, and aggregation function.
    Critical for OVOS to discover what features can be used for training baselines.
    
    **Example:**
    ```
    GET /api/v1/features/electricity
    GET /api/v1/features/natural_gas
    GET /api/v1/features/electricity?regression_only=true
    ```
    
    **Response:**
    ```json
    {
        "energy_source": "electricity",
        "energy_source_id": "uuid...",
        "total_features": 20,
        "features": [
            {
                "feature_name": "production_count",
                "source_table": "production_data",
                "source_column": "production_count",
                "aggregation_function": "AVG",
                "description": "Average production count per day"
            },
            ...
        ]
    }
    ```
    """
    try:
        # Get energy source ID
        async with db.pool.acquire() as conn:
            es_query = "SELECT id, name, unit FROM energy_sources WHERE LOWER(name) = LOWER($1)"
            es_row = await conn.fetchrow(es_query, energy_source_name)
            
            if not es_row:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Energy source '{energy_source_name}' not found. Available: electricity, natural_gas, steam, compressed_air"
                )
            
            energy_source_id = es_row["id"]
            
            # Get features using FeatureDiscoveryService
            features = await feature_discovery.get_available_features(
                energy_source_id, 
                regression_only=regression_only
            )
            
            # Map feature_name to actual column name in aggregated data
            # (e.g., "pressure_bar" -> "avg_pressure_bar")
            def get_column_name(feature: Any) -> str:
                """Map feature_name to actual aggregated column name."""
                agg = feature.aggregation_function.upper()
                
                # Special cases matching get_machine_data_combined() query
                if feature.feature_name == "production_count":
                    return "total_production_count"
                elif feature.feature_name == "avg_throughput":
                    return "avg_throughput_units_per_hour"
                elif feature.feature_name == "total_production":
                    return "total_production_count"
                elif feature.feature_name == "consumption_kwh":
                    return "total_energy_kwh"
                elif feature.feature_name == "operating_hours":
                    return "operating_hours"  # Derived field
                elif feature.feature_name == "good_units_count":
                    return "total_production_good"
                elif feature.feature_name == "defect_units_count":
                    return "total_production_bad"
                elif feature.feature_name == "avg_cycle_time_sec":
                    # Not in aggregated data - would need to add to query
                    return None  # Skip this feature for now
                
                # Standard prefix mapping
                if agg == "AVG":
                    return f"avg_{feature.source_column}"
                elif agg in ("SUM", "TOTAL"):
                    return f"total_{feature.source_column}"
                elif agg == "MAX":
                    return f"max_{feature.source_column}"
                elif agg == "MIN":
                    return f"min_{feature.source_column}"
                elif agg == "CUSTOM":
                    # Custom aggregations use feature_name as-is
                    return feature.feature_name
                else:
                    # Default: use feature_name as-is
                    return feature.feature_name
            
            return {
                "energy_source": es_row["name"],
                "energy_source_id": str(energy_source_id),
                "unit": es_row["unit"],
                "total_features": len(features),
                "features": [
                    {
                        "feature_name": f.feature_name,
                        "column_name": get_column_name(f),  # NEW: Actual column in aggregated data
                        "source_table": f.source_table,
                        "source_column": f.source_column,
                        "aggregation_function": f.aggregation_function,
                        "description": f.description
                    }
                    for f in features
                    if get_column_name(f) is not None  # Filter out unavailable features
                ]
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing features for {energy_source_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list features: {str(e)}")


@router.get("/features", tags=["Features"])
async def list_all_features():
    """
    List all features across all energy sources.
    
    Returns grouped by energy source.
    
    **Example:**
    ```
    GET /api/v1/features
    ```
    """
    try:
        async with db.pool.acquire() as conn:
            query = """
                SELECT 
                    es.id as energy_source_id,
                    es.name as energy_source_name,
                    es.unit,
                    f.feature_name,
                    f.source_table,
                    f.source_column,
                    f.aggregation_function,
                    f.description
                FROM energy_source_features f
                JOIN energy_sources es ON f.energy_source_id = es.id
                WHERE es.is_active = true
                ORDER BY es.name, f.feature_name
            """
            
            rows = await conn.fetch(query)
            
            # Group by energy source
            grouped = {}
            for row in rows:
                es_name = row["energy_source_name"]
                if es_name not in grouped:
                    grouped[es_name] = {
                        "energy_source": es_name,
                        "energy_source_id": str(row["energy_source_id"]),
                        "unit": row["unit"],
                        "features": []
                    }
                
                grouped[es_name]["features"].append({
                    "feature_name": row["feature_name"],
                    "source_table": row["source_table"],
                    "source_column": row["source_column"],
                    "aggregation_function": row["aggregation_function"],
                    "description": row["description"]
                })
            
            # Add feature counts
            for es_data in grouped.values():
                es_data["total_features"] = len(es_data["features"])
            
            return {
                "total_energy_sources": len(grouped),
                "energy_sources": list(grouped.values())
            }
    except Exception as e:
        logger.error(f"Error listing all features: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list features: {str(e)}")
