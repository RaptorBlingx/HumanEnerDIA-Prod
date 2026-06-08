"""
EnMS Analytics Service - Energy Baseline Model
===============================================
Multiple Linear Regression for ISO 50001-compliant energy baseline (EnB).

Author: EnMS Team
Phase: 3 - Analytics & ML
"""

from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
import joblib
import json
import logging
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)


class BaselineModel:
    """
    Energy Baseline (EnB) model using Multiple Linear Regression.
    
    Formula:
        Energy = β₀ + β₁(Production) + β₂(Temp) + β₃(Hours) + β₄(Material) + ε
    
    Features (Drivers):
        - Production count (units/hour)
        - Outdoor temperature (°C)
        - Operating hours (hours)
        - Pressure (bar)
        - Custom metadata fields
    """
    
    def __init__(self, machine_id: str, model_version: int = 1):
        """
        Initialize baseline model.
        
        Args:
            machine_id: Machine UUID
            model_version: Model version number
        """
        self.machine_id = machine_id
        self.model_version = model_version
        self.model = LinearRegression()
        self.feature_names: List[str] = []
        self.coefficients: Dict[str, float] = {}
        self.intercept: float = 0.0
        self.r_squared: float = 0.0
        self.rmse: float = 0.0
        self.mae: float = 0.0
        self.training_samples: int = 0
        self.training_start_date: Optional[datetime] = None
        self.training_end_date: Optional[datetime] = None
        self.is_trained: bool = False
        self.feature_ranges: Dict[str, Dict[str, float]] = {}  # NEW: Store min/max for validation
    
    def prepare_data(
        self,
        data: List[Dict[str, Any]],
        target_column: str = 'total_energy_kwh',
        feature_columns: Optional[List[str]] = None
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """
        Prepare training data from raw database records.
        
        Args:
            data: List of combined data records (energy + production + environmental)
            target_column: Target variable column name
            feature_columns: List of feature column names (if None, auto-select)
            
        Returns:
            Tuple of (X, y, feature_names)
        """
        # Convert to DataFrame
        df = pd.DataFrame(data)
        logger.info(f"[MODEL-PREP] DataFrame created with {len(df)} rows and {len(df.columns)} columns")
        logger.info(f"[MODEL-PREP] Column names: {list(df.columns)}")
        logger.info(f"[MODEL-PREP] First row sample: {df.iloc[0].to_dict() if len(df) > 0 else 'No data'}")
        
        # Convert all numeric columns to float (handle Decimal from PostgreSQL)
        for col in df.columns:
            if df[col].dtype == 'object':
                try:
                    df[col] = pd.to_numeric(df[col], errors='ignore')
                except:
                    pass
        
        # Auto-select features if not provided
        if feature_columns is None:
            feature_columns = [
                'total_production_count',
                'avg_outdoor_temp_c',
                'avg_pressure_bar',
                'avg_throughput_units_per_hour',
                'avg_machine_temp_c',
                'avg_load_factor'
            ]
        
        # Filter to columns that exist in the data AND have non-null values AND have variance
        available_features = []
        for col in feature_columns:
            if col in df.columns:
                # Check if column has at least some non-null values (>10% coverage)
                non_null_ratio = df[col].notna().sum() / len(df)
                if non_null_ratio < 0.1:
                    logger.warning(f"[MODEL-PREP] Feature '{col}': {non_null_ratio*100:.1f}% coverage - EXCLUDED (insufficient data)")
                    continue
                
                # Check variance - exclude constant/near-constant columns
                # First convert to numeric to handle Decimal types
                col_numeric = pd.to_numeric(df[col], errors='coerce')
                col_variance = col_numeric.var()
                col_std = col_numeric.std()
                col_mean = col_numeric.mean()
                
                # Skip if variance is near zero (constant column)
                if pd.isna(col_variance) or col_variance < 1e-10:
                    logger.warning(f"[MODEL-PREP] Feature '{col}': variance={col_variance} - EXCLUDED (near-zero variance, likely all zeros)")
                    continue
                
                # Skip if coefficient of variation is too small (less than 0.01% variation)
                if abs(col_mean) > 1e-10:
                    cv = abs(col_std / col_mean)
                    if cv < 0.0001:
                        logger.warning(f"[MODEL-PREP] Feature '{col}': CV={cv:.6f}, mean={col_mean:.2f}, std={col_std:.2f} - EXCLUDED (insufficient variation)")
                        continue
                
                available_features.append(col)
                logger.info(f"[MODEL-PREP] Feature '{col}': {non_null_ratio*100:.1f}% coverage, variance={col_variance:.4f}, std={col_std:.4f} - INCLUDED")
        
        logger.info(f"Available columns in data: {list(df.columns)}")
        logger.info(f"Requested features: {feature_columns}")
        logger.info(f"Features selected for training: {available_features}")
        
        if len(available_features) == 0:
            raise ValueError(f"No valid features found in data. Available columns: {list(df.columns)}, Requested: {feature_columns}")
        
        # Check for multicollinearity - remove highly correlated features
        if len(available_features) > 1:
            # Create temporary dataframe with just the features
            feature_df = df[available_features].apply(pd.to_numeric, errors='coerce').dropna()
            
            # Calculate correlation matrix
            corr_matrix = feature_df.corr().abs()
            
            # Find pairs with correlation > 0.95 (highly correlated)
            upper_triangle = corr_matrix.where(
                np.triu(np.ones(corr_matrix.shape), k=1).astype(bool)
            )
            
            # Features to drop
            to_drop = [column for column in upper_triangle.columns 
                      if any(upper_triangle[column] > 0.95)]
            
            if to_drop:
                logger.warning(f"[MODEL-PREP] Dropping {len(to_drop)} highly correlated features (>0.95): {to_drop}")
                available_features = [f for f in available_features if f not in to_drop]
                
                if len(available_features) == 0:
                    raise ValueError("All features are highly correlated - cannot train model")
        
        logger.info(f"[MODEL-PREP] Final features after correlation check: {available_features}")
        
        # Remove rows with missing values (only for selected features + target)
        df_clean = df[[target_column] + available_features].dropna()
        logger.info(f"[MODEL-PREP] After removing rows with missing values: {len(df_clean)} rows (removed {len(df) - len(df_clean)})")
        
        if len(df_clean) < settings.BASELINE_MIN_SAMPLES:
            raise ValueError(
                f"Insufficient samples after cleaning: {len(df_clean)} "
                f"(minimum: {settings.BASELINE_MIN_SAMPLES})"
            )
        
        # Extract features (X) and target (y)
        # Convert to float to handle Decimal types from database
        X = df_clean[available_features].astype(float).values
        y = df_clean[target_column].astype(float).values
        
        logger.info(
            f"Prepared data: {len(df_clean)} samples, "
            f"{len(available_features)} features: {available_features}"
        )
        
        return X, y, available_features
    
    def train(
        self,
        data: List[Dict[str, Any]],
        target_column: str = 'total_energy_kwh',
        feature_columns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Train the baseline model.
        
        Args:
            data: Training data records
            target_column: Target variable column name
            feature_columns: Feature column names (if None, auto-select)
            
        Returns:
            Training results dictionary
        """
        logger.info(f"Training baseline model for machine: {self.machine_id}")
        
        # Prepare data
        try:
            logger.info(f"Received {len(data)} data records for training")
            logger.info(f"Target column: {target_column}, Feature columns: {feature_columns}")
            X, y, feature_names = self.prepare_data(data, target_column, feature_columns)
            self.feature_names = feature_names
            self.training_samples = int(len(X))
            logger.info(f"Data preparation successful: {self.training_samples} samples, {len(feature_names)} features")
        except Exception as e:
            logger.error(f"Error preparing data: {e}", exc_info=True)
            raise
        
        # Extract training dates
        df = pd.DataFrame(data)
        self.training_start_date = pd.to_datetime(df['time'].min())
        self.training_end_date = pd.to_datetime(df['time'].max())
        
        # Train model
        self.model.fit(X, y)
        
        # Make predictions on training data
        y_pred = self.model.predict(X)
        
        # Calculate metrics (convert numpy types to Python natives)
        self.r_squared = float(r2_score(y, y_pred))
        self.rmse = float(np.sqrt(mean_squared_error(y, y_pred)))
        self.mae = float(mean_absolute_error(y, y_pred))
        
        # Store coefficients
        self.intercept = float(self.model.intercept_)
        self.coefficients = {
            name: float(coef) 
            for name, coef in zip(feature_names, self.model.coef_)
        }
        
        # NEW: Store feature ranges for validation
        df_features = pd.DataFrame(X, columns=feature_names)
        self.feature_ranges = {
            name: {
                'min': float(df_features[name].min()),
                'max': float(df_features[name].max()),
                'mean': float(df_features[name].mean()),
                'std': float(df_features[name].std())
            }
            for name in feature_names
        }
        
        self.is_trained = True
        
        # Validate model quality
        if self.r_squared < settings.BASELINE_MIN_R2:
            logger.warning(
                f"Model R² ({self.r_squared:.4f}) below minimum "
                f"({settings.BASELINE_MIN_R2})"
            )
        
        results = {
            'r_squared': self.r_squared,
            'rmse': self.rmse,
            'mae': self.mae,
            'training_samples': self.training_samples,
            'coefficients': self.coefficients,
            'intercept': self.intercept,
            'feature_names': feature_names,
            'training_start_date': self.training_start_date.isoformat(),
            'training_end_date': self.training_end_date.isoformat()
        }
        
        logger.info(
            f"✓ Model trained: R²={self.r_squared:.4f}, "
            f"RMSE={self.rmse:.4f}, MAE={self.mae:.4f}"
        )
        
        return results
    
    def validate_inputs(self, features: Dict[str, float]) -> List[str]:
        """
        Validate input features against training data ranges.
        
        Args:
            features: Dictionary of feature values to validate
            
        Returns:
            List of warning messages for out-of-range inputs
        """
        warnings = []
        
        # Skip validation if ranges not available (old models)
        if not hasattr(self, 'feature_ranges') or not self.feature_ranges:
            return warnings
        
        for feature_name, value in features.items():
            if feature_name not in self.feature_ranges:
                continue
            
            ranges = self.feature_ranges[feature_name]
            min_val = ranges['min']
            max_val = ranges['max']
            
            if value < min_val or value > max_val:
                warnings.append(
                    f"{feature_name}={value:.2f} is outside training range "
                    f"[{min_val:.2f}, {max_val:.2f}]. Prediction may be inaccurate."
                )
        
        return warnings
    
    def predict(self, features: Dict[str, float]) -> float:
        """
        Predict energy consumption for given features.
        
        Args:
            features: Dictionary of feature values
            
        Returns:
            Predicted energy (kWh)
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before prediction")
        
        # Create feature array in correct order
        X = np.array([[features.get(name, 0.0) for name in self.feature_names]])
        
        # Predict
        prediction = self.model.predict(X)[0]
        
        # NEW: Apply physical constraint - energy cannot be negative
        prediction = max(0.0, prediction)
        
        return float(prediction)
    
    def predict_batch(self, data: List[Dict[str, Any]]) -> np.ndarray:
        """
        Predict energy for multiple data points.
        
        Args:
            data: List of data records with features
            
        Returns:
            Array of predictions
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before prediction")
        
        # Convert to DataFrame and extract features
        df = pd.DataFrame(data)
        X = df[self.feature_names].fillna(0).values
        
        # Predict
        predictions = self.model.predict(X)
        
        return predictions
    
    def calculate_deviation(
        self,
        actual_energy: float,
        predicted_energy: float
    ) -> Tuple[float, float]:
        """
        Calculate baseline deviation.
        
        Args:
            actual_energy: Actual energy consumption (kWh)
            predicted_energy: Predicted energy consumption (kWh)
            
        Returns:
            Tuple of (deviation_kwh, deviation_percent)
        """
        deviation_kwh = float(actual_energy) - float(predicted_energy)
        
        if predicted_energy > 0:
            deviation_percent = (deviation_kwh / float(predicted_energy)) * 100
        else:
            deviation_percent = 0.0
        
        return deviation_kwh, deviation_percent
    
    def save(self, filepath: Optional[Path] = None) -> Path:
        """
        Save model to disk.
        
        Args:
            filepath: Optional custom filepath
            
        Returns:
            Path where model was saved
        """
        if filepath is None:
            filepath = Path(settings.MODEL_STORAGE_PATH) / \
                      f"baseline_{self.machine_id}_v{self.model_version}.joblib"
        
        # Ensure directory exists
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # Save model state
        model_state = {
            'machine_id': self.machine_id,
            'model_version': self.model_version,
            'sklearn_model': self.model,
            'feature_names': self.feature_names,
            'coefficients': self.coefficients,
            'intercept': self.intercept,
            'r_squared': self.r_squared,
            'rmse': self.rmse,
            'mae': self.mae,
            'training_samples': self.training_samples,
            'training_start_date': self.training_start_date.isoformat() if self.training_start_date else None,
            'training_end_date': self.training_end_date.isoformat() if self.training_end_date else None
        }
        
        joblib.dump(model_state, filepath)
        logger.info(f"✓ Model saved to: {filepath}")
        
        return filepath
    
    @classmethod
    def load(cls, filepath: Path) -> 'BaselineModel':
        """
        Load model from disk.
        
        Args:
            filepath: Path to saved model
            
        Returns:
            Loaded BaselineModel instance
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"Model file not found: {filepath}")
        
        # Load model state
        model_state = joblib.load(filepath)
        
        # Create instance
        instance = cls(
            machine_id=model_state['machine_id'],
            model_version=model_state['model_version']
        )
        
        # Restore state
        instance.model = model_state['sklearn_model']
        instance.feature_names = model_state['feature_names']
        instance.coefficients = model_state['coefficients']
        instance.intercept = model_state['intercept']
        instance.r_squared = model_state['r_squared']
        instance.rmse = model_state['rmse']
        instance.mae = model_state['mae']
        instance.training_samples = model_state['training_samples']
        instance.training_start_date = pd.to_datetime(model_state['training_start_date']) if model_state['training_start_date'] else None
        instance.training_end_date = pd.to_datetime(model_state['training_end_date']) if model_state['training_end_date'] else None
        instance.is_trained = True
        
        logger.info(f"✓ Model loaded from: {filepath}")
        
        return instance
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert model to dictionary for database storage.
        
        Returns:
            Model metadata dictionary
        """
        return {
            'machine_id': self.machine_id,
            'model_name': f'baseline_v{self.model_version}',
            'model_type': 'linear_regression',
            'model_version': self.model_version,
            'training_start_date': self.training_start_date,
            'training_end_date': self.training_end_date,
            'training_samples': self.training_samples,
            'coefficients': json.dumps(self.coefficients),  # Convert to JSON string
            'intercept': self.intercept,
            'feature_names': self.feature_names,
            'r_squared': self.r_squared,
            'rmse': self.rmse,
            'mae': self.mae,
            'is_active': True,
            'trained_by': 'analytics-service'
        }