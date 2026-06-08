"""
EnMS Analytics Service - Baseline API Routes
=============================================
REST API endpoints for energy baseline models.

Author: EnMS Team
Phase: 3 - Analytics & ML
"""

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
import logging

from services.baseline_service import baseline_service
from services.driver_analysis_service import driver_analysis_service
from services.model_explainer import model_explainer
from services.seu_baseline_service import seu_baseline_service
from models.seu import TrainBaselineRequest as SEUBaselineTrainRequest
from database import db

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Helper Functions
# ============================================================================

async def get_seu_by_name_and_energy_source(
    seu_name: str, 
    energy_source: str
) -> Optional[Dict[str, Any]]:
    """
    Lookup SEU by name and energy source.
    Reused from ovos_training.py for consistency.
    """
    query = """
        SELECT 
            s.id, s.name, s.description, s.energy_source_id, s.machine_ids,
            es.name as energy_source_name, es.unit as energy_unit
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


# ============================================================================
# Request/Response Models
# ============================================================================

class TrainBaselineRequest(BaseModel):
    """Request model for training baseline."""
    machine_id: UUID = Field(..., description="Machine UUID")
    start_date: datetime = Field(..., description="Training data start date (ISO 8601)")
    end_date: datetime = Field(..., description="Training data end date (ISO 8601)")
    drivers: Optional[List[str]] = Field(
        None,
        description="List of driver/feature names (if None, auto-select)",
        example=["total_production_count", "avg_outdoor_temp_c", "avg_pressure_bar"]
    )


class PredictEnergyRequest(BaseModel):
    """
    Request model for energy prediction.
    
    ENHANCEMENT (Nov 4, 2025): Supports BOTH UUID and SEU name inputs
    - Dashboard usage: Provide machine_id (UUID)
    - OVOS/Voice usage: Provide seu_name + energy_source
    """
    # Option 1: UUID-based (existing dashboard usage)
    machine_id: Optional[UUID] = Field(
        default=None, 
        description="Machine UUID (for dashboard/programmatic access)"
    )
    
    # Option 2: SEU name-based (NEW - OVOS/voice usage)
    seu_name: Optional[str] = Field(
        default=None,
        description="SEU name for voice-friendly access (e.g., 'Compressor-1')"
    )
    energy_source: Optional[str] = Field(
        default=None,
        description="Energy source name (e.g., 'electricity', 'natural_gas', 'steam', 'compressed_air')"
    )
    
    # Common parameters
    features: Dict[str, float] = Field(
        ...,
        description="Feature values for prediction",
        example={
            "total_production_count": 500,
            "avg_outdoor_temp_c": 25.5,
            "avg_pressure_bar": 7.2
        }
    )
    
    # NEW: Voice-friendly response flag
    include_message: bool = Field(
        False,
        description="Include voice-friendly message in response (for OVOS/TTS)"
    )
    
    @model_validator(mode='after')
    def check_identifier(self):
        """Ensure either machine_id OR (seu_name + energy_source) is provided."""
        machine_id = self.machine_id
        seu_name = self.seu_name
        energy_source = self.energy_source
        
        # Check if we have either UUID or SEU name combo
        has_uuid = machine_id is not None
        has_seu = seu_name is not None and energy_source is not None
        
        if not has_uuid and not has_seu:
            raise ValueError(
                "Must provide either 'machine_id' OR both 'seu_name' and 'energy_source'"
            )
        
        if seu_name is not None and energy_source is None:
            raise ValueError(
                "When using 'seu_name', 'energy_source' is also required"
            )
        
        if energy_source is not None and seu_name is None:
            raise ValueError(
                "When using 'energy_source', 'seu_name' is also required"
            )
        
        return self
    
    class Config:
        schema_extra = {
            "examples": [
                {
                    "name": "UUID-based (Dashboard)",
                    "value": {
                        "machine_id": "c0000000-0000-0000-0000-000000000001",
                        "features": {
                            "total_production_count": 500,
                            "avg_outdoor_temp_c": 22.5,
                            "avg_pressure_bar": 7.0
                        }
                    }
                },
                {
                    "name": "SEU name-based (OVOS/Voice)",
                    "value": {
                        "seu_name": "Compressor-1",
                        "energy_source": "electricity",
                        "features": {
                            "total_production_count": 500,
                            "avg_outdoor_temp_c": 22.5,
                            "avg_pressure_bar": 7.0
                        },
                        "include_message": True
                    }
                }
            ]
        }


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/baseline/train", tags=["Baseline"])
async def train_baseline(request: TrainBaselineRequest):
    """
    Train a new energy baseline model for a machine.
    
    **Requirements:**
    - Minimum 1000 data points
    - Target R² > 0.80 for quality baseline
    
    **Process:**
    1. Fetch historical data (energy + production + environmental)
    2. Filter by machine status (exclude maintenance/fault periods)
    3. Train Multiple Linear Regression model
    4. Validate model quality (R², RMSE, MAE)
    5. Save model to disk and database
    6. Deactivate previous models
    
    **Returns:**
    - Model ID and version
    - Performance metrics (R², RMSE, MAE)
    - Model coefficients and intercept
    - Feature names used
    """
    try:
        logger.info(f"[TRAIN-API] Received training request: machine_id={request.machine_id}, start={request.start_date}, end={request.end_date}, drivers={request.drivers}")
        
        # Deduplicate drivers (e.g., both "production_count" and "total_production" map to same column)
        drivers = list(dict.fromkeys(request.drivers)) if request.drivers else None
        if drivers and len(drivers) != len(request.drivers or []):
            logger.info(f"[TRAIN-API] Deduplicated drivers: {len(request.drivers)} -> {len(drivers)} unique columns")
        
        result = await baseline_service.train_baseline(
            machine_id=request.machine_id,
            start_date=request.start_date,
            end_date=request.end_date,
            drivers=drivers
        )
        
        logger.info(f"[TRAIN-API] Training completed successfully")
        return result
    
    except ValueError as e:
        logger.error(f"[TRAIN-API] ValueError occurred: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[TRAIN-API] Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/baseline/deviation", tags=["Baseline"])
async def get_baseline_deviation(
    machine_id: UUID = Query(..., description="Machine UUID"),
    start: datetime = Query(..., description="Start of analysis period (ISO 8601)"),
    end: datetime = Query(..., description="End of analysis period (ISO 8601)")
):
    """
    Calculate baseline performance deviation for a machine.
    
    **Deviation Calculation:**
    ```
    Deviation (kWh) = Actual Energy - Predicted Energy
    Deviation (%) = (Deviation / Predicted) × 100
    ```
    
    **Severity Levels:**
    - **Normal**: |Deviation| < 5%
    - **Warning**: 5% ≤ |Deviation| < 15%
    - **Critical**: |Deviation| ≥ 15%
    
    **Use Cases:**
    - Detect equipment degradation
    - Identify operational inefficiencies
    - Validate energy optimization measures
    - ISO 50001 compliance reporting
    
    **Returns:**
    - Total actual vs. predicted energy
    - Overall deviation (kWh and %)
    - Severity classification
    - Hourly breakdown of deviations
    """
    try:
        result = await baseline_service.get_baseline_deviation(
            machine_id=machine_id,
            start_time=start,
            end_time=end
        )
        return result
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error calculating deviation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/baseline/predict", tags=["Baseline"])
async def predict_energy(request: PredictEnergyRequest):
    """
    Predict energy consumption for given operating conditions.
    
    **ENHANCED (Nov 4, 2025):** Now supports BOTH UUID and SEU name inputs!
    
    **Input Methods:**
    
    **Method 1: UUID-based (Dashboard/Programmatic)**
    ```json
    {
      "machine_id": "c0000000-0000-0000-0000-000000000001",
      "features": {
        "total_production_count": 1000,
        "avg_outdoor_temp_c": 22.0,
        "avg_pressure_bar": 7.5
      }
    }
    ```
    
    **Method 2: SEU name-based (OVOS/Voice Assistant)** ⭐ NEW
    ```json
    {
      "seu_name": "Compressor-1",
      "energy_source": "electricity",
      "features": {
        "total_production_count": 1000,
        "avg_outdoor_temp_c": 22.0,
        "avg_pressure_bar": 7.5
      },
      "include_message": true
    }
    ```
    
    **Use Cases:**
    - What-if analysis for production planning
    - Energy forecasting for load scheduling
    - Voice queries: "What's the expected energy for Compressor-1 at 500 units?"
    - Capacity planning and cost estimation
    
    **Returns:**
    - Predicted energy consumption (kWh or other unit)
    - Model version used
    - Input features
    - Optional: Voice-friendly message (when include_message=true)
    """
    try:
        # Step 1: Resolve machine_id (from UUID or SEU name)
        machine_id = request.machine_id
        seu_name_for_message = None
        energy_unit = "kWh"  # default
        seu = None  # Initialize to None (used later for energy_source_id)
        
        if machine_id is None:
            # SEU name-based lookup
            logger.info(f"[PREDICT] SEU name-based lookup: {request.seu_name} ({request.energy_source})")
            
            seu = await get_seu_by_name_and_energy_source(
                request.seu_name,
                request.energy_source
            )
            
            if not seu:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "error": "SEU_NOT_FOUND",
                        "message": f"Could not find SEU '{request.seu_name}' with energy source '{request.energy_source}'",
                        "suggestion": "Check SEU name spelling or use GET /api/v1/ovos/seus to list available SEUs"
                    }
                )
            
            # Get first machine ID from SEU
            if not seu['machine_ids'] or len(seu['machine_ids']) == 0:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "NO_MACHINES",
                        "message": f"SEU '{request.seu_name}' has no associated machines"
                    }
                )
            
            machine_id = seu['machine_ids'][0]
            seu_name_for_message = seu['name']
            energy_unit = seu.get('energy_unit', 'kWh')
            
            logger.info(f"[PREDICT] Resolved SEU '{request.seu_name}' to machine_id: {machine_id}")
        else:
            logger.info(f"[PREDICT] UUID-based lookup: {machine_id}")
        
        # Step 2: Make prediction using baseline service
        # Pass energy_source_id if SEU-based lookup was used
        energy_source_id_for_predict = seu.get('energy_source_id') if seu else None
        
        result = await baseline_service.predict_energy(
            machine_id=machine_id,
            features=request.features,
            energy_source_id=energy_source_id_for_predict  # NEW: Support multi-energy
        )
        
        # Step 3: Add voice-friendly message if requested
        if request.include_message:
            predicted_value = result.get('predicted_energy_kwh', 0)
            warnings = result.get('warnings', [])
            
            # Build natural language message
            if seu_name_for_message:
                message = (
                    f"{seu_name_for_message} is predicted to consume "
                    f"{predicted_value:.1f} {energy_unit} under these conditions"
                )
            else:
                message = f"Predicted energy consumption: {predicted_value:.1f} {energy_unit}"
            
            # Add warning suffix if inputs are out of range
            if warnings:
                message += f". Warning: {len(warnings)} input(s) outside training range"
            
            result['message'] = message
            result['energy_unit'] = energy_unit
        
        logger.info(f"[PREDICT] Prediction successful: {result.get('predicted_energy_kwh', 0):.2f} {energy_unit}")
        return result
    
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"[PREDICT] ValueError: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[PREDICT] Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/baseline/models", tags=["Baseline"])
async def list_baseline_models(
    machine_id: Optional[UUID] = Query(None, description="Machine UUID (Option 1)"),
    seu_name: Optional[str] = Query(None, description="SEU name (Option 2 - for OVOS)"),
    energy_source: Optional[str] = Query(None, description="Energy source (required with seu_name)"),
    include_explanation: bool = Query(False, description="Include natural language explanations")
):
    """
    List all baseline models for a machine.
    
    **ENHANCED (November 2025):** Now accepts BOTH UUID and SEU name!
    
    **Parameters:**
    - **Option 1 - Dashboard usage (UUID):**
      - `machine_id`: Machine UUID
    - **Option 2 - Voice usage (SEU name) - NEW:**
      - `seu_name`: SEU name (e.g., "Compressor-1")
      - `energy_source`: "electricity", "natural_gas", "steam", "compressed_air"
    - `include_explanation`: Add natural language explanations to each model (default: false)
    
    **Returns:**
    - List of all models (active and inactive)
    - Model versions, performance metrics
    - Training dates and sample counts
    - Optional: Natural language explanations
    - Ordered by version (newest first)
    
    **OVOS Use Cases:**
    - "List baseline models for Compressor-1"
    - "Show me all models with explanations"
    - "What models exist for electricity?"
    """
    try:
        # Validation: Must provide exactly one input method
        if machine_id is None and (seu_name is None or energy_source is None):
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "MISSING_IDENTIFIER",
                    "message": "Must provide either 'machine_id' OR ('seu_name' + 'energy_source')",
                    "examples": {
                        "option_1": "?machine_id=c0000000-0000-0000-0000-000000000001",
                        "option_2": "?seu_name=Compressor-1&energy_source=electricity"
                    }
                }
            )
        
        if machine_id is not None and seu_name is not None:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "CONFLICTING_IDENTIFIERS",
                    "message": "Cannot provide both 'machine_id' and 'seu_name'. Choose one method.",
                }
            )
        
        # Resolve machine_id from SEU name if needed
        resolved_machine_id = machine_id
        seu_display_name = None
        energy_source_id_for_list = None  # Initialize to prevent NameError
        
        if machine_id is None:
            # Look up SEU
            seu = await get_seu_by_name_and_energy_source(seu_name, energy_source)
            if not seu:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "error": "SEU_NOT_FOUND",
                        "message": f"Could not find SEU '{seu_name}' with energy source '{energy_source}'.",
                        "suggestion": "Use GET /api/v1/ovos/seus to list all available SEUs."
                    }
                )
            
            # Get first machine ID from the SEU
            machine_ids = seu.get('machine_ids', [])
            if not machine_ids:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "error": "NO_MACHINE_FOR_SEU",
                        "message": f"SEU '{seu_name}' has no associated machines.",
                    }
                )
            
            resolved_machine_id = machine_ids[0]
            seu_display_name = seu.get('seu_name') or seu_name
            energy_source_id_for_list = seu.get('energy_source_id')  # Get energy_source_id
        
        # Get models (filtered by energy source if SEU-based)
        models = await baseline_service.list_baseline_models(
            resolved_machine_id,
            energy_source_id=energy_source_id_for_list if seu_display_name else None
        )
        
        # Add explanations if requested
        if include_explanation:
            for model in models:
                # Get full model details (includes coefficients)
                full_model = await baseline_service.get_model_details(model['id'])
                if full_model:
                    explanation = model_explainer.explain_model(full_model)
                    model['explanation'] = explanation
        
        response = {
            'machine_id': str(resolved_machine_id),
            'total_models': len(models),
            'models': models
        }
        
        # Add SEU info if accessed via SEU name
        if seu_display_name:
            response['seu_name'] = seu_display_name
            response['energy_source'] = energy_source
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/baseline/drivers", tags=["Baseline"])
async def get_seu_driver_analysis(
    seu_name: str = Query(..., description="SEU name, for example Compressor-1"),
    energy_source: str = Query(..., description="Energy source, for example electricity"),
    driver_name: Optional[str] = Query(None, description="Optional specific driver to inspect, for example temperature"),
    top_n: int = Query(3, description="Number of top drivers to return", ge=1, le=10),
):
    """Return learned drivers for a specific SEU.

    If no active baseline exists, the response explains that training is required and
    returns candidate drivers derived from the energy-source feature registry.
    """
    try:
        return await driver_analysis_service.get_seu_driver_analysis(
            seu_name=seu_name,
            energy_source=energy_source,
            requested_driver=driver_name,
            top_n=top_n,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"Error retrieving driver analysis: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/baseline/drivers/factory", tags=["Baseline"])
async def get_factory_driver_analysis(
    energy_source: Optional[str] = Query(None, description="Optional energy-source filter"),
    driver_name: Optional[str] = Query(None, description="Optional specific driver to inspect"),
    top_n: int = Query(5, description="Number of top drivers to return", ge=1, le=10),
):
    """Return aggregated learned drivers across active SEUs with baselines."""
    try:
        return await driver_analysis_service.get_factory_driver_analysis(
            energy_source=energy_source,
            requested_driver=driver_name,
            top_n=top_n,
        )
    except Exception as exc:
        logger.error(f"Error retrieving factory driver analysis: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/baseline/model/{model_id}", tags=["Baseline"])
async def get_model_details(
    model_id: UUID = Path(..., description="Model UUID"),
    include_explanation: bool = Query(
        False, 
        description="Include natural language explanation of model (for OVOS/voice)"
    )
):
    """
    Get detailed information about a specific baseline model.
    
    **ENHANCED (November 2025):** Adds optional natural language explanations for voice interfaces.
    
    **Parameters:**
    - `model_id`: Model UUID (required, in path)
    - `include_explanation`: Add voice-friendly explanations (optional, default: false)
    
    **Returns:**
    - Complete model metadata
    - Coefficients for each driver
    - Performance metrics
    - Training information
    - Natural language explanations (if requested)
    
    **OVOS Use Cases:**
    - "Explain the Compressor-1 baseline model"
    - "What are the key energy drivers?"
    - "How accurate is the model?"
    """
    try:
        model = await baseline_service.get_model_details(model_id)
        
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        
        # Add natural language explanation if requested
        if include_explanation:
            explanation = model_explainer.explain_model(model)
            model['explanation'] = explanation
        
        return model
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/baseline/model/{model_id}/activate", tags=["Baseline"])
async def activate_model(model_id: UUID = Path(..., description="Model UUID to activate")):
    """
    Activate a specific baseline model (sets it as the active model).
    
    Deactivates all other models for the same machine/energy_source and activates the selected one.
    
    **Use Cases:**
    - Revert to a previous model after testing
    - Activate better-performing older model
    - Switch between seasonal models
    
    **Returns:**
    - Updated model with is_active=true
    - Message confirming activation
    """
    try:
        # Get model details first
        model = await baseline_service.get_model_details(model_id)
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        
        machine_id = model['machine_id']
        energy_source_id = model.get('energy_source_id')
        
        # Deactivate all models for this machine/energy_source
        from database import db, deactivate_baseline_models
        await deactivate_baseline_models(machine_id, energy_source_id)
        
        # Activate the selected model
        async with db.pool.acquire() as conn:
            await conn.execute(
                "UPDATE energy_baselines SET is_active = true WHERE id = $1",
                model_id
            )
        
        logger.info(f"✓ Model {model_id} activated for machine {machine_id}")
        
        return {
            "success": True,
            "message": f"Model version {model['model_version']} is now active",
            "model_id": str(model_id),
            "machine_id": str(machine_id)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to activate model: {str(e)}")


@router.delete("/baseline/model/{model_id}", tags=["Baseline"])
async def delete_model(model_id: UUID = Path(..., description="Model UUID to delete")):
    """
    Delete a baseline model permanently.
    
    **WARNING:** This action cannot be undone!
    
    **Restrictions:**
    - Cannot delete the active model (deactivate/activate another first)
    - Deletes model metadata from database
    - Deletes saved model file from disk
    
    **Returns:**
    - Confirmation message
    """
    try:
        from database import db
        from pathlib import Path
        
        # Get model details
        model = await baseline_service.get_model_details(model_id)
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        
        # Check if active
        if model.get('is_active'):
            raise HTTPException(
                status_code=400, 
                detail="Cannot delete active model. Activate another model first."
            )
        
        # Delete from database
        async with db.pool.acquire() as conn:
            deleted = await conn.fetchval(
                "DELETE FROM energy_baselines WHERE id = $1 RETURNING id",
                model_id
            )
        
        if not deleted:
            raise HTTPException(status_code=404, detail="Model not found")
        
        # Delete model file from disk (if exists)
        try:
            model_path = Path(f"/app/models/saved/baseline/{model['machine_id']}_v{model['model_version']}.pkl")
            if model_path.exists():
                model_path.unlink()
                logger.info(f"Deleted model file: {model_path}")
        except Exception as e:
            logger.warning(f"Could not delete model file: {e}")
        
        logger.info(f"✓ Model {model_id} deleted")
        
        return {
            "success": True,
            "message": f"Model version {model['model_version']} deleted successfully",
            "model_id": str(model_id)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete model: {str(e)}")


# ============================================================================
# SEU-Based Training (Voice-Optimized)
# ============================================================================

class SEUTrainingRequest(BaseModel):
    """
    SEU-based training request (voice-friendly).
    
    Designed for natural language input from voice assistant.
    """
    seu_name: str = Field(..., description="SEU name (e.g., 'Compressor-1', 'HVAC-Main')")
    energy_source: str = Field(..., description="Energy source name (e.g., 'electricity', 'natural_gas', 'steam')")
    features: List[str] = Field(..., description="List of feature names to use in baseline (e.g., ['production_count', 'outdoor_temp_c'])")
    year: int = Field(..., description="Baseline year (e.g., 2024)", ge=2000, le=2100)
    
    class Config:
        json_schema_extra = {
            "example": {
                "seu_name": "Compressor-1",
                "energy_source": "electricity",
                "features": ["production_count", "outdoor_temp_c"],
                "year": 2024
            }
        }


class SEUTrainingResponse(BaseModel):
    """
    SEU-based training response (voice-friendly).
    
    Formatted for voice output and human readability.
    """
    success: bool
    message: str = Field(..., description="Voice-friendly message summarizing results")
    seu_name: str
    energy_source: str
    r_squared: Optional[float] = Field(None, description="R-squared value (0-1, higher is better)")
    rmse: Optional[float] = Field(None, description="Root mean squared error")
    formula_readable: Optional[str] = Field(None, description="Human-readable formula for voice output")
    formula_technical: Optional[str] = Field(None, description="Mathematical formula notation")
    samples_count: Optional[int] = Field(None, description="Number of days used for training")
    trained_at: Optional[datetime] = None
    error_details: Optional[str] = None


def _build_voice_formula(intercept: float, coefficients: Dict[str, float]) -> str:
    """Build voice-friendly formula."""
    parts = [f"{intercept:.6f}"]
    for feature, coef in coefficients.items():
        if coef >= 0:
            parts.append(f"plus {abs(coef):.6f} times {feature}")
        else:
            parts.append(f"minus {abs(coef):.6f} times {feature}")
    return "Energy equals " + " ".join(parts)


def _build_technical_formula(intercept: float, coefficients: Dict[str, float]) -> str:
    """Build technical formula."""
    parts = [f"{intercept:.6f}"]
    for feature, coef in coefficients.items():
        if coef >= 0:
            parts.append(f"+ {coef:.6f}*{feature}")
        else:
            parts.append(f"- {abs(coef):.6f}*{feature}")
    return "E = " + " ".join(parts)


async def _build_voice_friendly_error(error_type: str, seu_name: str, energy_source: str) -> SEUTrainingResponse:
    """Build voice-friendly error response."""
    messages = {
        "SEU_NOT_FOUND": f"Sorry, I couldn't find a SEU named {seu_name} with {energy_source} energy source.",
        "INVALID_FEATURES": f"Some of the requested features are not available for {seu_name} {energy_source}.",
        "INSUFFICIENT_DATA": f"Not enough historical data for {seu_name} {energy_source}. Need at least 7 days."
    }
    
    return SEUTrainingResponse(
        success=False,
        message=messages.get(error_type, "Training failed"),
        seu_name=seu_name,
        energy_source=energy_source,
        error_details=error_type
    )


@router.post("/baseline/train-seu", response_model=SEUTrainingResponse, tags=["Baseline"])
async def train_baseline_for_seu(request: SEUTrainingRequest):
    """
    Train baseline for SEU via voice command.
    
    **VOICE-OPTIMIZED** - Accepts SEU name + energy source (no UUIDs required).
    
    This endpoint is designed for natural language input from voice assistants.
    It accepts SEU name + energy source + features, looks up the SEU dynamically,
    validates features exist, trains the baseline, and returns a voice-friendly response.
    
    **ZERO HARDCODING:** Works for ANY energy source (electricity, natural gas, steam, etc.)
    as long as the energy source and features are defined in the database.
    
    **Parameters:**
    - `seu_name`: SEU name (e.g., "Compressor-1")
    - `energy_source`: Energy type (e.g., "electricity", "natural_gas")
    - `features`: List of feature names (e.g., ["production_count", "outdoor_temp_c"])
    - `year`: Training year (e.g., 2024)
    
    **Example:**
    ```bash
    curl -X POST "http://localhost:8001/api/v1/baseline/train-seu" \\
      -H "Content-Type: application/json" \\
      -d '{
        "seu_name": "Compressor-1",
        "energy_source": "electricity",
        "features": ["production_count", "outdoor_temp_c"],
        "year": 2024
      }'
    ```
    
    **OVOS Use Cases:**
    - "Train baseline for Compressor-1 electricity using production count"
    - "Create baseline for Boiler-1 natural gas with outdoor temperature"
    
    **Voice Response:**
    "Compressor-1 electricity baseline trained successfully. R-squared 0.99 (99% accuracy). 
    Energy equals 0.061 plus 0.000043 times production count minus 0.000004 times outdoor temperature."
    
    **Returns:**
    - Voice-friendly training results
    - R² accuracy and performance metrics
    - Human-readable formula
    - Technical formula notation
    """
    try:
        logger.info(
            f"[BASELINE-TRAIN-SEU] Voice request: SEU='{request.seu_name}', "
            f"Energy='{request.energy_source}', Features={request.features}, Year={request.year}"
        )
        
        # Step 1: Lookup SEU by name and energy source
        seu = await get_seu_by_name_and_energy_source(
            request.seu_name, 
            request.energy_source
        )
        
        if not seu:
            return await _build_voice_friendly_error(
                "SEU_NOT_FOUND",
                seu_name=request.seu_name,
                energy_source=request.energy_source
            )
        
        # Convert UUID to proper type
        seu_id = UUID(str(seu['id']))
        
        logger.info(f"[BASELINE-TRAIN-SEU] Found SEU: {seu['id']} - {seu['name']}")
        
        # Convert energy_source_id to UUID
        energy_source_id = UUID(str(seu['energy_source_id']))
        
        # Step 2: Validate features exist for this energy source
        from services.feature_discovery import feature_discovery
        
        is_valid, valid_features, invalid_features = await feature_discovery.validate_features(
            energy_source_id=energy_source_id,
            requested_features=request.features
        )
        
        if not is_valid:
            # Return voice-friendly error instead of HTTP exception
            return await _build_voice_friendly_error(
                "INVALID_FEATURES",
                seu_name=request.seu_name,
                energy_source=request.energy_source
            )
        
        logger.info(f"[BASELINE-TRAIN-SEU] Features validated: {valid_features}")

        # Step 3: Convert year to SEU training date range
        start_date = datetime(request.year, 1, 1, 0, 0, 0)
        end_date = datetime(request.year, 12, 31, 23, 59, 59)

        selected_features = valid_features or ['production_count', 'outdoor_temp_c', 'is_weekend']

        if valid_features:
            logger.info(f"[BASELINE-TRAIN-SEU] User requested SEU features: {selected_features}")
        else:
            logger.info(
                f"[BASELINE-TRAIN-SEU] No features requested, using default SEU features: {selected_features}"
            )

        seu_train_request = SEUBaselineTrainRequest(
            seu_id=seu_id,
            baseline_year=request.year,
            start_date=start_date.date(),
            end_date=end_date.date(),
            features=selected_features
        )

        training_response = await seu_baseline_service.train_baseline(
            seu_train_request
        )
        
        logger.info(
            f"[BASELINE-TRAIN-SEU] Training complete: R²={training_response.r_squared}, "
            f"Samples={training_response.samples_count}"
        )
        
        # Step 6: Format response for voice output
        formula_readable = _build_voice_formula(
            intercept=training_response.intercept,
            coefficients=training_response.coefficients
        )
        
        formula_technical = _build_technical_formula(
            intercept=training_response.intercept,
            coefficients=training_response.coefficients
        )
        
        # Build voice-friendly message
        r2_percent = round(training_response.r_squared * 100)
        message = (
            f"{request.seu_name} {request.energy_source} baseline trained successfully. "
            f"R-squared {training_response.r_squared:.2f} ({r2_percent}% accuracy). "
            f"{formula_readable}"
        )
        
        return SEUTrainingResponse(
            success=True,
            message=message,
            seu_name=request.seu_name,
            energy_source=request.energy_source,
            r_squared=training_response.r_squared,
            rmse=training_response.rmse,
            formula_readable=formula_readable,
            formula_technical=formula_technical,
            samples_count=training_response.samples_count,
            trained_at=training_response.trained_at
        )
    
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    
    except Exception as e:
        logger.error(f"[BASELINE-TRAIN-SEU] Training failed: {e}", exc_info=True)
        
        return SEUTrainingResponse(
            success=False,
            message=f"Training failed for {request.seu_name} {request.energy_source}: {str(e)}",
            seu_name=request.seu_name,
            energy_source=request.energy_source,
            error_details=str(e)
        )


# ============================================================================
# Model Details Endpoint
# ============================================================================

@router.get("/baseline/model/{model_id}/details", tags=["Baseline"])
async def get_model_details(
    model_id: UUID = Path(..., description="Model UUID")
) -> Dict[str, Any]:
    """
    Get detailed information about a baseline model.
    
    Returns:
        - Model metadata (version, training date, metrics)
        - Features/drivers used
        - Training data period
        - Hyperparameters
        - Data completeness
    """
    try:
        query = """
            SELECT 
                eb.id, eb.machine_id, eb.model_version, eb.created_at,
                eb.is_active, eb.training_start_date, eb.training_end_date,
                eb.training_samples, eb.r_squared, eb.rmse, eb.mae,
                eb.feature_names, eb.intercept, eb.coefficients,
                eb.energy_source_id,
                m.name as machine_name,
                es.name as energy_source_name, es.unit as energy_unit
            FROM energy_baselines eb
            JOIN machines m ON eb.machine_id = m.id
            LEFT JOIN energy_sources es ON eb.energy_source_id = es.id
            WHERE eb.id = $1
        """
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, model_id)
        
        if not row:
            raise HTTPException(status_code=404, detail=f"Model not found: {model_id}")
        
        # Build feature details with coefficients
        features = row['feature_names'] or []
        coefficients_raw = row['coefficients']
        
        # Handle JSONB - might be string or dict
        import json
        if isinstance(coefficients_raw, str):
            coefficients_dict = json.loads(coefficients_raw)
        elif isinstance(coefficients_raw, dict):
            coefficients_dict = coefficients_raw
        else:
            coefficients_dict = {}
            
        intercept = float(row['intercept']) if row['intercept'] is not None else 0.0
        
        feature_details = []
        for feature in features:
            coef = float(coefficients_dict.get(feature, 0.0))
            feature_details.append({
                "name": feature,
                "coefficient": round(coef, 4),
                "impact": "positive" if coef > 0 else "negative" if coef < 0 else "neutral"
            })
        
        # Sort by absolute coefficient value (most important first)
        feature_details.sort(key=lambda x: abs(x['coefficient']), reverse=True)
        
        # Build formula
        formula_parts = [f"{intercept:.2f}"]
        for fd in feature_details:
            sign = "+" if fd['coefficient'] > 0 else ""
            formula_parts.append(f"{sign}{fd['coefficient']:.4f}*{fd['name']}")
        formula = " ".join(formula_parts)
        
        # Calculate data quality metrics
        training_days = (row['training_end_date'] - row['training_start_date']).days if row['training_end_date'] and row['training_start_date'] else 0
        samples_per_day = row['training_samples'] / training_days if training_days > 0 else 0
        
        return {
            "success": True,
            "model_id": str(row['id']),
            "machine_id": str(row['machine_id']),
            "machine_name": row['machine_name'],
            "model_version": row['model_version'],
            "is_active": row['is_active'],
            "trained_at": row['created_at'].isoformat(),
            
            # Training period
            "training_period": {
                    "start": row['training_start_date'].isoformat() if row['training_start_date'] else None,
                    "end": row['training_end_date'].isoformat() if row['training_end_date'] else None,
                "samples": row['training_samples'],
                "samples_per_day": round(samples_per_day, 1)
            },
            
            # Performance metrics
            "metrics": {
                "r_squared": round(row['r_squared'], 4),
                "rmse": round(row['rmse'], 2),
                "mae": round(row['mae'], 2),
                "accuracy_percent": round(row['r_squared'] * 100, 1)
            },
            
            # Energy source
            "energy_source": {
                "name": row['energy_source_name'] or "Electricity",
                "unit": row['energy_unit'] or "kWh"
            },
            
            # Features/drivers
            "features": {
                "count": len(features),
                "names": features,
                "details": feature_details
            },
            
            # Model formula
            "formula": {
                "intercept": round(intercept, 4),
                "equation": formula,
                "readable": "Energy = {:.2f} + {}...".format(
                    intercept,
                    " + ".join(["{:.2f}*{}".format(fd['coefficient'], fd['name']) for fd in feature_details[:3]])
                )
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get model details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))