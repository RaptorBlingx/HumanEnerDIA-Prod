"""
EnMS Analytics Service - Forecast Service
Phase 4 Session 2

Orchestrates ARIMA and Prophet models for time-series forecasting.
Handles model selection, training, prediction, and persistence.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Literal
from uuid import UUID

import pandas as pd
from database import db

from models.arima_forecast import ARIMAForecastModel
from models.prophet_forecast import ProphetForecastModel

logger = logging.getLogger(__name__)


class ForecastService:
    """
    Service layer for energy forecasting operations.
    
    Automatically selects appropriate model based on forecast horizon:
    - Short-term (1-4 hours): ARIMA
    - Medium-term (24 hours): Prophet
    - Long-term (7 days): Prophet with regressors
    """
    
    def __init__(self, model_storage_path: str = "/app/models/saved/forecast"):
        """
        Initialize forecast service.
        
        Args:
            model_storage_path: Directory to store trained models
        """
        self.model_storage_path = Path(model_storage_path)
        self.model_storage_path.mkdir(parents=True, exist_ok=True)
        
    async def fetch_training_data(
        self,
        machine_id: UUID,
        start_time: datetime,
        end_time: datetime,
        interval: str = '15 minutes'
    ) -> pd.DataFrame:
        """
        Fetch historical energy data for model training.
        
        Args:
            machine_id: Machine identifier
            start_time: Start of training period
            end_time: End of training period
            interval: Data aggregation interval
            
        Returns:
            DataFrame with timestamp and power_kw columns
        """
        logger.info(
            f"[FORECAST-SVC] Fetching training data for {machine_id} "
            f"from {start_time} to {end_time}"
        )
        
        pool = db.pool
        
        query = """
            SELECT 
                bucket AS timestamp,
                avg_power_kw AS power_kw,
                NULL AS outdoor_temp_c,
                NULL AS production_count
            FROM energy_readings_1min
            WHERE 
                machine_id = $1
                AND bucket BETWEEN $2 AND $3
            ORDER BY 1
        """
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                query,
                machine_id,
                start_time,
                end_time
            )
        
        if not rows:
            raise ValueError(
                f"No data found for machine {machine_id} "
                f"in period {start_time} to {end_time}"
            )
        
        df = pd.DataFrame(rows, columns=['timestamp', 'power_kw', 
                                         'outdoor_temp_c', 'production_count'])
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Convert numeric columns from Decimal to float
        df['power_kw'] = pd.to_numeric(df['power_kw'], errors='coerce')
        df['outdoor_temp_c'] = pd.to_numeric(df['outdoor_temp_c'], errors='coerce')
        df['production_count'] = pd.to_numeric(df['production_count'], errors='coerce')
        
        df.set_index('timestamp', inplace=True)
        
        logger.info(f"[FORECAST-SVC] Fetched {len(df)} data points")
        
        return df
    
    async def train_arima(
        self,
        machine_id: UUID,
        lookback_days: int = 14,
        auto_order: bool = True
    ) -> Dict:
        """
        Train ARIMA model for short-term forecasting.
        
        Args:
            machine_id: Machine to train for
            lookback_days: Days of historical data to use
            auto_order: Automatically determine ARIMA order
            
        Returns:
            Training results
        """
        logger.info(f"[FORECAST-SVC] Training ARIMA for machine {machine_id}")
        
        # Fetch training data
        end_time = datetime.now()
        start_time = end_time - timedelta(days=lookback_days)
        
        data = await self.fetch_training_data(
            machine_id=machine_id,
            start_time=start_time,
            end_time=end_time,
            interval='15 minutes'  # 15-minute intervals for ARIMA
        )
        
        # Train model
        model = ARIMAForecastModel(auto_order=auto_order)
        metrics = model.train(data, target_column='power_kw')
        
        # Save model
        model_path = self.model_storage_path / f"arima_{machine_id}.joblib"
        model.save(str(model_path))
        
        result = {
            'model_type': 'ARIMA',
            'machine_id': str(machine_id),
            'model_path': str(model_path),
            'training_samples': len(data),
            'lookback_days': lookback_days,
            **metrics
        }
        
        logger.info(
            f"[FORECAST-SVC] ARIMA training complete - "
            f"RMSE={metrics['rmse']:.3f}"
        )
        
        return result
    
    async def train_prophet(
        self,
        machine_id: UUID,
        lookback_days: int = 60,
        use_regressors: bool = True
    ) -> Dict:
        """
        Train Prophet model for medium/long-term forecasting.
        
        Args:
            machine_id: Machine to train for
            lookback_days: Days of historical data to use
            use_regressors: Include external regressors
            
        Returns:
            Training results
        """
        logger.info(f"[FORECAST-SVC] Training Prophet for machine {machine_id}")
        
        # Fetch training data
        end_time = datetime.now()
        start_time = end_time - timedelta(days=lookback_days)
        
        data = await self.fetch_training_data(
            machine_id=machine_id,
            start_time=start_time,
            end_time=end_time,
            interval='1 hour'  # Hourly intervals for Prophet
        )
        
        # Prepare regressors
        regressors = []
        if use_regressors:
            regressors = ['outdoor_temp_c', 'production_count']
        
        # Train model
        model = ProphetForecastModel(
            daily_seasonality=True,
            weekly_seasonality=True,
            yearly_seasonality=False,
            seasonality_mode='multiplicative',
            regressors=regressors
        )
        
        metrics = model.train(data, target_column='power_kw', add_features=True)
        
        # Save model
        model_path = self.model_storage_path / f"prophet_{machine_id}.joblib"
        model.save(str(model_path))
        
        result = {
            'model_type': 'Prophet',
            'machine_id': str(machine_id),
            'model_path': str(model_path),
            'training_samples': len(data),
            'lookback_days': lookback_days,
            'regressors': regressors + ['hour', 'day_of_week', 'is_weekend', 
                                        'is_working_hours', 'season'],
            **metrics
        }
        
        logger.info(
            f"[FORECAST-SVC] Prophet training complete - "
            f"RMSE={metrics['rmse']:.3f}, R²={metrics['r2']:.4f}"
        )
        
        return result
    
    async def predict(
        self,
        machine_id: UUID,
        horizon: Literal['short', 'medium', 'long'] = 'short',
        periods: Optional[int] = None
    ) -> Dict:
        """
        Generate energy forecast.
        
        Args:
            machine_id: Machine to forecast for
            horizon: Forecast horizon
                - 'short': 1-4 hours (ARIMA)
                - 'medium': 24 hours (Prophet)
                - 'long': 7 days (Prophet)
            periods: Number of periods (overrides defaults)
            
        Returns:
            Forecast results
        """
        logger.info(
            f"[FORECAST-SVC] Generating {horizon}-term forecast "
            f"for machine {machine_id}"
        )
        
        # Select model and parameters based on horizon
        if horizon == 'short':
            model_type = 'arima'
            default_periods = 16  # 4 hours at 15-minute intervals
            freq = '15T'
        elif horizon == 'medium':
            model_type = 'prophet'
            default_periods = 24  # 24 hours
            freq = 'H'
        elif horizon == 'long':
            model_type = 'prophet'
            default_periods = 168  # 7 days in hours
            freq = 'H'
        else:
            raise ValueError(f"Invalid horizon: {horizon}")
        
        periods = periods or default_periods
        
        # Load model
        model_path = self.model_storage_path / f"{model_type}_{machine_id}.joblib"
        
        if not model_path.exists():
            raise FileNotFoundError(
                f"No trained {model_type.upper()} model found for machine {machine_id}. "
                f"Train model first using POST /forecast/train/{model_type}"
            )
        
        # Generate predictions
        if model_type == 'arima':
            model = ARIMAForecastModel.load(str(model_path))
            predictions = model.predict(steps=periods, return_conf_int=True)
            
            result = {
                'model_type': 'ARIMA',
                'machine_id': str(machine_id),
                'horizon': horizon,
                'periods': periods,
                'frequency': freq,
                **predictions
            }
            
        else:  # prophet
            model = ProphetForecastModel.load(str(model_path))
            predictions = model.predict(periods=periods, freq=freq)
            
            result = {
                'model_type': 'Prophet',
                'machine_id': str(machine_id),
                'horizon': horizon,
                'periods': periods,
                'frequency': freq,
                **predictions
            }
        
        logger.info(
            f"[FORECAST-SVC] Forecast generated - "
            f"{periods} periods, "
            f"Mean={sum(result['predictions'])/len(result['predictions']):.2f} kW"
        )
        
        # Save predictions to database
        await self._save_forecast_to_db(
            machine_id=machine_id,
            model_type=result['model_type'],
            horizon=horizon,
            predictions=result,
            model=model
        )
        
        return result
    
    async def get_optimal_schedule(
        self,
        machine_id: UUID,
        date: datetime,
        load_kw: float
    ) -> Dict:
        """
        Suggest optimal time to run a load based on predicted demand.
        
        Args:
            machine_id: Machine to schedule for
            date: Target date
            load_kw: Load power requirement (kW)
            
        Returns:
            Optimal schedule recommendations
        """
        logger.info(
            f"[FORECAST-SVC] Finding optimal schedule for {load_kw}kW load "
            f"on {date.date()}"
        )
        
        # Get 24-hour forecast
        forecast = await self.predict(
            machine_id=machine_id,
            horizon='medium',
            periods=24
        )
        
        predictions = forecast['predictions']
        timestamps = forecast.get('timestamps', [])
        
        # Calculate peak demand times
        peak_threshold = sum(predictions) / len(predictions) * 1.2  # 20% above average
        
        # Find off-peak hours (lowest demand)
        demand_with_time = list(zip(timestamps, predictions))
        sorted_demand = sorted(demand_with_time, key=lambda x: x[1])
        
        # Top 3 off-peak recommendations
        recommendations = []
        for ts, demand in sorted_demand[:3]:
            # Calculate cost savings (peak vs off-peak tariff)
            hour = datetime.fromisoformat(ts).hour if ts else 0
            is_peak_hour = 8 <= hour < 20
            
            tariff_peak = 0.20  # $/kWh
            tariff_offpeak = 0.10  # $/kWh
            
            current_tariff = tariff_peak if is_peak_hour else tariff_offpeak
            cost = load_kw * current_tariff
            
            # Potential savings if moved to off-peak
            savings = (tariff_peak - tariff_offpeak) * load_kw if is_peak_hour else 0
            
            recommendations.append({
                'timestamp': ts,
                'predicted_demand_kw': round(demand, 2),
                'load_kw': load_kw,
                'total_demand_kw': round(demand + load_kw, 2),
                'is_peak_hour': is_peak_hour,
                'cost_usd': round(cost, 2),
                'potential_savings_usd': round(savings, 2)
            })
        
        result = {
            'machine_id': str(machine_id),
            'date': date.isoformat(),
            'load_kw': load_kw,
            'peak_demand_threshold': round(peak_threshold, 2),
            'recommendations': recommendations,
            'generated_at': datetime.now().isoformat()
        }
        
        logger.info(
            f"[FORECAST-SVC] Optimal schedule generated - "
            f"Best time: {recommendations[0]['timestamp']}"
        )
        
        return result
    
    async def _save_forecast_to_db(
        self,
        machine_id: UUID,
        model_type: str,
        horizon: str,
        predictions: Dict,
        model: any
    ):
        """
        Save forecast predictions to database for Grafana visualization.
        
        Args:
            machine_id: Machine UUID
            model_type: 'ARIMA' or 'Prophet'
            horizon: 'short', 'medium', or 'long'
            predictions: Dictionary with predictions, timestamps, confidence intervals
            model: The trained model instance for extracting metrics
        """
        try:
            pool = db.pool
            forecasted_at = datetime.now()
            
            # Prepare data for bulk insert
            values = []
            timestamps = predictions.get('timestamps', [])
            preds = predictions['predictions']
            lower_bounds = predictions.get('lower_bound', [None] * len(preds))
            upper_bounds = predictions.get('upper_bound', [None] * len(preds))
            
            # Extract model metrics
            rmse = None
            mape = None
            r2 = None
            training_samples = None
            
            if hasattr(model, 'training_history') and model.training_history:
                last_training = model.training_history[-1]
                rmse = last_training.get('rmse')
                mape = last_training.get('mape')
                r2 = last_training.get('r2')
                training_samples = last_training.get('samples')
            
            # Build rows for insertion
            for i, pred in enumerate(preds):
                forecast_time = datetime.fromisoformat(timestamps[i]) if timestamps else forecasted_at + timedelta(hours=i)
                lower = lower_bounds[i] if i < len(lower_bounds) else None
                upper = upper_bounds[i] if i < len(upper_bounds) else None
                
                values.append((
                    machine_id,
                    model_type,
                    1,  # model_version
                    horizon,
                    forecasted_at,
                    forecast_time,
                    pred,
                    lower,
                    upper,
                    0.95,  # confidence_level
                    training_samples,
                    rmse,
                    mape,
                    r2
                ))
            
            # Bulk insert
            query = """
                INSERT INTO energy_forecasts (
                    machine_id, model_type, model_version, horizon,
                    forecasted_at, forecast_time,
                    predicted_power_kw, lower_bound_kw, upper_bound_kw,
                    confidence_level, training_samples, rmse, mape, r2
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                ON CONFLICT (forecast_time, machine_id, model_type) 
                DO UPDATE SET
                    predicted_power_kw = EXCLUDED.predicted_power_kw,
                    lower_bound_kw = EXCLUDED.lower_bound_kw,
                    upper_bound_kw = EXCLUDED.upper_bound_kw,
                    forecasted_at = EXCLUDED.forecasted_at,
                    rmse = EXCLUDED.rmse,
                    mape = EXCLUDED.mape,
                    r2 = EXCLUDED.r2
            """
            
            async with pool.acquire() as conn:
                await conn.executemany(query, values)
            
            logger.info(
                f"[FORECAST-SVC] Saved {len(values)} forecast predictions to database "
                f"for machine {machine_id}"
            )
            
        except Exception as e:
            # Don't fail the forecast if DB save fails
            logger.error(f"[FORECAST-SVC] Failed to save forecast to database: {e}", exc_info=True)