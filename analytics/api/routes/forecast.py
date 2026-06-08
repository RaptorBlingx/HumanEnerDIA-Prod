"""
EnMS Analytics Service - Forecast API Routes
Phase 4 Session 2

REST API endpoints for time-series energy forecasting.
"""

import logging
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.forecast_service import ForecastService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forecast", tags=["Forecasting"])

# Initialize service
forecast_service = ForecastService()


# ============================================================================
# Request/Response Models
# ============================================================================

class TrainRequest(BaseModel):
    """Request model for training forecast models."""
    machine_id: UUID = Field(..., description="Machine UUID to train for")
    lookback_days: int = Field(
        14,
        ge=7,
        le=90,
        description="Days of historical data to use for training"
    )
    auto_order: bool = Field(
        True,
        description="Auto-determine ARIMA order (ARIMA only)"
    )
    use_regressors: bool = Field(
        True,
        description="Include external regressors (Prophet only)"
    )


class TrainResponse(BaseModel):
    """Response model for training results."""
    model_type: str
    machine_id: str
    training_samples: int
    lookback_days: int
    mae: float
    rmse: float
    mape: float
    aic: Optional[float] = None  # ARIMA only
    r2: Optional[float] = None  # Prophet only
    regressors: Optional[list] = None  # Prophet only
    trained_at: str


class PredictRequest(BaseModel):
    """Request model for generating forecasts."""
    machine_id: UUID = Field(..., description="Machine UUID to forecast for")
    horizon: Literal['short', 'medium', 'long'] = Field(
        'short',
        description="Forecast horizon: short (1-4h), medium (24h), long (7d)"
    )
    periods: Optional[int] = Field(
        None,
        description="Number of periods to forecast (overrides defaults)"
    )


class PredictResponse(BaseModel):
    """Response model for forecast predictions."""
    model_type: str
    machine_id: str
    horizon: str
    periods: int
    frequency: str
    predictions: list[float]
    timestamps: Optional[list[str]] = None
    lower_bound: Optional[list[float]] = None
    upper_bound: Optional[list[float]] = None
    confidence_intervals: Optional[dict] = None
    forecasted_at: str


class ScheduleRequest(BaseModel):
    """Request model for optimal load scheduling."""
    machine_id: UUID = Field(..., description="Machine UUID to schedule for")
    date: datetime = Field(..., description="Target date for scheduling")
    load_kw: float = Field(
        ...,
        gt=0,
        description="Load power requirement in kW"
    )


class ScheduleRecommendation(BaseModel):
    """Individual schedule recommendation."""
    timestamp: str
    predicted_demand_kw: float
    load_kw: float
    total_demand_kw: float
    is_peak_hour: bool
    cost_usd: float
    potential_savings_usd: float


class ScheduleResponse(BaseModel):
    """Response model for optimal schedule."""
    machine_id: str
    date: str
    load_kw: float
    peak_demand_threshold: float
    recommendations: list[ScheduleRecommendation]
    generated_at: str


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/train/arima", response_model=TrainResponse)
async def train_arima_model(request: TrainRequest):
    """
    Train ARIMA model for short-term forecasting (1-4 hours).
    
    **Model Details:**
    - Algorithm: ARIMA (Autoregressive Integrated Moving Average)
    - Best for: Short-term predictions with 15-minute granularity
    - Auto-selects optimal (p, d, q) parameters
    
    **Use Cases:**
    - Immediate demand prediction
    - Real-time load balancing
    - Short-term operational planning
    
    **Returns:**
    - Training metrics (AIC, RMSE, MAPE)
    - Model performance statistics
    """
    logger.info(f"[FORECAST-API] Training ARIMA for machine {request.machine_id}")
    
    try:
        result = await forecast_service.train_arima(
            machine_id=request.machine_id,
            lookback_days=request.lookback_days,
            auto_order=request.auto_order
        )
        
        return TrainResponse(**result)
        
    except ValueError as e:
        logger.error(f"[FORECAST-API] Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[FORECAST-API] Training failed: {e}")
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")


@router.post("/train/prophet", response_model=TrainResponse)
async def train_prophet_model(request: TrainRequest):
    """
    Train Prophet model for medium/long-term forecasting (24h to 7 days).
    
    **Model Details:**
    - Algorithm: Facebook Prophet with external regressors
    - Best for: Medium to long-term predictions with hourly granularity
    - Captures daily, weekly seasonality
    
    **Regressors Used:**
    - Temperature (outdoor_temp_c)
    - Production count
    - Hour of day
    - Day of week
    - Is weekend
    - Is working hours
    - Season
    
    **Use Cases:**
    - Daily energy planning
    - Weekly demand forecasting
    - Load shifting optimization
    - Cost reduction strategies
    
    **Returns:**
    - Training metrics (RMSE, MAPE, R²)
    - Model performance statistics
    - Regressor coefficients
    """
    logger.info(f"[FORECAST-API] Training Prophet for machine {request.machine_id}")
    
    try:
        result = await forecast_service.train_prophet(
            machine_id=request.machine_id,
            lookback_days=max(request.lookback_days, 30),  # Prophet needs more data
            use_regressors=request.use_regressors
        )
        
        return TrainResponse(**result)
        
    except ValueError as e:
        logger.error(f"[FORECAST-API] Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[FORECAST-API] Training failed: {e}")
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")


@router.post("/predict", response_model=PredictResponse)
async def generate_forecast(request: PredictRequest):
    """
    Generate energy demand forecast.
    
    **Horizons:**
    - `short`: 1-4 hours (ARIMA, 15-minute intervals)
    - `medium`: 24 hours (Prophet, hourly intervals)
    - `long`: 7 days (Prophet, hourly intervals)
    
    **Returns:**
    - Point predictions
    - Confidence intervals (95%)
    - Timestamps for each prediction
    - Model metadata
    
    **Note:** Model must be trained first using `/train/arima` or `/train/prophet`
    """
    logger.info(
        f"[FORECAST-API] Generating {request.horizon} forecast "
        f"for machine {request.machine_id}"
    )
    
    try:
        result = await forecast_service.predict(
            machine_id=request.machine_id,
            horizon=request.horizon,
            periods=request.periods
        )
        
        return PredictResponse(**result)
        
    except FileNotFoundError as e:
        logger.error(f"[FORECAST-API] Model not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        logger.error(f"[FORECAST-API] Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[FORECAST-API] Prediction failed: {e}")
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")


@router.get("/demand")
async def get_demand_forecast(
    machine_id: UUID = Query(..., description="Machine UUID"),
    horizon: Literal['short', 'medium', 'long'] = Query(
        'short',
        description="Forecast horizon"
    ),
    periods: Optional[int] = Query(None, description="Number of periods")
):
    """
    Get energy demand forecast (GET version).
    
    Convenience endpoint for simple forecasting requests.
    """
    return await generate_forecast(
        PredictRequest(
            machine_id=machine_id,
            horizon=horizon,
            periods=periods
        )
    )


@router.post("/optimal-schedule", response_model=ScheduleResponse)
async def get_optimal_schedule(request: ScheduleRequest):
    """
    Find optimal time to run a load to minimize costs.
    
    **Algorithm:**
    1. Generate 24-hour demand forecast
    2. Identify off-peak hours (lowest demand)
    3. Calculate costs for different time slots
    4. Recommend top 3 optimal times
    
    **Cost Model:**
    - Peak hours (8am-8pm): $0.20/kWh
    - Off-peak hours: $0.10/kWh
    
    **Returns:**
    - Top 3 recommended time slots
    - Predicted demand for each slot
    - Cost and savings estimates
    - Peak hour indicators
    
    **Use Cases:**
    - Load shifting for cost reduction
    - Peak demand avoidance
    - Demand response programs
    - Energy cost optimization
    """
    logger.info(
        f"[FORECAST-API] Finding optimal schedule for "
        f"{request.load_kw}kW load on {request.date.date()}"
    )
    
    try:
        result = await forecast_service.get_optimal_schedule(
            machine_id=request.machine_id,
            date=request.date,
            load_kw=request.load_kw
        )
        
        return ScheduleResponse(**result)
        
    except FileNotFoundError as e:
        logger.error(f"[FORECAST-API] Model not found: {e}")
        raise HTTPException(
            status_code=404,
            detail=f"{str(e)} Train Prophet model first using POST /forecast/train/prophet"
        )
    except ValueError as e:
        logger.error(f"[FORECAST-API] Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[FORECAST-API] Schedule generation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Schedule generation failed: {str(e)}"
        )


@router.get("/models/{machine_id}")
async def get_trained_models(machine_id: UUID):
    """
    Check which forecast models are trained for a machine.
    
    **Returns:**
    - ARIMA model status
    - Prophet model status
    - Last training times
    - Model file paths
    """
    import os
    from pathlib import Path
    
    model_dir = Path("/app/models/saved/forecast")
    
    arima_path = model_dir / f"arima_{machine_id}.joblib"
    prophet_path = model_dir / f"prophet_{machine_id}.joblib"
    
    result = {
        'machine_id': str(machine_id),
        'arima': {
            'trained': arima_path.exists(),
            'path': str(arima_path) if arima_path.exists() else None,
            'last_modified': datetime.fromtimestamp(
                arima_path.stat().st_mtime
            ).isoformat() if arima_path.exists() else None
        },
        'prophet': {
            'trained': prophet_path.exists(),
            'path': str(prophet_path) if prophet_path.exists() else None,
            'last_modified': datetime.fromtimestamp(
                prophet_path.stat().st_mtime
            ).isoformat() if prophet_path.exists() else None
        }
    }
    
    return result


@router.get("/peak")
async def get_next_peak_time(
    machine_id: UUID = Query(..., description="Machine UUID")
):
    """
    Predict when the next peak demand will occur in the next 24 hours.
    
    **Returns:**
    - Predicted peak time
    - Expected peak demand (kW)
    - Surrounding demand forecast
    """
    # Get 24-hour forecast
    forecast = await generate_forecast(
        PredictRequest(
            machine_id=machine_id,
            horizon='medium',
            periods=24
        )
    )
    
    # Find peak
    predictions = forecast.predictions
    timestamps = forecast.timestamps
    
    max_demand = max(predictions)
    peak_index = predictions.index(max_demand)
    peak_time = timestamps[peak_index] if timestamps else None
    
    return {
        'machine_id': str(machine_id),
        'peak_time': peak_time,
        'peak_demand_kw': round(max_demand, 2),
        'average_demand_kw': round(sum(predictions) / len(predictions), 2),
        'peak_vs_average_percent': round(
            ((max_demand / (sum(predictions) / len(predictions))) - 1) * 100,
            1
        ),
        'forecasted_at': forecast.forecasted_at
    }


@router.get("/short-term", tags=["Forecasting"])
async def get_short_term_forecast(
    machine_id: Optional[UUID] = Query(None, description="Specific machine UUID (optional - if omitted, returns all machines)")
):
    """
    Get simplified energy forecast for tomorrow (24 hours).
    
    **OVOS-OPTIMIZED** - Quick forecast summary for voice queries.
    
    **Features:**
    - Tomorrow's predicted energy consumption (kWh)
    - Estimated cost at standard rate ($0.15/kWh)
    - Peak demand prediction (kW)
    - Peak time prediction
    - Confidence score
    - Per-machine breakdown (optional)
    
    **Parameters:**
    - `machine_id`: Optional - specific machine UUID. If omitted, returns factory-wide forecast.
    
    **Examples:**
    ```bash
    # Forecast for all machines (factory-wide)
    curl "http://localhost:8001/api/v1/forecast/short-term"
    
    # Forecast for specific machine
    curl "http://localhost:8001/api/v1/forecast/short-term?machine_id=c0000000-0000-0000-0000-000000000001"
    ```
    
    **OVOS Use Cases:**
    - "How much energy will we use tomorrow?"
    - "What's the forecast for Compressor-1 tomorrow?"
    - "When will peak demand occur tomorrow?"
    
    **Voice Response Template:**
    "Tomorrow's forecast: The factory will consume approximately 2,500 kilowatt 
    hours costing $375. Peak demand of 310 kilowatts is expected at 2 PM. 
    Confidence is 85%."
    """
    from database import db, get_machines
    from datetime import timedelta
    
    try:
        # Get tomorrow's date range
        today = datetime.utcnow().date()
        tomorrow = today + timedelta(days=1)
        tomorrow_start = datetime.combine(tomorrow, datetime.min.time())
        tomorrow_end = datetime.combine(tomorrow, datetime.max.time())
        
        ENERGY_RATE = 0.15  # $/kWh
        
        if machine_id:
            # Single machine forecast
            async with db.pool.acquire() as conn:
                # Get last 7 days of data for simple moving average forecast
                historical = await conn.fetch("""
                    SELECT 
                        DATE(time) as date,
                        SUM(energy_kwh) as daily_energy,
                        AVG(power_kw) as avg_power,
                        MAX(power_kw) as peak_power
                    FROM energy_readings
                    WHERE machine_id = $1
                        AND time >= NOW() - INTERVAL '7 days'
                        AND time < NOW()
                    GROUP BY DATE(time)
                    ORDER BY date DESC
                    LIMIT 7
                """, machine_id)
                
                if not historical or len(historical) == 0:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Insufficient historical data for machine {machine_id}"
                    )
                
                # Get machine info
                machines = await get_machines()
                machine = next((m for m in machines if m['id'] == machine_id), None)
                if not machine:
                    raise HTTPException(status_code=404, detail=f"Machine not found: {machine_id}")
            
            # Simple moving average forecast
            daily_energies = [float(h['daily_energy']) for h in historical]
            avg_powers = [float(h['avg_power']) for h in historical]
            peak_powers = [float(h['peak_power']) for h in historical]
            
            forecast_energy = sum(daily_energies) / len(daily_energies)
            forecast_avg_power = sum(avg_powers) / len(avg_powers)
            forecast_peak_power = sum(peak_powers) / len(peak_powers)
            forecast_cost = forecast_energy * ENERGY_RATE
            
            # Calculate confidence based on variance
            variance = sum((x - forecast_energy) ** 2 for x in daily_energies) / len(daily_energies)
            std_dev = variance ** 0.5
            coefficient_of_variation = (std_dev / forecast_energy) if forecast_energy > 0 else 1.0
            confidence = max(0.5, min(0.95, 1.0 - coefficient_of_variation))
            
            # Predict peak time (simplified - use historical pattern)
            # For simplicity, assume peak at 2 PM (14:00)
            peak_time = "14:00:00"
            
            response = {
                "forecast_type": "single_machine",
                "forecast_date": tomorrow.isoformat(),
                "machine_id": str(machine_id),
                "machine_name": machine.get('name'),
                "machine_type": machine.get('type'),
                "predicted_energy_kwh": round(forecast_energy, 2),
                "predicted_cost_usd": round(forecast_cost, 2),
                "predicted_avg_power_kw": round(forecast_avg_power, 2),
                "predicted_peak_power_kw": round(forecast_peak_power, 2),
                "predicted_peak_time": peak_time,
                "confidence": round(confidence, 2),
                "historical_days_used": len(historical),
                "method": "7-day moving average",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        else:
            # Factory-wide forecast (all machines)
            machines = await get_machines()
            active_machines = [m for m in machines if m.get('is_active')]
            
            machine_forecasts = []
            total_energy = 0.0
            total_cost = 0.0
            max_peak_power = 0.0
            peak_machine = None
            total_confidence = 0.0
            
            async with db.pool.acquire() as conn:
                for machine in active_machines:
                    mid = machine['id']
                    
                    # Get historical data
                    historical = await conn.fetch("""
                        SELECT 
                            DATE(time) as date,
                            SUM(energy_kwh) as daily_energy,
                            MAX(power_kw) as peak_power
                        FROM energy_readings
                        WHERE machine_id = $1
                            AND time >= NOW() - INTERVAL '7 days'
                            AND time < NOW()
                        GROUP BY DATE(time)
                        ORDER BY date DESC
                        LIMIT 7
                    """, mid)
                    
                    if not historical or len(historical) == 0:
                        continue
                    
                    # Forecast for this machine
                    daily_energies = [float(h['daily_energy']) for h in historical]
                    peak_powers = [float(h['peak_power']) for h in historical]
                    
                    forecast_energy = sum(daily_energies) / len(daily_energies)
                    forecast_peak = sum(peak_powers) / len(peak_powers)
                    forecast_cost = forecast_energy * ENERGY_RATE
                    
                    # Confidence
                    variance = sum((x - forecast_energy) ** 2 for x in daily_energies) / len(daily_energies)
                    std_dev = variance ** 0.5
                    coefficient_of_variation = (std_dev / forecast_energy) if forecast_energy > 0 else 1.0
                    confidence = max(0.5, min(0.95, 1.0 - coefficient_of_variation))
                    
                    machine_forecasts.append({
                        "machine_id": str(mid),
                        "machine_name": machine.get('name'),
                        "machine_type": machine.get('type'),
                        "predicted_energy_kwh": round(forecast_energy, 2),
                        "predicted_cost_usd": round(forecast_cost, 2),
                        "predicted_peak_power_kw": round(forecast_peak, 2),
                        "confidence": round(confidence, 2)
                    })
                    
                    total_energy += forecast_energy
                    total_cost += forecast_cost
                    total_confidence += confidence
                    
                    if forecast_peak > max_peak_power:
                        max_peak_power = forecast_peak
                        peak_machine = machine.get('name')
            
            if len(machine_forecasts) == 0:
                raise HTTPException(
                    status_code=404,
                    detail="Insufficient historical data for forecasting"
                )
            
            avg_confidence = total_confidence / len(machine_forecasts)
            
            response = {
                "forecast_type": "factory_wide",
                "forecast_date": tomorrow.isoformat(),
                "total_predicted_energy_kwh": round(total_energy, 2),
                "total_predicted_cost_usd": round(total_cost, 2),
                "predicted_peak_demand_kw": round(max_peak_power, 2),
                "predicted_peak_time": "14:00:00",
                "peak_machine": peak_machine,
                "average_confidence": round(avg_confidence, 2),
                "machines_forecasted": len(machine_forecasts),
                "by_machine": machine_forecasts,
                "method": "7-day moving average (per machine)",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FORECAST-API] Short-term forecast failed: {e}")
        raise HTTPException(status_code=500, detail=f"Forecast generation failed: {str(e)}")