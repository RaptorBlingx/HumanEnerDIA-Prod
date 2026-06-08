"""
Model Explainer Service
Provides natural language explanations of baseline models for OVOS voice integration.
"""
import json
from typing import Dict, List, Any, Tuple
import logging

logger = logging.getLogger(__name__)


class ModelExplainer:
    """
    Service for generating natural language explanations of baseline models.
    Used by /baseline/model/{id} and /baseline/models endpoints.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def explain_model(self, model_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate comprehensive natural language explanation of a baseline model.
        
        Args:
            model_data: Model data from database (coefficients, r_squared, etc.)
            
        Returns:
            Dict with explanation fields
        """
        try:
            # Parse coefficients if stored as JSON string
            coefficients = model_data.get('coefficients')
            if isinstance(coefficients, str):
                coefficients = json.loads(coefficients)
            elif coefficients is None:
                coefficients = {}
            
            feature_names = model_data.get('feature_names', [])
            r_squared = model_data.get('r_squared', 0)
            intercept = model_data.get('intercept', 0)
            
            # Generate explanations
            accuracy_explanation = self._interpret_r_squared(r_squared)
            key_drivers = self._analyze_key_drivers(coefficients, feature_names)
            formula_explanation = self._explain_coefficients(
                coefficients, intercept, feature_names
            )
            impact_summary = self._summarize_impacts(coefficients, feature_names)
            
            return {
                "accuracy_explanation": accuracy_explanation,
                "key_drivers": key_drivers,
                "formula_explanation": formula_explanation,
                "impact_summary": impact_summary,
                "voice_summary": self._generate_voice_summary(
                    r_squared, key_drivers, model_data
                )
            }
        
        except Exception as e:
            self.logger.error(f"Error explaining model: {e}", exc_info=True)
            return {
                "accuracy_explanation": "Unable to generate explanation",
                "key_drivers": [],
                "formula_explanation": "Error parsing model data",
                "impact_summary": {},
                "voice_summary": "Model explanation unavailable"
            }
    
    def _interpret_r_squared(self, r_squared: float) -> str:
        """
        Convert R² value to natural language accuracy description.
        
        Args:
            r_squared: R² value (0-1)
            
        Returns:
            Natural language description
        """
        percentage = r_squared * 100
        
        if r_squared >= 0.95:
            quality = "excellent"
            reliability = "extremely reliable"
        elif r_squared >= 0.85:
            quality = "very good"
            reliability = "highly reliable"
        elif r_squared >= 0.70:
            quality = "good"
            reliability = "reliable"
        elif r_squared >= 0.50:
            quality = "moderate"
            reliability = "moderately reliable"
        else:
            quality = "poor"
            reliability = "needs improvement"
        
        return (
            f"This model has {quality} accuracy with an R-squared of {r_squared:.4f} "
            f"({percentage:.2f}%), meaning it explains {percentage:.1f}% of the "
            f"variance in energy consumption. Predictions are {reliability} for "
            f"typical operating conditions."
        )
    
    def _analyze_key_drivers(
        self, 
        coefficients: Dict[str, float], 
        feature_names: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Identify and rank the most important features.
        
        Args:
            coefficients: Feature coefficients
            feature_names: List of feature names
            
        Returns:
            List of key drivers sorted by absolute impact
        """
        if not coefficients:
            return []
        
        # Calculate absolute impact for ranking
        impacts = []
        for feature in feature_names:
            coef = coefficients.get(feature, 0)
            impacts.append({
                "feature": feature,
                "coefficient": coef,
                "absolute_impact": abs(coef),
                "direction": "increases" if coef > 0 else "decreases",
                "human_name": self._humanize_feature_name(feature)
            })
        
        # Sort by absolute impact (descending)
        impacts.sort(key=lambda x: x['absolute_impact'], reverse=True)
        
        # Add ranking
        for i, impact in enumerate(impacts, 1):
            impact['rank'] = i
        
        return impacts
    
    def _explain_coefficients(
        self,
        coefficients: Dict[str, float],
        intercept: float,
        feature_names: List[str]
    ) -> str:
        """
        Generate natural language formula explanation.
        
        Args:
            coefficients: Feature coefficients
            intercept: Model intercept
            feature_names: List of feature names
            
        Returns:
            Natural language formula
        """
        if not coefficients:
            return "No coefficient data available"
        
        parts = [f"The baseline energy starts at {intercept:.2f} kWh"]
        
        for feature in feature_names:
            coef = coefficients.get(feature, 0)
            human_name = self._humanize_feature_name(feature)
            
            if coef > 0:
                if coef < 0.01:
                    parts.append(f"increases by {coef:.6f} kWh per unit of {human_name}")
                else:
                    parts.append(f"increases by {coef:.3f} kWh per unit of {human_name}")
            else:
                abs_coef = abs(coef)
                if abs_coef < 0.01:
                    parts.append(f"decreases by {abs_coef:.6f} kWh per unit of {human_name}")
                else:
                    parts.append(f"decreases by {abs_coef:.3f} kWh per unit of {human_name}")
        
        return ", then ".join(parts) + "."
    
    def _summarize_impacts(
        self,
        coefficients: Dict[str, float],
        feature_names: List[str]
    ) -> Dict[str, Any]:
        """
        Summarize positive and negative impacts.
        
        Args:
            coefficients: Feature coefficients
            feature_names: List of feature names
            
        Returns:
            Dict with positive/negative impact summaries
        """
        positive = []
        negative = []
        
        for feature in feature_names:
            coef = coefficients.get(feature, 0)
            human_name = self._humanize_feature_name(feature)
            
            if coef > 0:
                positive.append({
                    "feature": human_name,
                    "coefficient": coef,
                    "impact": f"+{coef:.6f} kWh per unit" if coef < 0.01 else f"+{coef:.3f} kWh per unit"
                })
            else:
                negative.append({
                    "feature": human_name,
                    "coefficient": coef,
                    "impact": f"{coef:.6f} kWh per unit" if abs(coef) < 0.01 else f"{coef:.3f} kWh per unit"
                })
        
        return {
            "positive_impacts": positive,
            "negative_impacts": negative,
            "total_features": len(feature_names),
            "increasing_factors": len(positive),
            "decreasing_factors": len(negative)
        }
    
    def _generate_voice_summary(
        self,
        r_squared: float,
        key_drivers: List[Dict[str, Any]],
        model_data: Dict[str, Any]
    ) -> str:
        """
        Generate concise voice-friendly summary for TTS.
        
        Args:
            r_squared: R² value
            key_drivers: List of key drivers
            model_data: Full model data
            
        Returns:
            Voice-friendly summary
        """
        percentage = r_squared * 100
        machine_name = model_data.get('machine_name', 'this machine')
        
        # Start with accuracy
        parts = [f"The baseline model for {machine_name} has {percentage:.1f}% accuracy"]
        
        # Add top driver
        if key_drivers:
            top_driver = key_drivers[0]
            parts.append(
                f"The main energy driver is {top_driver['human_name']}, "
                f"which {top_driver['direction']} energy consumption"
            )
        
        # Add number of features
        num_features = len(key_drivers)
        if num_features > 1:
            parts.append(f"The model uses {num_features} features total")
        
        return ". ".join(parts) + "."
    
    def _humanize_feature_name(self, feature: str) -> str:
        """
        Convert feature name to human-readable format.
        
        Args:
            feature: Technical feature name
            
        Returns:
            Human-readable name
        """
        # Mapping of technical names to human names
        name_map = {
            "total_production_count": "production volume",
            "avg_outdoor_temp_c": "outdoor temperature",
            "avg_indoor_temp_c": "indoor temperature",
            "avg_machine_temp_c": "machine temperature",
            "avg_pressure_bar": "operating pressure",
            "avg_load_factor": "equipment load factor",
            "avg_power_factor": "power factor",
            "avg_current_a": "electrical current",
            "avg_voltage_v": "supply voltage",
            "avg_cycle_time_sec": "cycle time",
            "avg_throughput": "throughput rate",
            "outdoor_humidity_percent": "outdoor humidity",
            "heating_degree_days": "heating degree days",
            "cooling_degree_days": "cooling degree days",
            "operating_hours": "operating hours",
            "is_weekend": "weekend operation",
            "good_units_count": "good units produced",
            "defect_units_count": "defective units",
            # Natural gas features
            "consumption_m3": "gas consumption",
            "avg_flow_rate_m3h": "gas flow rate",
            "max_flow_rate_m3h": "peak gas flow",
            "avg_gas_temp_c": "gas temperature",
            "avg_calorific_value": "gas calorific value",
            # Steam features
            "consumption_kg": "steam consumption",
            "avg_flow_rate_kg_h": "steam flow rate",
            "avg_temperature_c": "steam temperature",
            "avg_enthalpy_kj_kg": "steam enthalpy",
            # Compressed air features
            "avg_dewpoint_c": "air dewpoint"
        }
        
        return name_map.get(feature, feature.replace('_', ' ').title())


# Global service instance
model_explainer = ModelExplainer()
