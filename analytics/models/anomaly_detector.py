"""
EnMS Analytics Service - Anomaly Detector
==========================================
Isolation Forest for real-time fault detection.

Author: EnMS Team
Phase: 3 - Analytics & ML
"""

from sklearn.ensemble import IsolationForest
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
import logging

from config import settings

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """
    Anomaly detector using Isolation Forest algorithm.
    
    Detection Targets:
        - Power deviation from baseline
        - Pressure anomalies
        - Temperature spikes
        - Efficiency drops
        - Unusual consumption patterns
    
    Thresholds:
        - Warning: 2σ deviation
        - Critical: 3σ deviation
    """
    
    def __init__(self, contamination: float = None):
        """
        Initialize anomaly detector.
        
        Args:
            contamination: Expected proportion of anomalies (default from config)
        """
        if contamination is None:
            contamination = settings.ANOMALY_CONTAMINATION
        
        self.contamination = contamination
        self.model = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=100
        )
        self.is_fitted = False
        self.feature_names: List[str] = []
        self.feature_means: Dict[str, float] = {}
        self.feature_stds: Dict[str, float] = {}
    
    def prepare_features(
        self,
        data: List[Dict[str, Any]],
        baseline_predictions: Optional[np.ndarray] = None
    ) -> Tuple[np.ndarray, List[str]]:
        """
        Prepare features for anomaly detection.
        
        Args:
            data: List of data records
            baseline_predictions: Optional baseline predictions for deviation features
            
        Returns:
            Tuple of (feature_matrix, feature_names)
        """
        df = pd.DataFrame(data)
        
        # Select relevant features
        feature_columns = []
        
        # Power features
        if 'avg_power_kw' in df.columns:
            feature_columns.append('avg_power_kw')
        
        # Temperature features
        if 'avg_outdoor_temp_c' in df.columns:
            feature_columns.append('avg_outdoor_temp_c')
        if 'avg_machine_temp_c' in df.columns:
            feature_columns.append('avg_machine_temp_c')
        
        # Pressure features
        if 'avg_pressure_bar' in df.columns:
            feature_columns.append('avg_pressure_bar')
        
        # Production features
        if 'avg_throughput_units_per_hour' in df.columns:
            feature_columns.append('avg_throughput_units_per_hour')
        
        # Add baseline deviation if predictions provided
        if baseline_predictions is not None and 'total_energy_kwh' in df.columns:
            df['baseline_deviation'] = df['total_energy_kwh'].astype(float) - baseline_predictions
            feature_columns.append('baseline_deviation')
        
        # Extract features
        if not feature_columns:
            raise ValueError("No valid features found for anomaly detection")
        
        X = df[feature_columns].fillna(0).values
        
        logger.info(f"Prepared features for anomaly detection: {feature_columns}")
        
        return X, feature_columns
    
    def fit(
        self,
        data: List[Dict[str, Any]],
        baseline_predictions: Optional[np.ndarray] = None
    ):
        """
        Fit the anomaly detector on normal data.
        
        Args:
            data: List of normal data records (historical baseline)
            baseline_predictions: Optional baseline predictions
        """
        X, feature_names = self.prepare_features(data, baseline_predictions)
        self.feature_names = feature_names
        
        # Calculate statistics for severity assessment
        df_features = pd.DataFrame(X, columns=feature_names)
        self.feature_means = df_features.mean().to_dict()
        self.feature_stds = df_features.std().to_dict()
        
        # Fit model
        self.model.fit(X)
        self.is_fitted = True
        
        logger.info(f"✓ Anomaly detector fitted on {len(X)} samples")
    
    def detect(
        self,
        data: List[Dict[str, Any]],
        baseline_predictions: Optional[np.ndarray] = None
    ) -> List[Dict[str, Any]]:
        """
        Detect anomalies in new data.
        
        Args:
            data: List of data records to check
            baseline_predictions: Optional baseline predictions
            
        Returns:
            List of detected anomalies
        """
        if not self.is_fitted:
            # If not fitted, use unsupervised detection without training
            logger.warning("Detector not fitted, using unsupervised mode")
            X, feature_names = self.prepare_features(data, baseline_predictions)
            self.feature_names = feature_names
            
            # Quick fit on current data
            self.model.fit(X)
            predictions = self.model.predict(X)
            scores = self.model.score_samples(X)
        else:
            X, _ = self.prepare_features(data, baseline_predictions)
            predictions = self.model.predict(X)
            scores = self.model.score_samples(X)
        
        # Identify anomalies
        anomalies = []
        df = pd.DataFrame(data)
        
        for i, (pred, score) in enumerate(zip(predictions, scores)):
            if pred == -1:  # Anomaly detected
                record = data[i]
                
                # Determine anomaly type and severity
                anomaly_info = self._analyze_anomaly(
                    record=record,
                    features=X[i],
                    score=score
                )
                
                anomalies.append(anomaly_info)
        
        logger.info(f"Detected {len(anomalies)} anomalies in {len(data)} records")
        
        return anomalies
    
    def _analyze_anomaly(
        self,
        record: Dict[str, Any],
        features: np.ndarray,
        score: float
    ) -> Dict[str, Any]:
        """
        Analyze an anomaly to determine type and severity.
        
        Args:
            record: Original data record
            features: Feature vector
            score: Anomaly score
            
        Returns:
            Anomaly information dictionary
        """
        # Find the most deviant feature
        max_deviation = 0
        anomaly_type = "unknown"
        metric_name = None
        metric_value = None
        expected_value = None
        
        for i, feature_name in enumerate(self.feature_names):
            feature_value = features[i]
            
            if feature_name in self.feature_means and feature_name in self.feature_stds:
                mean = self.feature_means[feature_name]
                std = self.feature_stds[feature_name]
                
                if std > 0:
                    deviation = abs((feature_value - mean) / std)
                    
                    if deviation > max_deviation:
                        max_deviation = deviation
                        metric_name = feature_name
                        metric_value = feature_value
                        expected_value = mean
        
        # Classify anomaly type based on metric
        if metric_name:
            if 'power' in metric_name:
                anomaly_type = 'power_anomaly'
            elif 'temp' in metric_name:
                anomaly_type = 'temperature_anomaly'
            elif 'pressure' in metric_name:
                anomaly_type = 'pressure_anomaly'
            elif 'deviation' in metric_name:
                anomaly_type = 'baseline_deviation'
            elif 'throughput' in metric_name:
                anomaly_type = 'production_anomaly'
        
        # Determine severity based on deviation magnitude
        if max_deviation >= settings.ANOMALY_CRITICAL_THRESHOLD:
            severity = 'critical'
        elif max_deviation >= settings.ANOMALY_WARNING_THRESHOLD:
            severity = 'warning'
        else:
            severity = 'normal'  # Changed from 'info' to match database enum
        
        # Calculate deviation percentage
        deviation_percent = 0
        if expected_value and expected_value != 0:
            deviation_percent = ((metric_value - expected_value) / expected_value) * 100
        
        # Confidence score (normalized anomaly score)
        confidence = min(1.0, max(0.0, abs(score) / 10))  # Normalize to 0-1
        
        return {
            'detected_at': record.get('time', datetime.utcnow()),
            'anomaly_type': anomaly_type,
            'severity': severity,
            'metric_name': metric_name,
            'metric_value': float(metric_value) if metric_value is not None else None,
            'expected_value': float(expected_value) if expected_value is not None else None,
            'deviation_percent': round(deviation_percent, 2),
            'deviation_std_dev': round(max_deviation, 2),
            'detection_method': 'isolation_forest',
            'confidence_score': round(confidence, 4)
        }
    
    def get_anomaly_score(self, features: np.ndarray) -> float:
        """
        Get anomaly score for a single data point.
        
        Args:
            features: Feature vector
            
        Returns:
            Anomaly score (lower = more anomalous)
        """
        if not self.is_fitted:
            raise ValueError("Detector must be fitted before scoring")
        
        score = self.model.score_samples([features])[0]
        return float(score)