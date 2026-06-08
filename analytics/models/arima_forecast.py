"""
EnMS Analytics Service - ARIMA Forecasting Model
Phase 4 Session 2

Implements short-term time-series forecasting using ARIMA
(Autoregressive Integrated Moving Average) for 1-4 hour predictions.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.stattools import adfuller
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
import joblib

logger = logging.getLogger(__name__)


class ARIMAForecastModel:
    """
    ARIMA-based energy forecasting for short-term predictions.
    
    Suitable for 1-4 hour forecasts with 15-minute granularity.
    Auto-selects optimal (p, d, q) parameters based on data.
    """
    
    def __init__(
        self,
        order: Optional[Tuple[int, int, int]] = None,
        auto_order: bool = True,
        max_p: int = 5,
        max_d: int = 2,
        max_q: int = 5
    ):
        """
        Initialize ARIMA model.
        
        Args:
            order: Manual ARIMA order (p, d, q). If None, auto-detect
            auto_order: Automatically determine optimal order
            max_p: Maximum AR order to try
            max_d: Maximum differencing order to try
            max_q: Maximum MA order to try
        """
        self.order = order
        self.auto_order = auto_order
        self.max_p = max_p
        self.max_d = max_d
        self.max_q = max_q
        self.model = None
        self.model_fit = None
        self.training_history = []
        
    def check_stationarity(self, series: pd.Series) -> Dict:
        """
        Check if time series is stationary using Augmented Dickey-Fuller test.
        
        Args:
            series: Time series data
            
        Returns:
            Dict with test results
        """
        result = adfuller(series.dropna())
        
        return {
            'adf_statistic': result[0],
            'p_value': result[1],
            'critical_values': result[4],
            'is_stationary': result[1] < 0.05  # p-value < 0.05 = stationary
        }
    
    def determine_d(self, series: pd.Series) -> int:
        """
        Determine differencing order (d) needed for stationarity.
        
        Args:
            series: Time series data
            
        Returns:
            Optimal d value (0, 1, or 2)
        """
        # Check original series
        stationarity = self.check_stationarity(series)
        if stationarity['is_stationary']:
            return 0
        
        # Try first difference
        diff1 = series.diff().dropna()
        stationarity = self.check_stationarity(diff1)
        if stationarity['is_stationary']:
            return 1
        
        # Try second difference
        diff2 = diff1.diff().dropna()
        stationarity = self.check_stationarity(diff2)
        if stationarity['is_stationary']:
            return 2
        
        # Default to 1 if still not stationary
        logger.warning("Series may not be stationary even after d=2")
        return 1
    
    def auto_select_order(self, series: pd.Series) -> Tuple[int, int, int]:
        """
        Automatically select optimal ARIMA order using AIC criterion.
        
        Args:
            series: Time series data
            
        Returns:
            Optimal (p, d, q) order
        """
        logger.info("[ARIMA-AUTO] Starting auto order selection...")
        
        # Determine d
        d = self.determine_d(series)
        logger.info(f"[ARIMA-AUTO] Optimal d={d} (differencing order)")
        
        # Grid search for p and q
        best_aic = np.inf
        best_order = (0, d, 0)
        
        for p in range(self.max_p + 1):
            for q in range(self.max_q + 1):
                try:
                    model = ARIMA(series, order=(p, d, q))
                    model_fit = model.fit()
                    
                    if model_fit.aic < best_aic:
                        best_aic = model_fit.aic
                        best_order = (p, d, q)
                        logger.info(
                            f"[ARIMA-AUTO] New best: ({p},{d},{q}) "
                            f"AIC={best_aic:.2f}"
                        )
                        
                except Exception as e:
                    # Skip invalid combinations
                    continue
        
        logger.info(
            f"[ARIMA-AUTO] Selected order: {best_order} "
            f"(AIC={best_aic:.2f})"
        )
        
        return best_order
    
    def train(
        self,
        data: pd.DataFrame,
        target_column: str = 'power_kw'
    ) -> Dict:
        """
        Train ARIMA model on historical data.
        
        Args:
            data: DataFrame with datetime index and power_kw column
            target_column: Column to forecast
            
        Returns:
            Training metrics
        """
        logger.info(f"[ARIMA-TRAIN] Training on {len(data)} samples")
        
        # Ensure datetime index
        if not isinstance(data.index, pd.DatetimeIndex):
            raise ValueError("Data must have DatetimeIndex")
        
        # Extract time series
        series = data[target_column]
        
        # Remove NaN values
        series = series.dropna()
        
        if len(series) < 50:
            raise ValueError(
                f"Insufficient data: need at least 50 samples, got {len(series)}"
            )
        
        # Auto-select order if needed
        if self.auto_order and self.order is None:
            self.order = self.auto_select_order(series)
        elif self.order is None:
            self.order = (1, 1, 1)  # Default
        
        logger.info(f"[ARIMA-TRAIN] Using order: {self.order}")
        
        # Train model
        try:
            self.model = ARIMA(series, order=self.order)
            self.model_fit = self.model.fit()
            
            # Calculate metrics
            metrics = {
                'order': self.order,
                'aic': float(self.model_fit.aic),
                'bic': float(self.model_fit.bic),
                'samples': len(series),
                'trained_at': datetime.now().isoformat()
            }
            
            # In-sample predictions for validation
            predictions = self.model_fit.predict()
            residuals = series - predictions
            
            metrics['mae'] = float(np.mean(np.abs(residuals)))
            metrics['rmse'] = float(np.sqrt(np.mean(residuals**2)))
            metrics['mape'] = float(
                np.mean(np.abs(residuals / series.replace(0, np.nan))) * 100
            )
            
            logger.info(
                f"[ARIMA-TRAIN] Training complete - "
                f"AIC={metrics['aic']:.2f}, "
                f"RMSE={metrics['rmse']:.3f}, "
                f"MAPE={metrics['mape']:.2f}%"
            )
            
            self.training_history.append(metrics)
            
            return metrics
            
        except Exception as e:
            logger.error(f"[ARIMA-TRAIN] Training failed: {e}")
            raise
    
    def predict(
        self,
        steps: int = 16,
        return_conf_int: bool = True,
        alpha: float = 0.05
    ) -> Dict:
        """
        Generate forecast for future time steps.
        
        Args:
            steps: Number of steps to forecast (default 16 = 4 hours at 15min intervals)
            return_conf_int: Return confidence intervals
            alpha: Significance level for confidence intervals (default 5% = 95% CI)
            
        Returns:
            Dict with predictions and confidence intervals
        """
        if self.model_fit is None:
            raise ValueError("Model not trained. Call train() first.")
        
        logger.info(f"[ARIMA-PRED] Forecasting {steps} steps ahead")
        
        # Generate forecast
        forecast = self.model_fit.forecast(steps=steps)
        
        result = {
            'predictions': forecast.tolist(),
            'steps': steps,
            'forecasted_at': datetime.now().isoformat()
        }
        
        # Get confidence intervals
        if return_conf_int:
            forecast_obj = self.model_fit.get_forecast(steps=steps)
            conf_int = forecast_obj.conf_int(alpha=alpha)
            
            result['confidence_intervals'] = {
                'lower': conf_int.iloc[:, 0].tolist(),
                'upper': conf_int.iloc[:, 1].tolist(),
                'alpha': alpha
            }
        
        logger.info(
            f"[ARIMA-PRED] Forecast complete - "
            f"Mean={np.mean(forecast):.2f}, "
            f"Range=[{np.min(forecast):.2f}, {np.max(forecast):.2f}]"
        )
        
        return result
    
    def save(self, filepath: str):
        """Save trained model to disk."""
        if self.model_fit is None:
            raise ValueError("No trained model to save")
        
        model_data = {
            'model_fit': self.model_fit,
            'order': self.order,
            'training_history': self.training_history
        }
        
        joblib.dump(model_data, filepath)
        logger.info(f"[ARIMA-SAVE] Model saved to {filepath}")
    
    @classmethod
    def load(cls, filepath: str) -> 'ARIMAForecastModel':
        """Load trained model from disk."""
        model_data = joblib.load(filepath)
        
        instance = cls(order=model_data['order'], auto_order=False)
        instance.model_fit = model_data['model_fit']
        instance.training_history = model_data['training_history']
        
        logger.info(f"[ARIMA-LOAD] Model loaded from {filepath}")
        return instance