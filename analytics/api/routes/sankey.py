"""
Sankey Diagram API Routes
==========================
Provides energy flow data for Sankey diagrams showing:
Grid â†' Factory â†' Departments â†' Machines

Author: EnMS Team
Date: October 14, 2025
Phase 4, Session 3
"""

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timedelta
import logging

from database import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sankey")


# ============================================================================
# DATA MODELS
# ============================================================================

class SankeyNode(BaseModel):
    """Sankey diagram node"""
    id: str = Field(..., description="Unique node ID")
    name: str = Field(..., description="Display name")
    level: int = Field(..., description="Hierarchy level (0=Grid, 1=Factory, 2=Dept, 3=Machine)")


class SankeyLink(BaseModel):
    """Sankey diagram link (flow between nodes)"""
    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    value: float = Field(..., description="Energy flow in kWh")
    percentage: float = Field(..., description="Percentage of source energy")


class SankeyData(BaseModel):
    """Complete Sankey diagram data"""
    nodes: List[SankeyNode] = Field(..., description="All nodes in the diagram")
    links: List[SankeyLink] = Field(..., description="All flows between nodes")
    total_energy_kwh: float = Field(..., description="Total energy consumed")
    start_date: datetime = Field(..., description="Start of data period")
    end_date: datetime = Field(..., description="End of data period")
    factory_count: int = Field(..., description="Number of factories")
    department_count: int = Field(..., description="Number of departments")
    machine_count: int = Field(..., description="Number of machines")


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/data", response_model=SankeyData)
async def get_sankey_data(
    start_date: Optional[datetime] = Query(None, description="Start date (default: 7 days ago)"),
    end_date: Optional[datetime] = Query(None, description="End date (default: now)"),
    factory_ids: Optional[str] = Query(None, description="Comma-separated factory IDs (default: all)"),
    min_energy_kwh: float = Query(0.0, description="Minimum energy to show (filter small flows)")
):
    """
    Get energy flow data for Sankey diagram.
    
    Hierarchy:
    - Level 0: Grid (single source)
    - Level 1: Factories
    - Level 2: Departments (location_in_factory)
    - Level 3: Machines
    
    Args:
        start_date: Start of analysis period
        end_date: End of analysis period
        factory_ids: Filter specific factories
        min_energy_kwh: Minimum energy threshold to reduce clutter
    
    Returns:
        SankeyData with nodes and links for visualization
    """
    try:
        # Default date range: last 7 days
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=7)
        
        # Parse factory IDs if provided
        factory_id_list = None
        if factory_ids:
            factory_id_list = [fid.strip() for fid in factory_ids.split(',')]
        
        # Get database pool
        pool = db.pool
        
        async with pool.acquire() as conn:
            # Query 1: Get factory-level aggregation
            factory_query = """
                SELECT 
                    f.id AS factory_id,
                    f.name AS factory_name,
                    COALESCE(SUM(er.energy_kwh), 0) AS total_energy_kwh,
                    COUNT(DISTINCT m.id) AS machine_count
                FROM factories f
                LEFT JOIN machines m ON m.factory_id = f.id AND m.is_active = TRUE
                LEFT JOIN energy_readings er ON er.machine_id = m.id 
                    AND er.time >= $1 AND er.time <= $2
                WHERE f.is_active = TRUE
            """
            
            if factory_id_list:
                factory_query += " AND f.id = ANY($3::uuid[])"
                factory_rows = await conn.fetch(factory_query, start_date, end_date, factory_id_list)
            else:
                factory_query += " GROUP BY f.id, f.name ORDER BY total_energy_kwh DESC"
                factory_rows = await conn.fetch(factory_query, start_date, end_date)
            
            # Query 2: Get department-level aggregation
            dept_query = """
                SELECT 
                    f.id AS factory_id,
                    f.name AS factory_name,
                    COALESCE(m.location_in_factory, 'Unassigned') AS department,
                    COALESCE(SUM(er.energy_kwh), 0) AS total_energy_kwh,
                    COUNT(DISTINCT m.id) AS machine_count
                FROM factories f
                LEFT JOIN machines m ON m.factory_id = f.id AND m.is_active = TRUE
                LEFT JOIN energy_readings er ON er.machine_id = m.id 
                    AND er.time >= $1 AND er.time <= $2
                WHERE f.is_active = TRUE
            """
            
            if factory_id_list:
                dept_query += " AND f.id = ANY($3::uuid[])"
                dept_query += " GROUP BY f.id, f.name, m.location_in_factory ORDER BY total_energy_kwh DESC"
                dept_rows = await conn.fetch(dept_query, start_date, end_date, factory_id_list)
            else:
                dept_query += " GROUP BY f.id, f.name, m.location_in_factory ORDER BY total_energy_kwh DESC"
                dept_rows = await conn.fetch(dept_query, start_date, end_date)
            
            # Query 3: Get machine-level aggregation
            machine_query = """
                SELECT 
                    f.id AS factory_id,
                    f.name AS factory_name,
                    COALESCE(m.location_in_factory, 'Unassigned') AS department,
                    m.id AS machine_id,
                    m.name AS machine_name,
                    m.type AS machine_type,
                    COALESCE(SUM(er.energy_kwh), 0) AS total_energy_kwh
                FROM factories f
                JOIN machines m ON m.factory_id = f.id AND m.is_active = TRUE
                LEFT JOIN energy_readings er ON er.machine_id = m.id 
                    AND er.time >= $1 AND er.time <= $2
                WHERE f.is_active = TRUE
            """
            
            if factory_id_list:
                machine_query += " AND f.id = ANY($3::uuid[])"
                machine_query += " GROUP BY f.id, f.name, m.location_in_factory, m.id, m.name, m.type"
                machine_query += " HAVING SUM(er.energy_kwh) >= $4 ORDER BY total_energy_kwh DESC"
                machine_rows = await conn.fetch(machine_query, start_date, end_date, factory_id_list, min_energy_kwh)
            else:
                machine_query += " GROUP BY f.id, f.name, m.location_in_factory, m.id, m.name, m.type"
                machine_query += " HAVING SUM(er.energy_kwh) >= $3 ORDER BY total_energy_kwh DESC"
                machine_rows = await conn.fetch(machine_query, start_date, end_date, min_energy_kwh)
        
        # Build Sankey structure
        nodes = []
        links = []
        
        # Level 0: Grid (single source)
        total_energy = sum(row['total_energy_kwh'] for row in factory_rows)
        nodes.append(SankeyNode(id="grid", name="Grid", level=0))
        
        # Level 1: Factories
        factory_energies = {}
        for row in factory_rows:
            factory_id = str(row['factory_id'])
            factory_name = row['factory_name']
            energy = row['total_energy_kwh']
            
            if energy >= min_energy_kwh:
                nodes.append(SankeyNode(
                    id=f"factory_{factory_id}",
                    name=factory_name,
                    level=1
                ))
                
                # Link: Grid → Factory
                links.append(SankeyLink(
                    source="grid",
                    target=f"factory_{factory_id}",
                    value=energy,
                    percentage=round((energy / total_energy * 100) if total_energy > 0 else 0, 2)
                ))
                
                factory_energies[factory_id] = energy
        
        # Level 2: Departments
        dept_energies = {}
        for row in dept_rows:
            factory_id = str(row['factory_id'])
            department = row['department']
            energy = row['total_energy_kwh']
            
            if energy >= min_energy_kwh and factory_id in factory_energies:
                dept_id = f"dept_{factory_id}_{department}"
                
                # Add department node if not already added
                if not any(node.id == dept_id for node in nodes):
                    nodes.append(SankeyNode(
                        id=dept_id,
                        name=f"{department}",
                        level=2
                    ))
                
                # Link: Factory → Department
                links.append(SankeyLink(
                    source=f"factory_{factory_id}",
                    target=dept_id,
                    value=energy,
                    percentage=round((energy / factory_energies[factory_id] * 100) if factory_energies[factory_id] > 0 else 0, 2)
                ))
                
                dept_energies[dept_id] = energy
        
        # Level 3: Machines
        for row in machine_rows:
            factory_id = str(row['factory_id'])
            department = row['department']
            machine_id = str(row['machine_id'])
            machine_name = row['machine_name']
            energy = row['total_energy_kwh']
            
            dept_id = f"dept_{factory_id}_{department}"
            
            if energy >= min_energy_kwh and dept_id in dept_energies:
                # Add machine node
                nodes.append(SankeyNode(
                    id=f"machine_{machine_id}",
                    name=machine_name,
                    level=3
                ))
                
                # Link: Department → Machine
                links.append(SankeyLink(
                    source=dept_id,
                    target=f"machine_{machine_id}",
                    value=energy,
                    percentage=round((energy / dept_energies[dept_id] * 100) if dept_energies[dept_id] > 0 else 0, 2)
                ))
        
        # Build response
        unique_factories = set(str(row['factory_id']) for row in factory_rows)
        unique_depts = set(f"{row['factory_id']}_{row['department']}" for row in dept_rows)
        unique_machines = set(str(row['machine_id']) for row in machine_rows)
        
        return SankeyData(
            nodes=nodes,
            links=links,
            total_energy_kwh=round(total_energy, 3),
            start_date=start_date,
            end_date=end_date,
            factory_count=len(unique_factories),
            department_count=len(unique_depts),
            machine_count=len(unique_machines)
        )
        
    except Exception as e:
        logger.error(f"Error generating Sankey data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate Sankey data: {str(e)}")


@router.get("/factories", response_model=List[dict])
async def get_available_factories():
    """
    Get list of available factories for filtering.
    
    Returns:
        List of factories with their IDs and names
    """
    try:
        pool = db.pool
        
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, name, location
                FROM factories
                WHERE is_active = TRUE
                ORDER BY name
            """)
        
        return [
            {
                "id": str(row['id']),
                "name": row['name'],
                "location": row['location']
            }
            for row in rows
        ]
        
    except Exception as e:
        logger.error(f"Error fetching factories: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch factories: {str(e)}")