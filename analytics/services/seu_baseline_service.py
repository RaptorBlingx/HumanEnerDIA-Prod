"""
EnMS Analytics Service - SEU Baseline Service
==============================================
Business logic for ISO 50001 annual baseline regression training.
Different from baseline_service.py (which is for real-time predictions).

Author: EnMS Team
Phase: 3 - Analytics & ML (ISO 50001 Extension)
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, date
from uuid import UUID
import logging
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
import json

from database import db
from models.seu import TrainBaselineRequest, TrainBaselineResponse
from services.feature_discovery import feature_discovery  # DYNAMIC ARCHITECTURE

logger = logging.getLogger(__name__)


class SEUBaselineService:
    """
    Service for managing ISO 50001 SEU baseline models.
    
    Key differences from BaselineService:
    - Trains on full year (365 days) of data
    - Uses daily aggregates (not hourly)
    - Stores coefficients in seus table (not energy_baselines)
    - Manual training trigger (not automated scheduler)
    - Purpose: Compliance reporting (not real-time anomaly detection)
    """
    
    _instance = None
    _DISALLOWED_REGRESSION_FEATURES = {
        'consumption_kwh',
        'consumption_m3',
        'consumption_kg',
        'total_energy_kwh',
        'avg_power_kw',
        'max_power_kw',
        'avg_current_a',
        'avg_voltage_v'
    }
    
    def __new__(cls):
        """Singleton pattern to reuse instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def _is_disallowed_regression_feature(cls, feature_name: str) -> bool:
        """Reject energy measurements and direct proxies as regression drivers."""
        normalized = feature_name.lower()
        return normalized.startswith('consumption_') or normalized in cls._DISALLOWED_REGRESSION_FEATURES
    
    async def train_baseline(
        self, 
        request: TrainBaselineRequest
    ) -> TrainBaselineResponse:
        """
        Train annual baseline regression for SEU.
        
        Args:
            request: Training parameters (seu_id, year, dates, features)
            
        Returns:
            Training results with formula and metrics
            
        Raises:
            ValueError: If SEU not found or insufficient data
        """
        logger.info(
            f"[SEU-TRAIN] Training baseline for SEU {request.seu_id}: "
            f"{request.start_date} to {request.end_date}"
        )
        
        # Step 1: Validate SEU exists and get details
        seu = await self._get_seu(request.seu_id)
        if not seu:
            raise ValueError(f"SEU not found: {request.seu_id}")
        
        logger.info(f"[SEU-TRAIN] SEU: {seu['name']} ({len(seu['machine_ids'])} machines)")
        
        # Step 1.5: Validate features exist for this energy source
        is_valid, valid_features, invalid_features = await feature_discovery.validate_features(
            energy_source_id=seu['energy_source_id'],
            requested_features=request.features
        )
        
        if not is_valid:
            raise ValueError(
                f"Invalid features for energy source: {invalid_features}. "
                f"Valid features: {valid_features}"
            )
        
        logger.info(f"[SEU-TRAIN] Validated features: {valid_features}")
        
        # Step 2: Fetch daily aggregated data using DYNAMIC aggregation
        logger.info(f"[SEU-TRAIN] Fetching daily aggregates for {len(request.features)} features...")
        data = await self._get_daily_aggregates(
            seu_id=request.seu_id,
            energy_source_id=seu['energy_source_id'],
            machine_ids=seu['machine_ids'],
            requested_features=request.features,
            start_date=request.start_date,
            end_date=request.end_date
        )
        
        logger.info(f"[SEU-TRAIN] Retrieved {len(data)} daily records")
        
        if len(data) < 7:
            raise ValueError(
                f"Insufficient data: {len(data)} days. "
                f"Need at least 7 days for reliable baseline."
            )
        
        # Step 3: Prepare features and target
        X, y, feature_names = self._prepare_training_data(data, request.features)
        
        if X.shape[0] == 0:
            raise ValueError("No valid training samples after filtering")
        
        logger.info(f"[SEU-TRAIN] Training samples: {X.shape[0]}, Features: {feature_names}")
        
        # Step 4: Train linear regression
        model = LinearRegression()
        model.fit(X, y)
        
        # Step 5: Calculate metrics
        y_pred = model.predict(X)
        r2 = r2_score(y, y_pred)
        rmse = np.sqrt(mean_squared_error(y, y_pred))
        mae = mean_absolute_error(y, y_pred)
        
        logger.info(
            f"[SEU-TRAIN] Model trained: R²={r2:.4f}, RMSE={rmse:.2f}, MAE={mae:.2f}"
        )
        
        # Step 6: Store baseline in database
        coefficients = {
            feature_names[i]: float(model.coef_[i]) 
            for i in range(len(feature_names))
        }
        
        await self._save_baseline(
            seu_id=request.seu_id,
            baseline_year=request.baseline_year,
            start_date=request.start_date,
            end_date=request.end_date,
            coefficients=coefficients,
            intercept=float(model.intercept_),
            feature_columns=feature_names,
            r_squared=r2,
            rmse=rmse,
            mae=mae,
            samples_count=X.shape[0]
        )
        
        # Step 7: Build formula string
        formula = self._build_formula_string(coefficients, model.intercept_)
        
        return TrainBaselineResponse(
            success=True,
            seu_id=request.seu_id,
            seu_name=seu['name'],
            baseline_year=request.baseline_year,
            training_period=f"{request.start_date} to {request.end_date}",
            samples_count=X.shape[0],
            r_squared=round(r2, 4),
            rmse=round(rmse, 2),
            mae=round(mae, 2),
            coefficients=coefficients,
            intercept=round(float(model.intercept_), 4),
            formula=formula,
            trained_at=datetime.utcnow()
        )
    
    async def _get_seu(self, seu_id: UUID) -> Optional[Dict[str, Any]]:
        """Get SEU details from database."""
        query = """
            SELECT 
                s.id,
                s.name,
                s.machine_ids,
                s.energy_source_id,
                es.name as energy_source_name,
                es.unit as energy_unit
            FROM seus s
            JOIN energy_sources es ON s.energy_source_id = es.id
            WHERE s.id = $1
        """
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, seu_id)
            return dict(row) if row else None
    
    async def _get_daily_aggregates(
        self,
        seu_id: UUID,
        energy_source_id: UUID,
        machine_ids: List[UUID],
        requested_features: List[str],
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """
        Get daily aggregated data for SEU using DYNAMIC feature discovery.
        
        NO HARDCODED SQL. Query built dynamically based on energy_source_features table.
        Works for electricity, natural_gas, steam, compressed_air - ANY energy source!
        
        Args:
            seu_id: SEU UUID
            energy_source_id: Energy source UUID (electricity, natural_gas, etc.)
            machine_ids: List of machine UUIDs in this SEU
            requested_features: Features to aggregate (e.g., ['consumption_kwh', 'production_count'])
            start_date: Start date
            end_date: End date
        
        Returns:
            List of dicts with daily aggregated data
        """
        # Build dynamic query using feature discovery
        query = await feature_discovery.build_daily_aggregation_query(
            energy_source_id=energy_source_id,
            machine_ids=machine_ids,
            requested_features=requested_features,
            start_date=str(start_date),
            end_date=str(end_date)
        )
        
        logger.info(
            f"[SEU-TRAIN] Executing dynamic aggregation for {len(requested_features)} features"
        )
        logger.debug(f"[SEU-TRAIN] Generated SQL: {query[:1000]}")
        logger.debug(f"[SEU-TRAIN] Parameters: machine_ids={machine_ids}, start_date={start_date}, end_date={end_date}")
        
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query, machine_ids, start_date, end_date)
            return [dict(row) for row in rows]
    
    def _prepare_training_data(
        self,
        data: List[Dict[str, Any]],
        requested_features: List[str]
    ) -> tuple:
        """
        Prepare feature matrix X and target vector y.
        
        DYNAMIC: No hardcoded feature mappings! Uses actual column names from data.
        
        Args:
            data: Daily aggregated records (from _get_daily_aggregates)
            requested_features: Feature names requested by user
            
        Returns:
            (X: np.ndarray, y: np.ndarray, feature_names: List[str])
        """
        if not data:
            raise ValueError("No data provided for training")
        
        # Get first record to see what columns are available
        sample = data[0]
        available_columns = set(sample.keys())
        
        logger.info(f"[SEU-TRAIN] Available columns in data: {sorted(available_columns)}")

        safe_requested_features = []
        excluded_features = []
        for feature in requested_features:
            if self._is_disallowed_regression_feature(feature):
                excluded_features.append(feature)
            else:
                safe_requested_features.append(feature)

        if excluded_features:
            logger.warning(
                f"[SEU-TRAIN] Excluding non-driver features from regression input: {excluded_features}"
            )
        
        # Determine which requested features are actually in the data
        # Note: Some features might have been renamed during aggregation
        # (e.g., 'consumption_kwh' might be stored as 'consumption_kwh')
        feature_names = []
        for feature in safe_requested_features:
            if feature in available_columns:
                feature_names.append(feature)
            else:
                # Try common variations
                for col in available_columns:
                    if feature.lower() in col.lower() or col.lower() in feature.lower():
                        feature_names.append(col)
                        logger.info(f"[SEU-TRAIN] Mapped '{feature}' → '{col}'")
                        break

        feature_names = [
            feature_name
            for feature_name in feature_names
            if not self._is_disallowed_regression_feature(feature_name)
        ]
        
        if not feature_names:
            raise ValueError(
                "No valid regression drivers found after excluding energy measurement "
                f"features. Requested: {requested_features}. Available columns: {sorted(available_columns)}"
            )
        
        logger.info(f"[SEU-TRAIN] Using features: {feature_names}")
        
        # Identify energy/consumption column (target variable)
        energy_column = None
        for col in ['consumption_kwh', 'consumption_m3', 'consumption_kg', 'total_energy_kwh']:
            if col in available_columns:
                energy_column = col
                break
        
        if not energy_column:
            raise ValueError(f"No energy/consumption column found in data. Available: {sorted(available_columns)}")
        
        logger.info(f"[SEU-TRAIN] Target variable (y): {energy_column}")
        
        # Extract feature values and target
        X_list = []
        y_list = []
        
        for record in data:
            # Skip records with missing values
            if any(record.get(f) is None for f in feature_names):
                continue
            
            if record.get(energy_column) is None or record[energy_column] <= 0:
                continue
            
            feature_values = [float(record[f]) for f in feature_names]
            energy_value = float(record[energy_column])
            
            X_list.append(feature_values)
            y_list.append(energy_value)
        
        if len(X_list) == 0:
            raise ValueError("No valid training samples after filtering missing values")
        
        X = np.array(X_list)
        y = np.array(y_list)
        
        logger.info(f"[SEU-TRAIN] Training matrix: X shape={X.shape}, y shape={y.shape}")
        
        return X, y, feature_names
        
        if not feature_names:
            raise ValueError(
                f"None of requested features {requested_features} found in data. "
                f"Available: {list(data[0].keys())}"
            )
        
        # Extract feature values
        for record in data:
            # Skip records with missing values
            if any(record.get(f) is None for f in feature_names):
                continue
            
            feature_values = [float(record[f]) for f in feature_names]
            energy_value = float(record['total_energy_kwh'])
            
            X_list.append(feature_values)
            y_list.append(energy_value)
        
        X = np.array(X_list)
        y = np.array(y_list)
        
        logger.info(
            f"[SEU-TRAIN] Prepared data: {X.shape[0]} samples, "
            f"{X.shape[1]} features ({', '.join(feature_names)})"
        )
        
        return X, y, feature_names
    
    async def _save_baseline(
        self,
        seu_id: UUID,
        baseline_year: int,
        start_date: date,
        end_date: date,
        coefficients: Dict[str, float],
        intercept: float,
        feature_columns: List[str],
        r_squared: float,
        rmse: float,
        mae: float,
        samples_count: int
    ):
        """Save baseline model to seus table."""
        query = """
            UPDATE seus
            SET 
                baseline_year = $2,
                baseline_start_date = $3,
                baseline_end_date = $4,
                regression_coefficients = $5::jsonb,
                intercept = $6,
                feature_columns = $7,
                r_squared = $8,
                rmse = $9,
                mae = $10,
                trained_at = NOW(),
                trained_by = 'analytics-service',
                updated_at = NOW()
            WHERE id = $1
        """
        
        async with db.pool.acquire() as conn:
            await conn.execute(
                query,
                seu_id,
                baseline_year,
                start_date,
                end_date,
                json.dumps(coefficients),
                intercept,
                feature_columns,
                r_squared,
                rmse,
                mae
            )
        
        logger.info(
            f"[SEU-TRAIN] Baseline saved to database: SEU {seu_id}, "
            f"Year {baseline_year}, R²={r_squared:.4f}"
        )
    
    def _build_formula_string(
        self,
        coefficients: Dict[str, float],
        intercept: float
    ) -> str:
        """
        Build human-readable formula string.
        Example: "Energy = 45.2 + 0.00003×production + 0.5×temp"
        """
        terms = [f"{intercept:.4f}"]
        
        for feature, coef in coefficients.items():
            # Clean up feature name for display
            display_name = feature.replace('avg_', '').replace('_', ' ')
            
            if coef >= 0:
                terms.append(f"+ {coef:.6f}×{display_name}")
            else:
                terms.append(f"- {abs(coef):.6f}×{display_name}")
        
        return f"Energy (kWh) = {' '.join(terms)}"
    
    async def get_seu_baseline(self, seu_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get active baseline for SEU.
        
        Args:
            seu_id: SEU identifier
            
        Returns:
            Baseline data or None if not trained
        """
        query = """
            SELECT 
                id,
                name,
                baseline_year,
                baseline_start_date,
                baseline_end_date,
                regression_coefficients,
                intercept,
                feature_columns,
                r_squared,
                rmse,
                mae,
                trained_at
            FROM seus
            WHERE id = $1
              AND baseline_year IS NOT NULL
        """
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, seu_id)
            
            if row:
                result = dict(row)
                # Parse JSON coefficients
                if result['regression_coefficients']:
                    result['regression_coefficients'] = json.loads(
                        result['regression_coefficients']
                    )
                return result
            
            return None
    
    async def calculate_expected_consumption(
        self,
        seu_id: UUID,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Calculate expected energy consumption based on baseline formula.
        
        Args:
            seu_id: SEU identifier
            period_start: Start of comparison period
            period_end: End of comparison period
            
        Returns:
            Expected energy consumption (kWh)
            
        Raises:
            ValueError: If baseline not trained
        """
        # Get baseline formula
        baseline = await self.get_seu_baseline(seu_id)
        if not baseline:
            raise ValueError(f"No baseline trained for SEU {seu_id}")
        
        # Get SEU details
        seu_query = """
            SELECT energy_source_id, machine_ids
            FROM seus
            WHERE id = $1
        """
        async with db.pool.acquire() as conn:
            seu_row = await conn.fetchrow(seu_query, seu_id)
        
        if not seu_row:
            raise ValueError(f"SEU not found: {seu_id}")
        
        energy_source_id = seu_row['energy_source_id']
        machine_ids = seu_row['machine_ids']
        feature_columns = baseline['feature_columns']
        
        # Get actual conditions for the comparison period
        data = await self._get_daily_aggregates(
            seu_id=seu_id,
            energy_source_id=energy_source_id,
            machine_ids=machine_ids,
            requested_features=feature_columns,
            start_date=period_start,
            end_date=period_end
        )
        
        if not data:
            raise ValueError(f"No data available for period {period_start} to {period_end}")
        
        coefficients = baseline['regression_coefficients']
        intercept = baseline['intercept']
        
        # Calculate expected for each day
        total_expected = 0.0
        
        for record in data:
            expected_daily = float(intercept)
            
            for feature in feature_columns:
                if feature in record and record[feature] is not None:
                    expected_daily += float(coefficients[feature]) * float(record[feature])
            
            total_expected += expected_daily
        
        logger.info(
            f"[SEU-EXPECTED] Calculated expected consumption: {total_expected:.2f} kWh "
            f"for {len(data)} days"
        )
        
        return total_expected


# Global singleton instance
seu_baseline_service = SEUBaselineService()
