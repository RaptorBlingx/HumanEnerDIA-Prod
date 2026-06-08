"""
EnMS Analytics Service - Prophet Forecasting Model
Phase 4 Session 2

Implements medium to long-term forecasting using Facebook Prophet
with external regressors for seasonality and trend detection.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from prophet import Prophet
import joblib

logger = logging.getLogger(__name__)


class ProphetForecastModel:
    """
    Prophet-based energy forecasting for medium/long-term predictions.
    
    Suitable for 24-hour to 7-day forecasts with hourly granularity.
    Supports external regressors: temperature, production, day of week.
    """
    
    def __init__(
        self,
        daily_seasonality: bool = True,
        weekly_seasonality: bool = True,
        yearly_seasonality: bool = False,
        seasonality_mode: str = 'multiplicative',
        changepoint_prior_scale: float = 0.05,
        regressors: Optional[List[str]] = None
    ):
        """
        Initialize Prophet model.
        
        Args:
            daily_seasonality: Enable daily patterns
            weekly_seasonality: Enable weekly patterns
            yearly_seasonality: Enable yearly patterns
            seasonality_mode: 'additive' or 'multiplicative'
            changepoint_prior_scale: Flexibility of trend changes (0.001-0.5)
            regressors: List of external regressor column names
        """
        self.daily_seasonality = daily_seasonality
        self.weekly_seasonality = weekly_seasonality
        self.yearly_seasonality = yearly_seasonality
        self.seasonality_mode = seasonality_mode
        self.changepoint_prior_scale = changepoint_prior_scale
        self.regressors = regressors or []
        
        self.model = None
        self.training_history = []
        
    def prepare_data(
        self,
        data: pd.DataFrame,
        target_column: str = 'power_kw',
        time_column: str = 'timestamp'
    ) -> pd.DataFrame:
        """
        Prepare data in Prophet format.
        
        Prophet requires columns: 'ds' (datetime) and 'y' (target).
        
        Args:
            data: Input DataFrame
            target_column: Column to forecast
            time_column: Datetime column name
            
        Returns:
            DataFrame in Prophet format
        """
        df = data.copy()
        
        # Rename columns for Prophet
        if time_column in df.columns:
            df['ds'] = pd.to_datetime(df[time_column])
        elif isinstance(df.index, pd.DatetimeIndex):
            df['ds'] = df.index
        else:
            raise ValueError("No datetime column found")
        
        # Remove timezone - Prophet doesn't support timezone-aware timestamps
        if df['ds'].dt.tz is not None:
            df['ds'] = df['ds'].dt.tz_localize(None)
        
        df['y'] = df[target_column]
        
        # Filter regressors that actually exist and have data
        valid_regressors = []
        for reg in self.regressors:
            if reg in df.columns and df[reg].notna().any():
                valid_regressors.append(reg)
            else:
                logger.warning(
                    f"[PROPHET-PREP] Regressor '{reg}' has no data, excluding"
                )
        
        # Update regressors list with only valid ones
        self.regressors = valid_regressors
        
        # Keep valid columns only
        columns_to_keep = ['ds', 'y'] + valid_regressors
        df = df[columns_to_keep]
        
        # Remove NaN values in target column only
        # (regressors can have NaNs, we'll handle those separately)
        df = df.dropna(subset=['ds', 'y'])
        
        return df
    
    def add_engineered_features(
        self,
        df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Add engineered time-based features as regressors.
        
        Args:
            df: DataFrame with 'ds' column
            
        Returns:
            DataFrame with additional features
        """
        df = df.copy()
        
        # Hour of day (0-23)
        df['hour'] = df['ds'].dt.hour
        
        # Day of week (0=Monday, 6=Sunday)
        df['day_of_week'] = df['ds'].dt.dayofweek
        
        # Is weekend (0 or 1)
        df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
        
        # Is working hours (8-18)
        df['is_working_hours'] = (
            (df['hour'] >= 8) & (df['hour'] < 18)
        ).astype(int)
        
        # Season (simple quarterly)
        df['season'] = df['ds'].dt.quarter
        
        return df
    
    def train(
        self,
        data: pd.DataFrame,
        target_column: str = 'power_kw',
        add_features: bool = True
    ) -> Dict:
        """
        Train Prophet model on historical data.
        
        Args:
            data: DataFrame with datetime and target columns
            target_column: Column to forecast
            add_features: Auto-generate time-based features
            
        Returns:
            Training metrics
        """
        logger.info(f"[PROPHET-TRAIN] Training on {len(data)} samples")
        
        # Prepare data
        df = self.prepare_data(data, target_column=target_column)
        
        if len(df) < 100:
            raise ValueError(
                f"Insufficient data: need at least 100 samples, got {len(df)}"
            )
        
        # Add engineered features
        if add_features:
            df = self.add_engineered_features(df)
            # Add to regressors if not already there
            new_regressors = ['hour', 'day_of_week', 'is_weekend', 
                             'is_working_hours', 'season']
            for reg in new_regressors:
                if reg not in self.regressors:
                    self.regressors.append(reg)
        
        logger.info(f"[PROPHET-TRAIN] Using regressors: {self.regressors}")
        
        # Initialize Prophet model
        self.model = Prophet(
            daily_seasonality=self.daily_seasonality,
            weekly_seasonality=self.weekly_seasonality,
            yearly_seasonality=self.yearly_seasonality,
            seasonality_mode=self.seasonality_mode,
            changepoint_prior_scale=self.changepoint_prior_scale
        )
        
        # Add regressors
        for regressor in self.regressors:
            if regressor in df.columns:
                self.model.add_regressor(regressor)
            else:
                logger.warning(
                    f"[PROPHET-TRAIN] Regressor '{regressor}' not in data, skipping"
                )
        
        # Train model
        try:
            self.model.fit(df)
            
            # Calculate metrics
            # Make in-sample predictions
            predictions = self.model.predict(df)
            
            residuals = df['y'].values - predictions['yhat'].values
            
            metrics = {
                'samples': len(df),
                'regressors': self.regressors,
                'mae': float(np.mean(np.abs(residuals))),
                'rmse': float(np.sqrt(np.mean(residuals**2))),
                'mape': float(
                    np.mean(np.abs(residuals / df['y'].replace(0, np.nan))) * 100
                ),
                'r2': float(1 - (np.sum(residuals**2) / 
                                np.sum((df['y'] - df['y'].mean())**2))),
                'trained_at': datetime.now().isoformat()
            }
            
            logger.info(
                f"[PROPHET-TRAIN] Training complete - "
                f"RMSE={metrics['rmse']:.3f}, "
                f"MAPE={metrics['mape']:.2f}%, "
                f"R²={metrics['r2']:.4f}"
            )
            
            self.training_history.append(metrics)
            
            return metrics
            
        except Exception as e:
            logger.error(f"[PROPHET-TRAIN] Training failed: {e}")
            raise
    
    def predict(
        self,
        periods: int = 24,
        freq: str = 'H',
        future_regressors: Optional[pd.DataFrame] = None
    ) -> Dict:
        """
        Generate forecast for future periods.
        
        Args:
            periods: Number of periods to forecast
            freq: Frequency string ('H'=hourly, '15T'=15min, 'D'=daily)
            future_regressors: DataFrame with future regressor values
            
        Returns:
            Dict with predictions and components
        """
        if self.model is None:
            raise ValueError("Model not trained. Call train() first.")
        
        logger.info(f"[PROPHET-PRED] Forecasting {periods} periods at {freq} frequency")
        
        # Create future dataframe
        future = self.model.make_future_dataframe(periods=periods, freq=freq)
        
        # Remove timezone if present
        if future['ds'].dt.tz is not None:
            future['ds'] = future['ds'].dt.tz_localize(None)
        
        # Add regressors to future
        if future_regressors is not None:
            # Merge provided regressors
            future = future.merge(future_regressors, on='ds', how='left')
        else:
            # Generate features automatically
            future = self.add_engineered_features(future)
        
        # Ensure all regressors are present
        for reg in self.regressors:
            if reg not in future.columns:
                logger.warning(
                    f"[PROPHET-PRED] Regressor '{reg}' missing, using zeros"
                )
                future[reg] = 0
        
        # Generate forecast
        forecast = self.model.predict(future)
        
        # Extract only future predictions (not historical)
        future_forecast = forecast.tail(periods)
        
        result = {
            'predictions': future_forecast['yhat'].tolist(),
            'lower_bound': future_forecast['yhat_lower'].tolist(),
            'upper_bound': future_forecast['yhat_upper'].tolist(),
            'timestamps': future_forecast['ds'].dt.strftime('%Y-%m-%d %H:%M:%S').tolist(),
            'periods': periods,
            'frequency': freq,
            'forecasted_at': datetime.now().isoformat()
        }
        
        # Add component breakdowns (trend, seasonality)
        if 'trend' in future_forecast.columns:
            result['trend'] = future_forecast['trend'].tolist()
        
        if 'daily' in future_forecast.columns:
            result['daily_seasonality'] = future_forecast['daily'].tolist()
        
        if 'weekly' in future_forecast.columns:
            result['weekly_seasonality'] = future_forecast['weekly'].tolist()
        
        logger.info(
            f"[PROPHET-PRED] Forecast complete - "
            f"Mean={np.mean(result['predictions']):.2f}, "
            f"Range=[{np.min(result['predictions']):.2f}, "
            f"{np.max(result['predictions']):.2f}]"
        )
        
        return result
    
    def plot_components(self) -> None:
        """Plot forecast components (trend, seasonality)."""
        if self.model is None:
            raise ValueError("Model not trained")
        
        # This would typically create plots showing:
        # - Overall trend
        # - Daily seasonality
        # - Weekly seasonality
        # For now, just log
        logger.info("[PROPHET-PLOT] Component plots available via Prophet.plot_components()")
    
    def save(self, filepath: str):
        """Save trained model to disk."""
        if self.model is None:
            raise ValueError("No trained model to save")
        
        model_data = {
            'model': self.model,
            'regressors': self.regressors,
            'training_history': self.training_history,
            'config': {
                'daily_seasonality': self.daily_seasonality,
                'weekly_seasonality': self.weekly_seasonality,
                'yearly_seasonality': self.yearly_seasonality,
                'seasonality_mode': self.seasonality_mode,
                'changepoint_prior_scale': self.changepoint_prior_scale
            }
        }
        
        joblib.dump(model_data, filepath)
        logger.info(f"[PROPHET-SAVE] Model saved to {filepath}")
    
    @classmethod
    def load(cls, filepath: str) -> 'ProphetForecastModel':
        """Load trained model from disk."""
        model_data = joblib.load(filepath)
        
        config = model_data['config']
        instance = cls(
            daily_seasonality=config['daily_seasonality'],
            weekly_seasonality=config['weekly_seasonality'],
            yearly_seasonality=config['yearly_seasonality'],
            seasonality_mode=config['seasonality_mode'],
            changepoint_prior_scale=config['changepoint_prior_scale'],
            regressors=model_data['regressors']
        )
        
        instance.model = model_data['model']
        instance.training_history = model_data['training_history']
        
        logger.info(f"[PROPHET-LOAD] Model loaded from {filepath}")
        return instance