"""
EnMS Analytics API - SEU Management Routes
==========================================
Significant Energy Use (SEU) endpoints for ISO 50001 compliance.

Extracted from ovos_training.py as part of Phase 1 API cleanup.
Provides centralized SEU discovery and management.

Author: EnMS Team
Phase: 1 - API Cleanup & Refactoring
Date: November 5, 2025
"""

from fastapi import APIRouter, HTTPException, status
from typing import Optional
from datetime import datetime
import logging

from database import db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/seus", tags=["SEU Management"])
async def list_seus(energy_source: Optional[str] = None):
    """
    List all Significant Energy Uses (SEUs) with optional filtering.
    
    SEUs are ISO 50001 compliant energy monitoring boundaries.
    Each SEU represents one machine + energy source combination.
    
    **Use Cases:**
    - Discover available SEUs for baseline training
    - Filter SEUs by energy type (electricity, natural gas, steam)
    - Get SEU information for voice commands
    
    **Parameters:**
    - `energy_source` (optional): Filter by energy source name
      - Options: "electricity", "natural_gas", "steam", "compressed_air"
    
    **Response:**
    - List of SEUs with metadata (name, energy source, machine count, baseline status)
    
    **Example:**
    ```bash
    # Get all SEUs
    curl "http://localhost:8001/api/v1/seus"
    
    # Get electricity SEUs only
    curl "http://localhost:8001/api/v1/seus?energy_source=electricity"
    ```
    """
    try:
        query = """
            SELECT 
                s.id,
                s.name,
                es.name as energy_source,
                es.unit,
                array_length(s.machine_ids, 1) as machine_count,
                s.baseline_year,
                s.r_squared
            FROM seus s
            JOIN energy_sources es ON s.energy_source_id = es.id
            WHERE s.is_active = true
        """
        
        params = []
        if energy_source:
            query += " AND LOWER(es.name) = LOWER($1)"
            params.append(energy_source)
        
        query += " ORDER BY s.name"
        
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            
            seus = [
                {
                    "id": str(row['id']),
                    "name": row['name'],
                    "energy_source": row['energy_source'],
                    "unit": row['unit'],
                    "machine_count": row['machine_count'],
                    "baseline_year": row['baseline_year'],
                    "r_squared": float(row['r_squared']) if row['r_squared'] else None,
                    "has_baseline": row['r_squared'] is not None
                }
                for row in rows
            ]
            
            return {
                "success": True,
                "seus": seus,
                "total_count": len(seus),
                "filtered_by": energy_source,
                "timestamp": datetime.now().isoformat()
            }
    
    except Exception as e:
        logger.error(f"Failed to list SEUs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve SEUs: {str(e)}"
        )


@router.get("/seus/{seu_id}", tags=["SEU Management"])
async def get_seu_details(seu_id: str):
    """
    Get detailed information about a specific SEU.
    
    **Parameters:**
    - `seu_id`: UUID of the SEU
    
    **Response:**
    - Full SEU details including associated machines, baseline info, and energy metrics
    
    **Example:**
    ```bash
    curl "http://localhost:8001/api/v1/seus/{seu_id}"
    ```
    """
    try:
        query = """
            SELECT 
                s.id,
                s.name,
                s.description,
                es.name as energy_source,
                es.unit,
                s.machine_ids,
                s.baseline_year,
                s.r_squared,
                s.target_reduction_percent,
                s.is_active,
                s.created_at,
                s.updated_at,
                COUNT(eb.id) as baseline_model_count
            FROM seus s
            JOIN energy_sources es ON s.energy_source_id = es.id
            LEFT JOIN energy_baselines eb ON eb.machine_id = ANY(s.machine_ids) 
                AND eb.energy_source_id = es.id
                AND eb.is_active = true
            WHERE s.id = $1
            GROUP BY s.id, s.name, s.description, es.name, es.unit, s.machine_ids,
                     s.baseline_year, s.r_squared, s.target_reduction_percent,
                     s.is_active, s.created_at, s.updated_at
        """
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, seu_id)
            
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"SEU with ID {seu_id} not found"
                )
            
            # Get machine details
            machine_query = """
                SELECT id, name, type, rated_power_kw
                FROM machines
                WHERE id = ANY($1)
            """
            machines = await conn.fetch(machine_query, row['machine_ids'])
            
            seu_details = {
                "id": str(row['id']),
                "name": row['name'],
                "description": row['description'],
                "energy_source": row['energy_source'],
                "unit": row['unit'],
                "machines": [
                    {
                        "id": str(m['id']),
                        "name": m['name'],
                        "type": m['type'],
                        "rated_power_kw": float(m['rated_power_kw']) if m['rated_power_kw'] else None
                    }
                    for m in machines
                ],
                "baseline_year": row['baseline_year'],
                "r_squared": float(row['r_squared']) if row['r_squared'] else None,
                "target_reduction_percent": float(row['target_reduction_percent']) if row['target_reduction_percent'] else None,
                "baseline_model_count": row['baseline_model_count'],
                "has_baseline": row['baseline_model_count'] > 0,
                "is_active": row['is_active'],
                "created_at": row['created_at'].isoformat() if row['created_at'] else None,
                "updated_at": row['updated_at'].isoformat() if row['updated_at'] else None
            }
            
            return {
                "success": True,
                "seu": seu_details,
                "timestamp": datetime.now().isoformat()
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get SEU details for {seu_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve SEU details: {str(e)}"
        )
