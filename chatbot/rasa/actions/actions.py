from typing import Any, Text, Dict, List, Optional, Tuple
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
import random
import re
import json
import os
import logging
from datetime import datetime
from difflib import SequenceMatcher
from collections import Counter

# Set up query logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# File handler for query logs
log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'query_log.jsonl')

file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(file_handler)

# Q&A verisini yükle
QA_DATA = {}
QA_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'qa_data.json')
if os.path.exists(QA_DATA_PATH):
    with open(QA_DATA_PATH, 'r', encoding='utf-8') as f:
        qa_data_raw = json.load(f)
        # Veriyi düzleştir: her intent için question->answer mapping
        for intent, qa_pairs in qa_data_raw.items():
            QA_DATA[intent] = {}
            for qa_pair in qa_pairs:
                if isinstance(qa_pair, list) and len(qa_pair) >= 2:
                    question = qa_pair[0].strip()
                    answer = qa_pair[1].strip().replace('\n', ' ').strip()
                    if question and answer:
                        QA_DATA[intent][question.lower()] = answer


class ActionRetrieveAnswer(Action):
    """Custom action to retrieve the most appropriate answer based on user's question."""
    
    def name(self) -> Text:
        return "action_retrieve_answer"
    
    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # Get the latest user message
        latest_message = tracker.latest_message
        user_message = latest_message.get("text", "")
        user_message_lower = user_message.lower()
        user_message_original_lower = user_message_lower
        intent = latest_message.get("intent", {}).get("name", "")
        
        # Log query start
        query_log = {
            "timestamp": datetime.utcnow().isoformat(),
            "query": user_message,
            "intent": intent,
            "sender_id": tracker.sender_id
        }
        
        # Common misspellings correction (Phase 8.6)
        misspellings = {
            "eneregy": "energy", "enery": "energy", "energey": "energy",
            "anaomaly": "anomaly", "anomoly": "anomaly", "anamoly": "anomaly",
            "eficiency": "efficiency", "efficency": "efficiency",
            "basline": "baseline", "baseeline": "baseline",
            "forcast": "forecast", "forcaste": "forecast",
            "dashbord": "dashboard", "dashbaord": "dashboard",
            "monitering": "monitoring", "moniterring": "monitoring",
            "equipement": "equipment", "equiptment": "equipment",
            "performace": "performance", "preformance": "performance",
            "consuption": "consumption", "consumtion": "consumption",
            "maintainance": "maintenance", "maintenence": "maintenance",
        }
        
        # Correct common misspellings
        for misspell, correct in misspellings.items():
            if misspell in user_message_lower:
                user_message_lower = user_message_lower.replace(misspell, correct)
        
        # Abbreviation expansion map (Phase 8.3)
        abbreviation_map = {
            "\\boee\\b": "overall equipment effectiveness",
            "\\bhvac\\b": "heating ventilation air conditioning",
            "\\bkpi\\b": "key performance indicator",
            "\\bseu\\b": "significant energy use",
            "\\bsec\\b": "specific energy consumption",
            "\\benpi\\b": "energy performance indicator",
            "\\bkpis\\b": "key performance indicators",
            "\\biot\\b": "internet of things",
            "\\bapi\\b": "application programming interface",
            "\\benpis\\b": "energy performance indicators",
        }
        
        # Expand abbreviations in user message (regex with word boundaries)
        for abbr, expansion in abbreviation_map.items():
            user_message_lower = re.sub(abbr, expansion, user_message_lower, flags=re.IGNORECASE)
        
        # Exact match across all categories (avoids misrouting for known questions)
        exact_category, exact_answer = self._find_exact_answer(user_message_lower)
        if not exact_answer and user_message_lower != user_message_original_lower:
            exact_category, exact_answer = self._find_exact_answer(user_message_original_lower)
        if exact_answer:
            query_log["matched_category"] = exact_category
            query_log["answer_preview"] = exact_answer[:100]
            query_log["status"] = "exact_match"
            logger.info(json.dumps(query_log))

            dispatcher.utter_message(text=exact_answer)
            self._give_contextual_advice(dispatcher, tracker, exact_category, user_message_lower)
            return []

        special_category, special_answer, special_status = self._resolve_special_case(user_message_lower)
        if special_answer:
            query_log["matched_category"] = special_category
            query_log["answer_preview"] = special_answer[:100]
            query_log["status"] = special_status
            logger.info(json.dumps(query_log))

            dispatcher.utter_message(text=special_answer)
            return []

        # Anahtar kelime mapping - hangi kelimeler hangi alt konuya ait
        keyword_to_topic = {
            # HumanEnerDIA PLATFORM topics (NEW - longer keywords for specificity)
            "humanenerdia platform": "ask_humenerdia_platform",
            "humanenerdia": "ask_humenerdia_platform",
            "what is humanenerdia": "ask_humenerdia_platform",
            "humanenerdia features": "ask_humenerdia_platform",
            "navigate humanenerdia": "ask_humenerdia_platform",
            
            # PORTAL DASHBOARD topics (Phase 2)
            "main dashboard": "ask_portal_dashboard",
            "portal dashboard": "ask_portal_dashboard",
            "portal home": "ask_portal_dashboard",
            "sidebar menu": "ask_portal_dashboard",
            "navigate portal": "ask_portal_dashboard",
            "what widgets": "ask_portal_dashboard",
            "main sections": "ask_portal_dashboard",
            "real-time data": "ask_portal_dashboard",
            "analytics vs grafana": "ask_portal_dashboard",
            
            # PORTAL BASELINE topics (Phase 2 - longer keywords to avoid ISO collision)
            "baseline page": "ask_portal_baseline",
            "baseline analysis": "ask_portal_baseline",
            "baseline prediction": "ask_portal_baseline",
            "baseline model": "ask_portal_baseline",
            "train baseline": "ask_portal_baseline",
            "r² score": "ask_portal_baseline",
            "r2 score": "ask_portal_baseline",
            "rmse baseline": "ask_portal_baseline",
            "mae baseline": "ask_portal_baseline",
            "coefficient bars": "ask_portal_baseline",
            "driver selection": "ask_portal_baseline",
            "baseline chart": "ask_portal_baseline",
            "baseline metrics": "ask_portal_baseline",
            
            # PORTAL ANOMALY topics (Phase 2)
            "anomaly page": "ask_portal_anomaly",
            "anomaly detection": "ask_portal_anomaly",
            "anomalies": "ask_portal_anomaly",
            "energy anomaly": "ask_portal_anomaly",
            "anomaly severity": "ask_portal_anomaly",
            "critical anomaly": "ask_portal_anomaly",
            "warning anomaly": "ask_portal_anomaly",
            "anomaly threshold": "ask_portal_anomaly",
            "filter anomalies": "ask_portal_anomaly",
            "detect anomalies": "ask_portal_anomaly",
            
            # PORTAL KPI topics (Phase 2)
            "kpi page": "ask_portal_kpi",
            "kpi dashboard": "ask_portal_kpi",
            "key performance indicator": "ask_portal_kpi",
            "efficiency metrics": "ask_portal_kpi",
            "load factor kpi": "ask_portal_kpi",
            "peak demand ratio": "ask_portal_kpi",
            "cost efficiency": "ask_portal_kpi",
            "sec kpi": "ask_portal_kpi",
            "specific energy consumption": "ask_portal_kpi",
            "improve kpis": "ask_portal_kpi",
            "kpis": "ask_portal_kpi",
            "track kpi": "ask_portal_kpi",
            
            # PORTAL FORECAST topics (Phase 2)
            "forecast page": "ask_portal_forecast",
            "energy forecasting": "ask_portal_forecast",
            "arima model": "ask_portal_forecast",
            "prophet model": "ask_portal_forecast",
            "arima vs prophet": "ask_portal_forecast",
            "difference between arima and prophet": "ask_portal_forecast",
            "arima and prophet": "ask_portal_forecast",
            "compare arima prophet": "ask_portal_forecast",
            "train forecast": "ask_portal_forecast",
            "forecast horizon": "ask_portal_forecast",
            "optimal load scheduling": "ask_portal_forecast",
            "load scheduling": "ask_portal_forecast",
            "best time to run": "ask_portal_forecast",
            "trained model status": "ask_portal_forecast",
            "retrain forecast": "ask_portal_forecast",
            
            # PORTAL REPORTS topics (Phase 2)
            "report page": "ask_portal_reports",
            "generate report": "ask_portal_reports",
            "pdf report": "ask_portal_reports",
            "energy report": "ask_portal_reports",
            "download report": "ask_portal_reports",
            "report types": "ask_portal_reports",
            
            # VISUALIZATION - SANKEY topics (Phase 2)
            "sankey diagram": "ask_viz_sankey",
            "sankey": "ask_viz_sankey",
            "energy flow": "ask_viz_sankey",
            "flow diagram": "ask_viz_sankey",
            "sankey nodes": "ask_viz_sankey",
            
            # VISUALIZATION - HEATMAP topics (Phase 2)
            "heatmap": "ask_viz_heatmap",
            "heat map": "ask_viz_heatmap",
            "anomaly heatmap": "ask_viz_heatmap",
            "consumption heatmap": "ask_viz_heatmap",
            
            # VISUALIZATION - COMPARISON topics (Phase 2)
            "comparison page": "ask_viz_comparison",
            "compare machines": "ask_viz_comparison",
            "machine comparison": "ask_viz_comparison",
            "compare energy": "ask_viz_comparison",
            
            # GETTING STARTED - New user onboarding (Phase 3.1)
            "how do i get started": "ask_getting_started",
            "get started": "ask_getting_started",
            "getting started": "ask_getting_started",
            "first time user": "ask_getting_started",
            "new user": "ask_getting_started",
            "where should i start": "ask_getting_started",
            "start using": "ask_getting_started",
            "quick start": "ask_getting_started",
            "onboarding": "ask_getting_started",
            
            # TROUBLESHOOTING - High priority specific issues (Phase 3.5)
            "dashboard not showing data": "ask_troubleshooting",
            "grafana dashboard not showing data": "ask_troubleshooting",
            "grafana dashboard empty": "ask_troubleshooting",
            "dashboard empty": "ask_troubleshooting",
            "no data in dashboard": "ask_troubleshooting",
            "charts empty": "ask_troubleshooting",
            "troubleshooting": "ask_troubleshooting",
            "troubleshoot": "ask_troubleshooting",
            "fix issues": "ask_troubleshooting",
            "problems": "ask_troubleshooting",
            "not working": "ask_troubleshooting",
            "error": "ask_troubleshooting",
            
            # MULTI-ENERGY - Multiple fuel types (Phase 3.2)
            "multi-energy": "ask_multi_energy",
            "multiple energy": "ask_multi_energy",
            "multi energy": "ask_multi_energy",
            "natural gas": "ask_multi_energy",
            "steam energy": "ask_multi_energy",
            "compressed air": "ask_multi_energy",
            "fuel types": "ask_multi_energy",
            "energy source": "ask_multi_energy",
            "fuel switching": "ask_multi_energy",
            
            # ALERTS CONFIG - Threshold and notification setup (Phase 3.3)
            "alerts config": "ask_alerts_config",
            "alert configuration": "ask_alerts_config",
            "threshold configuration": "ask_alerts_config",
            "notification settings": "ask_alerts_config",
            "email alerts": "ask_alerts_config",
            "sms alerts": "ask_alerts_config",
            "push notifications": "ask_alerts_config",
            "configure thresholds": "ask_alerts_config",
            
            # DATA EXPORT - Export and reporting (Phase 3.4)
            "data export": "ask_data_export",
            "export data": "ask_data_export",
            "download data": "ask_data_export",
            "csv export": "ask_data_export",
            "excel export": "ask_data_export",
            "export to": "ask_data_export",
            "scheduled export": "ask_data_export",
            
            # WASABI PROJECT - Project context and support (Phase 3.6)
            "wasabi project": "ask_wasabi_project",
            "wasabi experiment": "ask_wasabi_project",
            "about wasabi": "ask_wasabi_project",
            "green edih": "ask_wasabi_project",
            "a plus engineering": "ask_wasabi_project",
            "open source": "ask_wasabi_project",
            
            # GRAFANA DASHBOARDS - General (Phase 3)
            "grafana": "ask_grafana_general",
            "grafana dashboards": "ask_grafana_general",
            "sota dashboards": "ask_grafana_general",
            "what is sota": "ask_grafana_general",
            "how many dashboards": "ask_grafana_general",
            "access grafana": "ask_grafana_general",
            "dashboard refresh": "ask_grafana_general",
            
            # SCHEDULER JOBS - Automated Tasks
            "scheduler": "ask_scheduler",
            "scheduled jobs": "ask_scheduler",
            "automated jobs": "ask_scheduler",
            "background jobs": "ask_scheduler",
            "cron jobs": "ask_scheduler",
            "apscheduler": "ask_scheduler",
            "baseline retrain": "ask_scheduler",
            "anomaly detection job": "ask_scheduler",
            "kpi calculation": "ask_scheduler",
            "training cleanup": "ask_scheduler",
            "job status": "ask_scheduler",
            "trigger job": "ask_scheduler",
            
            # GRAFANA - Factory Overview (Phase 3)
            "factory overview": "ask_grafana_factory",
            "factory dashboard": "ask_grafana_factory",
            "command center": "ask_grafana_factory",
            "factory status": "ask_grafana_factory",
            "all machines dashboard": "ask_grafana_factory",
            "live power consumption": "ask_grafana_factory",
            
            # GRAFANA - ISO 50001 EnPI (Phase 3)
            "sota iso 50001": "ask_grafana_iso50001",
            "iso 50001 dashboard": "ask_grafana_iso50001",
            "enpi dashboard": "ask_grafana_iso50001",
            "cusum control": "ask_grafana_iso50001",
            "weather normalization": "ask_grafana_iso50001",
            "seu performance": "ask_grafana_iso50001",
            "baseline vs actual": "ask_grafana_iso50001",
            
            # GRAFANA - Anomaly Detection (Phase 3)
            "grafana anomaly": "ask_grafana_anomaly",
            "anomaly dashboard": "ask_grafana_anomaly",
            "anomaly heatmap grafana": "ask_grafana_anomaly",
            "mean time to resolution": "ask_grafana_anomaly",
            "mttr anomaly": "ask_grafana_anomaly",
            "unresolved anomalies": "ask_grafana_anomaly",
            "anomaly timeline": "ask_grafana_anomaly",
            
            # GRAFANA - Cost Analytics (Phase 3)
            "cost analytics": "ask_grafana_cost",
            "cost dashboard": "ask_grafana_cost",
            "energy costs grafana": "ask_grafana_cost",
            "time of use cost": "ask_grafana_cost",
            "cost savings opportunities": "ask_grafana_cost",
            "monthly cost trend": "ask_grafana_cost",
            "top cost contributors": "ask_grafana_cost",
            
            # GRAFANA - Executive Summary (Phase 3)
            "executive summary": "ask_grafana_executive",
            "executive dashboard": "ask_grafana_executive",
            "management dashboard": "ask_grafana_executive",
            "energy intensity trend": "ask_grafana_executive",
            "operational concerns": "ask_grafana_executive",
            
            # GRAFANA - Machine Health (Phase 3)
            "machine health dashboard": "ask_grafana_machine_health",
            "machine health grafana": "ask_grafana_machine_health",
            "health score": "ask_grafana_machine_health",
            "baseline variance": "ask_grafana_machine_health",
            "machine deep dive": "ask_grafana_machine_health",
            
            # GRAFANA - ML Performance (Phase 3)
            "ml performance dashboard": "ask_grafana_ml",
            "model performance grafana": "ask_grafana_ml",
            "ml metrics dashboard": "ask_grafana_ml",
            "r² score trend": "ask_grafana_ml",
            "rmse trend": "ask_grafana_ml",
            "training history": "ask_grafana_ml",
            "active models": "ask_grafana_ml",
            
            # GRAFANA - Operational Efficiency (Phase 3)
            "operational efficiency dashboard": "ask_grafana_operational",
            "oee dashboard": "ask_grafana_operational",
            "availability rate": "ask_grafana_operational",
            "performance rate": "ask_grafana_operational",
            "production efficiency": "ask_grafana_operational",
            
            # GRAFANA - Predictive Analytics (Phase 3)
            "predictive analytics dashboard": "ask_grafana_predictive",
            "forecast dashboard": "ask_grafana_predictive",
            "mape forecast": "ask_grafana_predictive",
            "forecast vs actual": "ask_grafana_predictive",
            "forecast accuracy": "ask_grafana_predictive",
            
            # GRAFANA - Real-Time Production (Phase 3)
            "realtime production": "ask_grafana_realtime",
            "real-time dashboard": "ask_grafana_realtime",
            "live power grafana": "ask_grafana_realtime",
            "realtime monitoring": "ask_grafana_realtime",
            
            # GRAFANA - Environmental Impact (Phase 3)
            "environmental impact": "ask_grafana_environmental",
            "carbon footprint": "ask_grafana_environmental",
            "co2 emissions": "ask_grafana_environmental",
            "emission intensity": "ask_grafana_environmental",
            "carbon dashboard": "ask_grafana_environmental",
            "emission reduction": "ask_grafana_environmental",
            
            # OVOS Voice Assistant - Capabilities (Phase 4)
            "ovos capabilities": "ask_ovos_capabilities",
            "voice assistant": "ask_ovos_capabilities",
            "what can ovos do": "ask_ovos_capabilities",
            "what can i ask": "ask_ovos_capabilities",
            "voice commands": "ask_ovos_capabilities",
            "what is ovos": "ask_ovos_capabilities",
            "ovos features": "ask_ovos_capabilities",
            "available voice commands": "ask_ovos_capabilities",
            
            # OVOS Voice Assistant - Energy Queries (Phase 4)
            "energy by voice": "ask_ovos_energy",
            "ask about energy": "ask_ovos_energy",
            "voice energy query": "ask_ovos_energy",
            "energy consumption voice": "ask_ovos_energy",
            "ask ovos energy": "ask_ovos_energy",
            "how do i ask about energy": "ask_ovos_energy",
            
            # OVOS Voice Assistant - Status Queries (Phase 4)
            "status by voice": "ask_ovos_status",
            "machine status voice": "ask_ovos_status",
            "check status voice": "ask_ovos_status",
            "ask machine status": "ask_ovos_status",
            "voice status check": "ask_ovos_status",
            "system health voice": "ask_ovos_status",
            
            # OVOS Voice Assistant - KPI Queries (Phase 4)
            "kpi by voice": "ask_ovos_kpi",
            "ask kpis voice": "ask_ovos_kpi",
            "performance voice": "ask_ovos_kpi",
            "voice kpi query": "ask_ovos_kpi",
            "load factor voice": "ask_ovos_kpi",
            "sec voice": "ask_ovos_kpi",
            
            # OVOS Voice Assistant - Forecast Queries (Phase 4)
            "forecast by voice": "ask_ovos_forecast",
            "voice forecast": "ask_ovos_forecast",
            "ask forecast voice": "ask_ovos_forecast",
            "prediction voice": "ask_ovos_forecast",
            "baseline voice": "ask_ovos_forecast",
            
            # OVOS Voice Assistant - Anomaly Queries (Phase 4)
            "anomaly by voice": "ask_ovos_anomaly",
            "voice anomaly": "ask_ovos_anomaly",
            "ask about anomalies": "ask_ovos_anomaly",
            "alerts voice": "ask_ovos_anomaly",
            
            # OVOS Voice Assistant - Cost Queries (Phase 4)
            "cost by voice": "ask_ovos_cost",
            "voice cost query": "ask_ovos_cost",
            "ask about costs": "ask_ovos_cost",
            "energy cost voice": "ask_ovos_cost",
            
            # OVOS Voice Assistant - Reports (Phase 4)
            "report by voice": "ask_ovos_reports",
            "generate report voice": "ask_ovos_reports",
            "generate reports by voice": "ask_ovos_reports",
            "pdf voice": "ask_ovos_reports",
            "voice report": "ask_ovos_reports",
            "voice reports": "ask_ovos_reports",
            
            # TECHNICAL CONCEPTS - Baseline (Phase 5)
            "what is energy baseline": "ask_concept_baseline",
            "what is baseline": "ask_concept_baseline",
            "baseline concept": "ask_concept_baseline",
            "how is baseline calculated": "ask_concept_baseline",
            "baseline vs forecast": "ask_concept_baseline",
            "baseline drivers": "ask_concept_baseline",
            "baseline deviation": "ask_concept_baseline",
            "baseline accuracy": "ask_concept_baseline",
            "retrain baseline": "ask_concept_baseline",
            "normalized baseline": "ask_concept_baseline",
            
            # TECHNICAL CONCEPTS - EnPI (Phase 5)
            "what is enpi": "ask_concept_enpi",
            "enpi concept": "ask_concept_enpi",
            "how is enpi calculated": "ask_concept_enpi",
            "enpi vs kpi": "ask_concept_enpi",
            "good enpi value": "ask_concept_enpi",
            "enpi trend": "ask_concept_enpi",
            "enpi iso 50001": "ask_concept_enpi",
            "cusum enpi": "ask_concept_enpi",
            
            # TECHNICAL CONCEPTS - SEC (Phase 5)
            "what is sec": "ask_concept_sec",
            "sec concept": "ask_concept_sec",
            "specific energy consumption": "ask_concept_sec",
            "how is sec calculated": "ask_concept_sec",
            "good sec value": "ask_concept_sec",
            "reduce sec": "ask_concept_sec",
            "kwh per unit": "ask_concept_sec",
            
            # TECHNICAL CONCEPTS - Load Factor (Phase 5)
            "what is load factor": "ask_concept_loadfactor",
            "load factor concept": "ask_concept_loadfactor",
            "how is load factor calculated": "ask_concept_loadfactor",
            "good load factor": "ask_concept_loadfactor",
            "improve load factor": "ask_concept_loadfactor",
            
            # TECHNICAL CONCEPTS - Peak Demand (Phase 5)
            "what is peak demand": "ask_concept_peakdemand",
            "peak demand concept": "ask_concept_peakdemand",
            "reduce peak demand": "ask_concept_peakdemand",
            "demand response": "ask_concept_peakdemand",
            "peak shaving": "ask_concept_peakdemand",
            
            # TECHNICAL CONCEPTS - SEU (Phase 5)
            "what is seu": "ask_concept_seu",
            "seu concept": "ask_concept_seu",
            "significant energy uses": "ask_concept_seu",
            "how are seus identified": "ask_concept_seu",
            "manage seus": "ask_concept_seu",
            
            # TECHNICAL CONCEPTS - ARIMA (Phase 5)
            "what is arima": "ask_concept_arima",
            "arima concept": "ask_concept_arima",
            "how does arima work": "ask_concept_arima",
            "arima forecast": "ask_concept_arima",
            "arima accuracy": "ask_concept_arima",
            "arima limitations": "ask_concept_arima",
            
            # TECHNICAL CONCEPTS - Prophet (Phase 5)
            "what is prophet": "ask_concept_prophet",
            "prophet concept": "ask_concept_prophet",
            "how does prophet work": "ask_concept_prophet",
            "prophet forecast": "ask_concept_prophet",
            "prophet vs arima": "ask_concept_prophet",
            
            # TECHNICAL CONCEPTS - Anomaly Detection (Phase 5)
            "how does anomaly detection work": "ask_concept_anomaly_ml",
            "anomaly detection algorithm": "ask_concept_anomaly_ml",
            "z-score anomaly": "ask_concept_anomaly_ml",
            "isolation forest": "ask_concept_anomaly_ml",
            "anomaly severity": "ask_concept_anomaly_ml",
            "what causes anomalies": "ask_concept_anomaly_ml",
            
            # TECHNICAL CONCEPTS - OEE (Phase 5)
            "what is oee": "ask_concept_oee",
            "oee concept": "ask_concept_oee",
            "overall equipment effectiveness": "ask_concept_oee",
            "how is oee calculated": "ask_concept_oee",
            "good oee": "ask_concept_oee",
            
            # TECHNICAL CONCEPTS - CUSUM (Phase 5)
            "what is cusum": "ask_concept_cusum",
            "cusum chart": "ask_concept_cusum",
            "cusum concept": "ask_concept_cusum",
            "how does cusum work": "ask_concept_cusum",
            "read cusum chart": "ask_concept_cusum",
            
            # SYSTEM COMPONENTS - Node-RED (Phase 6)
            "what is node-red": "ask_nodered",
            "node-red": "ask_nodered",
            "nodered": "ask_nodered",
            "node red": "ask_nodered",
            "etl pipeline": "ask_nodered",
            "data pipeline": "ask_nodered",
            "node-red flows": "ask_nodered",
            "access node-red": "ask_nodered",
            
            # SYSTEM COMPONENTS - MQTT (Phase 6)
            "what is mqtt": "ask_mqtt",
            "mqtt broker": "ask_mqtt",
            "mqtt topics": "ask_mqtt",
            "publish subscribe": "ask_mqtt",
            "mqtt messages": "ask_mqtt",
            "monitor mqtt": "ask_mqtt",
            
            # SYSTEM COMPONENTS - TimescaleDB (Phase 6)
            "what is timescaledb": "ask_timescaledb",
            "timescaledb": "ask_timescaledb",
            "hypertables": "ask_timescaledb",
            "continuous aggregates": "ask_timescaledb",
            "time-series database": "ask_timescaledb",
            "query timescaledb": "ask_timescaledb",
            "access database": "ask_timescaledb",
            
            # SYSTEM COMPONENTS - Analytics API (Phase 6)
            "what is analytics api": "ask_analytics_api",
            "analytics api": "ask_analytics_api",
            "analytics service": "ask_analytics_api",
            "fastapi backend": "ask_analytics_api",
            "api endpoints": "ask_analytics_api",
            "swagger docs": "ask_analytics_api",
            "analytics architecture": "ask_analytics_api",
            
            # SYSTEM COMPONENTS - Simulator (Phase 6)
            "what is simulator": "ask_simulator",
            "simulator": "ask_simulator",
            "simulated data": "ask_simulator",
            "factory simulator": "ask_simulator",
            "simulator status": "ask_simulator",
            "machine simulation": "ask_simulator",
            "test data generator": "ask_simulator",
            
            # SYSTEM COMPONENTS - Docker (Phase 6)
            "docker": "ask_docker",
            "docker services": "ask_docker",
            "docker-compose": "ask_docker",
            "start services": "ask_docker",
            "restart service": "ask_docker",
            "check service health": "ask_docker",
            "what ports": "ask_docker",
            "nginx routing": "ask_docker",
            
            # SYSTEM COMPONENTS - Redis (Phase 6)
            "what is redis": "ask_redis",
            "redis caching": "ask_redis",
            "redis pub/sub": "ask_redis",
            "websocket events": "ask_redis",
            "real-time events": "ask_redis",
            
            # DEFINITION topics (expanded Phase 8)
            "baseline": "ask_energy_baseline",
            "energy baseline": "ask_energy_baseline",
            "baseline reference": "ask_energy_baseline",
            "baseline period": "ask_energy_baseline",
            "baseline adjustment": "ask_energy_baseline",
            "enpi": "ask_enpi",
            "enpis": "ask_enpi",
            "energy performance indicator": "ask_enpi",
            "significant energy use": "ask_significant_energy_use",
            "seu": "ask_significant_energy_use",
            "energy review": "ask_energy_review",
            "scope": "ask_scope",
            "boundary": "ask_scope",
            "scope definition": "ask_scope",
            "scope exclusions": "ask_scope",
            "system boundary": "ask_scope",
            "terms": "ask_terms_definitions",
            "definitions": "ask_definitions",
            "define": "ask_definitions",
            "meaning": "ask_definitions",
            "exactly is meant by": "ask_terms_definitions",
            "what exactly is meant": "ask_terms_definitions",
            
            # PURPOSE topics (expanded Phase 8.6)
            "pdca": "ask_pdca",
            "plan do check act": "ask_pdca",
            "pdca cycle": "ask_pdca",
            "continuous improvement": "ask_pdca",
            "benchmarking": "ask_benchmarking",
            "benchmark": "ask_benchmarking",
            "compare performance": "ask_benchmarking",
            "industry standards": "ask_benchmarking",
            "iso": "ask_iso_standards",
            "iso 50001": "ask_iso_standards",
            "international standard": "ask_iso_standards",
            "this international standard": "ask_iso_standards",
            "primary objective": "ask_iso_standards",
            "for what purposes": "ask_iso_standards",
            "standard": "ask_iso_standards",
            "general": "ask_general_info",
            "general information": "ask_general_info",
            "overview": "ask_general_info",
            "about humanenerdia": "ask_general_info",
            
            # PROCESS topics (expanded coverage for Phase 8)
            "planning": "ask_energy_planning",
            "energy planning": "ask_energy_planning",
            "planning process": "ask_energy_planning",
            "energy review": "ask_energy_planning",
            "energy objectives": "ask_energy_planning",
            "implementation": "ask_implementation",
            "implement": "ask_implementation",
            "implementation plan": "ask_implementation",
            "deployment": "ask_implementation",
            "checking": "ask_checking",
            "check": "ask_checking",
            "checking process": "ask_checking",
            "verification": "ask_checking",
            "monitoring": "ask_monitoring_measurement",
            "measurement": "ask_monitoring_measurement",
            "audit": "ask_internal_audit",
            "internal audit": "ask_internal_audit",
            "audit program": "ask_internal_audit",
            "audit criteria": "ask_internal_audit",
            "audit findings": "ask_internal_audit",
            "management review": "ask_management_review",
            "review meeting": "ask_management_review",
            "review process": "ask_management_review",
            "review inputs": "ask_management_review",
            "review outputs": "ask_management_review",
            "corrective": "ask_corrective_preventive_action",
            "preventive": "ask_corrective_preventive_action",
            "action plan": "ask_action_plans",
            "action plans": "ask_action_plans",
            "action plan development": "ask_action_plans",
            "plan execution": "ask_action_plans",
            "plan monitoring": "ask_action_plans",
            "objectives": "ask_objectives_targets",
            "targets": "ask_objectives_targets",
            "operational control": "ask_operational_control",
            "design": "ask_design",
            "procurement": "ask_procurement",
            "communication": "ask_communication",
            "competence": "ask_competence_training",
            "training": "ask_competence_training",
            "documentation": "ask_documentation",
            "records": "ask_records",
            "process": "process",
            "procedure": "process",
            "how to": "process",
            "steps": "process",
            "establish process": "process",
            "implement process": "process",
            
            # REQUIREMENT topics (expanded coverage for Phase 8)
            "policy": "ask_energy_policy",
            "energy policy": "ask_energy_policy",
            "policy statement": "ask_energy_policy",
            "policy commitments": "ask_energy_policy",
            "policy framework": "ask_energy_policy",
            "legal": "ask_legal_requirements",
            "legal requirements": "ask_legal_requirements",
            "compliance": "ask_compliance",
            "management responsibility": "ask_management_responsibility",
            "top management": "ask_management_responsibility",
            "management commitment": "ask_management_responsibility",
            "leadership": "ask_management_responsibility",
            "requirement": "requirement",
            "must": "requirement",
            "shall": "requirement",
            "mandatory": "requirement",
            "required": "requirement",
            "obligated": "requirement",
        }
        
        # If intent is not in new structure, use default utter action
        if intent not in ["definition", "purpose", "process", "requirement"]:
            # For non-ask intents, use the standard utter action
            if intent in ["greet", "goodbye", "thank", "affirm", "deny"]:
                dispatcher.utter_message(response=f"utter_{intent}")
            return []
        
        # Anahtar kelimelerle alt konuyu belirle
        # Önce uzun keyword'leri kontrol et (daha spesifik olanlar öncelikli)
        topic = None
        best_match_length = 0
        
        # Keyword'leri uzunluklarına göre sırala (uzun olanlar önce - daha spesifik)
        sorted_keywords = sorted(keyword_to_topic.items(), key=lambda x: len(x[0]), reverse=True)
        
        for keyword, topic_name in sorted_keywords:
            # Regex ile kelime sınırlarını kontrol et (daha doğru eşleşme)
            # \b kelime sınırı, (?i) case-insensitive
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, user_message_lower, re.IGNORECASE):
                # Uzun keyword'ler daha yüksek öncelik alır
                if len(keyword) > best_match_length:
                    best_match_length = len(keyword)
                    topic = topic_name
                    # En uzun eşleşmeyi bulduk, devam et (daha uzun olabilir)
        
        # Eğer regex ile bulunamazsa, basit substring kontrolü yap (fallback)
        if not topic:
            for keyword, topic_name in sorted_keywords:
                if keyword in user_message_lower:
                    topic = topic_name
                    break
        
        # Özel durumlar: "international standard" içeren sorular
        if not topic or topic == "ask_terms_definitions":
            if 'international standard' in user_message_lower or 'this international standard' in user_message_lower:
                if 'primary objective' in user_message_lower or 'objective' in user_message_lower:
                    topic = "ask_iso_standards"
                elif 'for what purposes' in user_message_lower or 'what purposes' in user_message_lower:
                    topic = "ask_iso_standards"
                elif 'to what variables' in user_message_lower or ('variables' in user_message_lower and 'applicable' in user_message_lower):
                    topic = "ask_scope"
                elif topic != "ask_iso_standards" and topic != "ask_scope":
                    topic = "ask_iso_standards"
        
        # Eğer topic bulunamazsa, intent'e göre genel bir topic seç
        if not topic:
            if intent == "definition":
                topic = "ask_definitions"
            elif intent == "purpose":
                # Purpose intent'i için daha spesifik kontrol
                if any(term in user_message_lower for term in ['iso', 'standard', 'international standard']):
                    topic = "ask_iso_standards"
                elif any(term in user_message_lower for term in ['scope', 'boundary']):
                    topic = "ask_scope"
                elif any(term in user_message_lower for term in ['benchmark']):
                    topic = "ask_benchmarking"
                elif any(term in user_message_lower for term in ['pdca', 'plan do check act']):
                    topic = "ask_pdca"
                else:
                    topic = "ask_general_info"
            elif intent == "process":
                # Process intent'inde scope/boundary soruları da var
                if any(term in user_message_lower for term in ['scope', 'boundary', 'boundaries']):
                    # Scope soruları process intent'inde, topic'i ask_scope olarak işaretle
                    # ama arama process intent'inde yapılacak
                    topic = "ask_scope"
                else:
                    topic = "ask_energy_planning"
            elif intent == "requirement":
                topic = "ask_energy_policy"
        
        # ÖNEMLİ: Scope/boundary soruları process intent'inde olduğu için özel kontrol
        # Intent definition olsa bile, scope soruları process intent'inde
        scope_keywords = ['scope', 'boundary', 'boundaries']
        user_has_scope = any(keyword in user_message_lower for keyword in scope_keywords)
        
        # PRIORITY 1: Topic-specific categories (e.g., ask_humenerdia_platform) take precedence
        # This ensures keyword-matched topics are checked BEFORE generic process/definition lookups
        if topic and topic not in ["ask_scope"] and topic in QA_DATA and QA_DATA[topic]:
            best_answer = self._find_best_answer(user_message_lower, QA_DATA[topic], topic)
            if best_answer:
                # Log successful match
                query_log["matched_category"] = topic
                query_log["answer_preview"] = best_answer[:100]
                query_log["status"] = "success"
                logger.info(json.dumps(query_log))
                
                dispatcher.utter_message(text=best_answer)
                # Trigger advice after answer
                self._give_contextual_advice(dispatcher, tracker, topic, user_message_lower)
                return []
        
        # PRIORITY 2: Process intent için QA_DATA["process"]'e bak
        if intent == "process" and "process" in QA_DATA and QA_DATA["process"]:
            best_answer = self._find_best_answer(user_message_lower, QA_DATA["process"], "process")
            if best_answer:
                # Log successful match
                query_log["matched_category"] = "process"
                query_log["answer_preview"] = best_answer[:100]
                query_log["status"] = "success"
                logger.info(json.dumps(query_log))
                
                dispatcher.utter_message(text=best_answer)
                return []
        
        # Scope soruları için özel kontrol: Intent definition olsa bile process'te ara
        if user_has_scope and "process" in QA_DATA and QA_DATA["process"]:
            best_answer = self._find_best_answer(user_message_lower, QA_DATA["process"], "process")
            if best_answer:
                # Log successful match
                query_log["matched_category"] = "process (scope)"
                query_log["answer_preview"] = best_answer[:100]
                query_log["status"] = "success"
                logger.info(json.dumps(query_log))
                
                dispatcher.utter_message(text=best_answer)
                return []
        
        # PRIORITY 3: Scope topic'ine bak (process intent'inden sonra)
        if topic == "ask_scope" and topic in QA_DATA and QA_DATA[topic]:
            best_answer = self._find_best_answer(user_message_lower, QA_DATA[topic], topic)
            if best_answer:
                # Log successful match
                query_log["matched_category"] = topic
                query_log["answer_preview"] = best_answer[:100]
                query_log["status"] = "success"
                logger.info(json.dumps(query_log))
                
                dispatcher.utter_message(text=best_answer)
                return []
        
        # Q&A verisinde bulunamazsa, domain'deki response'ları kullan
        topic_to_response = {
            # HumanEnerDIA PLATFORM (NEW)
            "ask_humenerdia_platform": "utter_ask_humenerdia_platform",
            
            # PORTAL PAGES (Phase 2)
            "ask_portal_dashboard": "utter_ask_portal_dashboard",
            "ask_portal_baseline": "utter_ask_portal_baseline",
            "ask_portal_anomaly": "utter_ask_portal_anomaly",
            "ask_portal_kpi": "utter_ask_portal_kpi",
            "ask_portal_forecast": "utter_ask_portal_forecast",
            "ask_portal_reports": "utter_ask_portal_reports",
            
            # VISUALIZATIONS (Phase 2)
            "ask_viz_sankey": "utter_ask_viz_sankey",
            "ask_viz_heatmap": "utter_ask_viz_heatmap",
            "ask_viz_comparison": "utter_ask_viz_comparison",
            
            # GRAFANA DASHBOARDS (Phase 3)
            "ask_grafana_general": "utter_ask_grafana_general",
            "ask_grafana_factory": "utter_ask_grafana_factory",
            "ask_grafana_iso50001": "utter_ask_grafana_iso50001",
            "ask_grafana_anomaly": "utter_ask_grafana_anomaly",
            "ask_grafana_cost": "utter_ask_grafana_cost",
            "ask_grafana_executive": "utter_ask_grafana_executive",
            "ask_grafana_machine_health": "utter_ask_grafana_machine_health",
            "ask_grafana_ml": "utter_ask_grafana_ml",
            "ask_grafana_operational": "utter_ask_grafana_operational",
            "ask_grafana_predictive": "utter_ask_grafana_predictive",
            "ask_grafana_realtime": "utter_ask_grafana_realtime",
            "ask_grafana_environmental": "utter_ask_grafana_environmental",
            
            # OVOS VOICE ASSISTANT (Phase 4)
            "ask_ovos_capabilities": "utter_ask_ovos_capabilities",
            "ask_ovos_energy": "utter_ask_ovos_energy",
            "ask_ovos_status": "utter_ask_ovos_status",
            "ask_ovos_kpi": "utter_ask_ovos_kpi",
            "ask_ovos_forecast": "utter_ask_ovos_forecast",
            "ask_ovos_anomaly": "utter_ask_ovos_anomaly",
            "ask_ovos_cost": "utter_ask_ovos_cost",
            "ask_ovos_reports": "utter_ask_ovos_reports",
            
            # TECHNICAL CONCEPTS (Phase 5)
            "ask_concept_baseline": "utter_ask_concept_baseline",
            "ask_concept_enpi": "utter_ask_concept_enpi",
            "ask_concept_sec": "utter_ask_concept_sec",
            "ask_concept_loadfactor": "utter_ask_concept_loadfactor",
            "ask_concept_peakdemand": "utter_ask_concept_peakdemand",
            "ask_concept_seu": "utter_ask_concept_seu",
            "ask_concept_arima": "utter_ask_concept_arima",
            "ask_concept_prophet": "utter_ask_concept_prophet",
            "ask_concept_anomaly_ml": "utter_ask_concept_anomaly_ml",
            "ask_concept_oee": "utter_ask_concept_oee",
            "ask_concept_cusum": "utter_ask_concept_cusum",
            
            # SYSTEM COMPONENTS (Phase 6)
            "ask_nodered": "utter_ask_nodered",
            "ask_mqtt": "utter_ask_mqtt",
            "ask_timescaledb": "utter_ask_timescaledb",
            "ask_analytics_api": "utter_ask_analytics_api",
            "ask_simulator": "utter_ask_simulator",
            "ask_docker": "utter_ask_docker",
            "ask_redis": "utter_ask_redis",
            
            # Existing ISO 50001 topics
            "ask_energy_baseline": "utter_ask_energy_baseline",
            "ask_enpi": "utter_ask_enpi",
            "ask_significant_energy_use": "utter_ask_significant_energy_use",
            "ask_energy_review": "utter_ask_energy_review",
            "ask_scope": "utter_ask_scope",
            "ask_terms_definitions": "utter_ask_terms_definitions",
            "ask_definitions": "utter_ask_definitions",
            "ask_pdca": "utter_ask_pdca",
            "ask_benchmarking": "utter_ask_benchmarking",
            "ask_iso_standards": "utter_ask_iso_standards",
            "ask_general_info": "utter_ask_general_info",
            "ask_energy_planning": "utter_ask_energy_planning",
            "ask_implementation": "utter_ask_implementation",
            "ask_checking": "utter_ask_checking",
            "ask_monitoring_measurement": "utter_ask_monitoring_measurement",
            "ask_internal_audit": "utter_ask_internal_audit",
            "ask_management_review": "utter_ask_management_review",
            "ask_corrective_preventive_action": "utter_ask_corrective_preventive_action",
            "ask_action_plans": "utter_ask_action_plans",
            "ask_objectives_targets": "utter_ask_objectives_targets",
            "ask_operational_control": "utter_ask_operational_control",
            "ask_design": "utter_ask_design",
            "ask_procurement": "utter_ask_procurement",
            "ask_communication": "utter_ask_communication",
            "ask_competence_training": "utter_ask_competence_training",
            "ask_documentation": "utter_ask_documentation",
            "ask_records": "utter_ask_records",
            "ask_energy_policy": "utter_ask_energy_policy",
            "ask_legal_requirements": "utter_ask_legal_requirements",
            "ask_compliance": "utter_ask_compliance",
            "ask_management_responsibility": "utter_ask_management_responsibility",
        }
        
        response_key = topic_to_response.get(topic, f"utter_ask_general_info")
        responses = domain.get("responses", {}).get(response_key, [])
        
        if not responses:
            # Fallback: use the standard utter action
            # Log fallback
            query_log["matched_category"] = "fallback"
            query_log["response_key"] = response_key
            query_log["status"] = "fallback"
            logger.info(json.dumps(query_log))
            
            dispatcher.utter_message(response=response_key)
            return []
        
        # Select the most appropriate response based on keywords in user message
        selected_response = self._select_best_response(user_message_lower, responses, topic or intent)
        
        # Log domain response
        query_log["matched_category"] = topic or intent
        query_log["response_key"] = response_key
        query_log["answer_preview"] = selected_response[:100]
        query_log["status"] = "domain_response"
        logger.info(json.dumps(query_log))
        
        # Send the selected response
        dispatcher.utter_message(text=selected_response)
        
        # Trigger advice system after answer
        self._give_contextual_advice(dispatcher, tracker, topic or intent, user_message_lower)
        
        return []
    
    def _give_contextual_advice(self, dispatcher, tracker, matched_category, user_message_lower):
        """Give contextual advice/appreciation based on matched category and user message."""
        # Advice map for different intent categories
        advice_map = {
            'ask_portal_anomaly': [
                "💡 Tip: Set up email alerts for critical anomalies to catch issues early!",
                "💡 Tip: Review anomalies weekly - quick action prevents energy waste.",
                "💡 Tip: Fine-tune thresholds per machine to reduce false positives."
            ],
            'ask_concept_baseline': [
                "💡 Tip: Retrain baselines quarterly or after major production changes.",
                "💡 Tip: Check R² score - aim for >0.85 for reliable predictions.",
                "💡 Tip: Exclude anomalies when training for better model accuracy."
            ],
            'ask_portal_kpi': [
                "💡 Tip: Export KPI reports weekly to track trends over time.",
                "💡 Tip: Focus on improving load factor to reduce demand charges.",
                "💡 Tip: SEC (specific energy consumption) is key for efficiency tracking."
            ],
            'ask_portal_forecast': [
                "💡 Tip: Use forecasts to schedule high-load operations during low-cost periods.",
                "💡 Tip: ARIMA works best for short-term, Prophet for seasonal patterns.",
                "💡 Tip: Validate forecasts monthly - retrain if accuracy drops below 85%."
            ],
            'ask_significant_energy_use': [
                "💡 Tip: Focus on SEUs first - 80/20 rule applies to energy management.",
                "💡 Tip: Monitor top 3 energy consumers daily for maximum impact."
            ],
            'ask_grafana_environmental': [
                "💡 Tip: Track carbon intensity (kg CO₂/kWh) to measure true environmental impact.",
                "💡 Tip: Set carbon reduction targets aligned with your ISO 50001 goals."
            ],
            'ask_concept_peakdemand': [
                "💡 Tip: Peak demand charges can be 30-50% of your bill - worth managing!",
                "💡 Tip: Stagger equipment startups to avoid simultaneous peak loads."
            ],
            'ask_troubleshooting': [
                "💡 Tip: Check our comprehensive troubleshooting guide first - covers 90% of issues.",
                "💡 Tip: Hard refresh (Ctrl+F5) solves most UI rendering issues."
            ]
        }
        
        # Check if matched category has advice
        if matched_category in advice_map:
            advice = random.choice(advice_map[matched_category])
            dispatcher.utter_message(text=advice)
        
        # Appreciation triggers for positive actions
        appreciation_keywords = ['fix', 'reduce', 'improve', 'train', 'invest', 'achieve']
        if any(keyword in user_message_lower for keyword in appreciation_keywords):
            appreciation_messages = [
                "🌟 Great work! Actions like this directly improve your energy performance.",
                "👏 Excellent! This is exactly the proactive approach ISO 50001 encourages.",
                "🎯 Well done! Continuous improvement is key to energy management success.",
                "💪 Outstanding! Your team's commitment to efficiency is commendable."
            ]
            dispatcher.utter_message(text=random.choice(appreciation_messages))
    
    def _extract_keywords(self, text: str) -> set:
        """Extract important keywords from text, filtering out stop words."""
        # Stop words listesi
        stop_words = {
            'what', 'is', 'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
            'of', 'with', 'by', 'from', 'as', 'are', 'was', 'were', 'been', 'be', 'have', 'has', 
            'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'may', 'might', 'must',
            'can', 'this', 'that', 'these', 'those', 'it', 'its', 'they', 'them', 'their', 'there',
            'when', 'where', 'why', 'how', 'which', 'who', 'whom', 'whose', 'about', 'into', 'onto',
            'if', 'then', 'than', 'so', 'such', 'more', 'most', 'very', 'just', 'only', 'also',
            'must', 'shall', 'should', 'may', 'might', 'can', 'could', 'will', 'would'
        }
        
        # Metni temizle ve kelimelere ayır
        words = re.findall(r'\b[a-z]+\b', text.lower())
        # Stop words'leri filtrele ve 2+ harfli kelimeleri al
        keywords = {w for w in words if w not in stop_words and len(w) > 2}
        return keywords
    
    def _calculate_question_type_score(self, user_q: str, db_q: str) -> float:
        """Calculate score based on question type matching (what, how, when, etc.)."""
        question_words = {'what', 'how', 'when', 'where', 'why', 'who', 'which', 'whom', 'whose'}
        
        user_q_words = set(re.findall(r'\b\w+\b', user_q.lower()))
        db_q_words = set(re.findall(r'\b\w+\b', db_q.lower()))
        
        user_q_type = user_q_words & question_words
        db_q_type = db_q_words & question_words
        
        if user_q_type and db_q_type:
            if user_q_type == db_q_type:
                return 0.2  # Aynı soru tipi bonusu
        return 0.0
    
    def _calculate_keyword_score(self, user_keywords: set, question_keywords: set, 
                                 user_message: str, question: str) -> float:
        """Calculate keyword-based similarity score with weighted importance."""
        if not user_keywords or not question_keywords:
            return 0.0
        
        # Ortak kelimeler
        common = user_keywords & question_keywords
        if not common:
            return 0.0
        
        # Önemli terimler (daha uzun kelimeler ve teknik terimler)
        important_terms = {
            'energy', 'management', 'system', 'performance', 'baseline', 'enpi', 'enpis',
            'objective', 'target', 'action', 'plan', 'review', 'audit', 'policy', 'requirement',
            'significant', 'consumption', 'efficiency', 'improvement', 'continual', 'organization',
            'monitoring', 'measurement', 'compliance', 'legal', 'documentation', 'record',
            'corrective', 'preventive', 'nonconformity', 'procurement', 'design', 'operational',
            'control', 'communication', 'competence', 'training', 'awareness', 'scope', 'boundary'
        }
        
        # Jaccard similarity
        union = user_keywords | question_keywords
        jaccard = len(common) / len(union) if union else 0.0
        
        # Önemli terimler için bonus
        important_matches = common & important_terms
        important_bonus = len(important_matches) * 0.1
        
        # Kelime sırası benzerliği (bigram)
        user_bigrams = set(zip(user_message.split()[:-1], user_message.split()[1:]))
        question_bigrams = set(zip(question.split()[:-1], question.split()[1:]))
        if user_bigrams and question_bigrams:
            bigram_overlap = len(user_bigrams & question_bigrams) / len(user_bigrams | question_bigrams)
            jaccard = max(jaccard, bigram_overlap * 0.7)
        
        return min(jaccard + important_bonus, 1.0)
    
    def _calculate_specificity_bonus(self, user_message: str, question: str) -> float:
        """Calculate bonus for specific question types and patterns."""
        bonus = 0.0
        
        # Soru başlangıcı eşleşmesi - ÇOK ÖNEMLİ
        user_start_words = user_message.split()[:5]  # İlk 5 kelime
        question_start_words = question.split()[:5]
        if len(user_start_words) >= 3 and len(question_start_words) >= 3:
            # İlk 3 kelime eşleşiyorsa büyük bonus
            if user_start_words[:3] == question_start_words[:3]:
                bonus += 0.4
            elif user_start_words[:2] == question_start_words[:2]:
                bonus += 0.3
            elif user_start_words[0] == question_start_words[0]:
                bonus += 0.15
        
        # "What is X?" gibi genel sorular için definition sorularına öncelik
        if re.match(r'^what is\s+\w+', user_message):
            if 'definition' in question or 'define' in question or 'fundamental' in question:
                bonus += 0.3
            if 'what is' in question and 'definition' in question:
                bonus += 0.2
        
        # "What is the primary objective" gibi spesifik sorular
        if 'primary objective' in user_message:
            if 'primary objective' in question:
                bonus += 0.5  # Çok yüksek bonus
            elif 'objective' in question:
                bonus += 0.2
        
        # "To what variables" gibi spesifik sorular
        if 'variables' in user_message and 'applicable' in user_message:
            if 'variables' in question and 'applicable' in question:
                bonus += 0.5
            elif 'variables' in question:
                bonus += 0.3
        
        # "For what purposes" gibi spesifik sorular
        if 'for what purposes' in user_message or 'what purposes' in user_message:
            if 'purposes' in question:
                bonus += 0.4
        
        # "What must X include?" gibi sorular için "include" içeren sorulara öncelik
        if 'must' in user_message and 'include' in user_message:
            if 'include' in question:
                bonus += 0.25
                # Aynı zamanda "must" varsa ekstra bonus
                if 'must' in question:
                    bonus += 0.15
        
        # "How" soruları için "how" içeren sorulara öncelik
        if user_message.startswith('how'):
            if question.startswith('how'):
                bonus += 0.2
        
        # "When" soruları için "when" içeren sorulara öncelik
        if user_message.startswith('when'):
            if question.startswith('when'):
                bonus += 0.2
        
        # "Define" veya "Explain" ile başlayan sorular
        if user_message.startswith('define') or user_message.startswith('explain'):
            if question.startswith('define') or question.startswith('explain'):
                bonus += 0.3
        
        # Kullanıcı sorusundaki anahtar terimler soruda geçiyorsa bonus
        user_important_terms = {'definition', 'purpose', 'requirement', 'must', 'shall', 
                               'include', 'establish', 'maintain', 'implement', 'objective',
                               'variables', 'applicable', 'purposes', 'scope', 'boundary'}
        user_terms_in_msg = {term for term in user_important_terms if term in user_message}
        question_terms = {term for term in user_important_terms if term in question}
        if user_terms_in_msg and question_terms:
            common_important = user_terms_in_msg & question_terms
            bonus += len(common_important) * 0.15  # Artırıldı
        
        return min(bonus, 0.8)  # Maksimum 0.8 bonus (artırıldı)

    def _find_exact_answer(self, user_message: str):
        """Find an exact question match across all categories."""
        normalized = user_message.strip().lower()
        if not normalized:
            return None, None
        for category, qa_dict in QA_DATA.items():
            if normalized in qa_dict:
                return category, qa_dict[normalized]
        return None, None

    def _resolve_special_case(self, user_message: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Handle queries that need explicit scope or live-data routing."""
        redirect_response = self._build_operational_redirect(user_message)
        if redirect_response:
            return "ovos_redirect", redirect_response, "redirect"

        capability_response = self._build_capability_response(user_message)
        if capability_response:
            return "ask_chatbot_scope", capability_response, "special_case"

        return None, None, None

    def _build_capability_response(self, user_message: str) -> Optional[str]:
        """Explain the chatbot's role when the user asks about its scope."""
        if any(term in user_message for term in ["humanenerdia", "platform"]):
            return None

        capability_phrases = [
            "what can you help me with",
            "how can you help",
            "what can i ask you",
            "what can i ask",
            "what do you do",
            "what is this chatbot",
            "what are you for",
        ]

        if any(phrase in user_message for phrase in capability_phrases):
            return (
                "I can help with ISO 50001 explanations, HumanEnerDIA page guidance, reports, "
                "baseline and anomaly concepts, and common troubleshooting. For live machine status, "
                "current energy values, top consumers, or active alerts, use the OVOS assistant or the live dashboards."
            )

        return None

    def _build_operational_redirect(self, user_message: str) -> Optional[str]:
        """Redirect live operational questions to OVOS instead of guessing."""
        ranking_phrases = [
            "top consumer",
            "most electricity",
            "most energy",
            "highest consumption",
            "which machine is using the most",
            "which machine uses the most",
            "which machine consumed the most",
            "any active alerts",
            "any alerts right now",
            "active anomalies right now",
        ]
        time_markers = ["right now", "currently", "current", "today", "live", "at the moment"]
        operational_markers = [
            "status",
            "running",
            "offline",
            "online",
            "consumption",
            "power",
            "energy",
            "cost",
            "alert",
            "alerts",
            "anomaly",
            "anomalies",
            "using",
        ]
        machine_pattern = re.search(
            r"\b(compressor|hvac|boiler|conveyor|pump|cnc|furnace|dryer|packaging|machine|factory)([-_ ]?[a-z0-9]+)?\b",
            user_message,
        )

        has_ranking_phrase = any(phrase in user_message for phrase in ranking_phrases)
        has_time_marker = any(marker in user_message for marker in time_markers)
        has_operational_marker = any(marker in user_message for marker in operational_markers)
        has_machine_reference = bool(machine_pattern)

        if has_ranking_phrase or (has_machine_reference and has_time_marker and has_operational_marker):
            return (
                "That sounds like a live operational query. This text assistant focuses on ISO 50001, "
                "HumanEnerDIA how-to guidance, reports, and troubleshooting. For current machine status, "
                "live energy values, top consumers, or active alerts, use the OVOS assistant or the live dashboards."
            )

        return None

    def _should_merge_answers(self, user_message: str, category: Optional[str] = None) -> bool:
        """Keep portal help and troubleshooting answers focused instead of stitching multiple replies."""
        if category and (
            category.startswith("ask_portal_")
            or category in {"ask_humenerdia_platform", "ask_getting_started", "ask_troubleshooting"}
        ):
            return False

        no_merge_phrases = [
            "how do i",
            "how to",
            "what can you help",
            "what can i ask",
            "what do you do",
            "what is this chatbot",
            "why is my",
            "not showing data",
            "current ",
            "right now",
            "today",
            "status of",
            "which machine",
            "show me",
            "open",
            "navigate",
        ]
        if any(phrase in user_message for phrase in no_merge_phrases):
            return False

        merge_phrases = [
            "what is",
            "define",
            "explain",
            "difference between",
            "how does",
            "what does",
            "purpose of",
        ]
        return any(phrase in user_message for phrase in merge_phrases)
    
    def _find_best_answer(self, user_message: str, qa_dict: Dict[str, str], category: Optional[str] = None) -> str:
        """Find the best matching answer using improved similarity matching."""
        if not qa_dict:
            return None
        
        # Önce tam eşleşme ara
        if user_message in qa_dict:
            return qa_dict[user_message]
        
        # Kullanıcı mesajından anahtar kelimeleri çıkar
        user_keywords = self._extract_keywords(user_message)
        
        # Her soru için skor hesapla
        scored_questions = []
        
        for question, answer in qa_dict.items():
            score = 0.0
            
            # 1. Tam metin benzerliği (SequenceMatcher) - daha yüksek ağırlık
            text_similarity = SequenceMatcher(None, user_message, question).ratio()
            score += text_similarity * 0.6  # Daha da artırıldı
            
            # 2. Soru tipi eşleşmesi
            question_type_score = self._calculate_question_type_score(user_message, question)
            score += question_type_score
            
            # 3. Anahtar kelime benzerliği
            question_keywords = self._extract_keywords(question)
            keyword_score = self._calculate_keyword_score(user_keywords, question_keywords, 
                                                         user_message, question)
            score += keyword_score * 0.5  # Artırıldı
            
            # 4. Spesifiklik bonusu
            specificity_bonus = self._calculate_specificity_bonus(user_message, question)
            score += specificity_bonus
            
            # 5. Özel terim eşleşmesi (tam eşleşme bonusu) - ÖNEMLİ
            user_terms = set(re.findall(r'\b[a-z]+\b', user_message.lower()))
            question_terms = set(re.findall(r'\b[a-z]+\b', question.lower()))
            exact_term_matches = user_terms & question_terms
            
            # Önemli terimler (daha yüksek ağırlık)
            important_terms = {
                'iso', 'standard', 'scope', 'boundary', 'benchmark', 'pdca', 'audit',
                'energy', 'performance', 'baseline', 'enpi', 'policy', 'planning',
                'management', 'review', 'implementation', 'checking', 'objective', 'target',
                'efficiency', 'consumption', 'continual', 'improvement', 'corrective', 'preventive'
            }
            important_matches = exact_term_matches & important_terms
            
            # Kullanıcı sorusundaki önemli terimler soruda varsa büyük bonus
            if len(important_matches) >= 2:
                score += 0.3  # Artırıldı
            elif len(important_matches) >= 1:
                score += 0.2  # Artırıldı
            
            # Spesifik terim eşleşmesi - çok önemli (örn: "energy efficiency" hem soruda hem cevapta)
            specific_phrases = ['energy efficiency', 'energy baseline', 'energy performance', 'continual improvement',
                              'corrective action', 'preventive action', 'energy review', 'energy policy',
                              'energy objective', 'energy target', 'significant energy use', 'energy consumption',
                              'exactly is meant by energy', 'what exactly is meant by', 'exactly is meant by',
                              'scope', 'boundary', 'boundaries', 'scope and boundary', 'scope and boundaries']
            for phrase in specific_phrases:
                if phrase in user_message.lower() and phrase in question.lower():
                    score += 0.5  # Çok yüksek bonus
                    break
            
            # Scope/boundary soruları için özel bonus - ÇOK ÖNEMLİ
            scope_keywords = ['scope', 'boundary', 'boundaries']
            user_has_scope = any(keyword in user_message.lower() for keyword in scope_keywords)
            question_has_scope = any(keyword in question.lower() for keyword in scope_keywords)
            if user_has_scope and question_has_scope:
                # Her iki tarafta da scope/boundary varsa büyük bonus
                score += 0.4  # Scope soruları için özel bonus
                # Eğer aynı scope keyword'ü varsa ekstra bonus
                for keyword in scope_keywords:
                    if keyword in user_message.lower() and keyword in question.lower():
                        score += 0.2
                        break
            
            # Tam ifade eşleşmesi - en yüksek öncelik
            # Kullanıcı sorusundaki önemli ifadeler soruda tam olarak geçiyorsa
            user_important_phrases = []
            if 'exactly is meant by' in user_message.lower():
                user_important_phrases.append('exactly is meant by')
            if 'what is' in user_message.lower()[:10]:
                user_important_phrases.append('what is')
            if 'define' in user_message.lower()[:10]:
                user_important_phrases.append('define')
            if 'explain' in user_message.lower()[:10]:
                user_important_phrases.append('explain')
            
            for phrase in user_important_phrases:
                if phrase in question.lower():
                    score += 0.3
                    break
            
            # Genel terim eşleşmesi
            if len(exact_term_matches) >= len(user_terms) * 0.7:  # %70+ eşleşme (artırıldı)
                score += 0.25  # Artırıldı
            elif len(exact_term_matches) >= len(user_terms) * 0.5:  # %50+ eşleşme
                score += 0.18
            elif len(exact_term_matches) >= 4:  # En az 4 terim eşleşmesi
                score += 0.12
            
            # 6. Soru başlangıcı benzerliği (ilk birkaç kelime) - ÇOK ÖNEMLİ
            user_words = user_message.split()
            question_words = question.split()
            
            # İlk 3-6 kelimeyi karşılaştır
            for i in range(3, 7):
                if len(user_words) >= i and len(question_words) >= i:
                    user_start = ' '.join(user_words[:i])
                    question_start = ' '.join(question_words[:i])
                    if user_start.lower() == question_start.lower():
                        score += 0.5 / (i - 2)  # İlk kelimeler çok daha önemli
                        break
                    elif user_start.lower() in question_start.lower() or question_start.lower() in user_start.lower():
                        score += 0.25 / (i - 2)
                        break
            
            # İlk kelime eşleşmesi - ekstra bonus
            if len(user_words) > 0 and len(question_words) > 0:
                if user_words[0].lower() == question_words[0].lower():
                    score += 0.2
            
            # 7. Soru uzunluğu benzerliği
            length_ratio = min(len(user_message), len(question)) / max(len(user_message), len(question))
            if length_ratio > 0.7:  # 0.6'dan 0.7'ye çıkarıldı
                score += 0.05
            
            # 8. Soru ortası ve sonu benzerliği (yeni)
            user_words = user_message.split()
            question_words = question.split()
            if len(user_words) > 4 and len(question_words) > 4:
                # Ortadaki kelimeleri kontrol et
                user_middle = ' '.join(user_words[2:-2])
                question_middle = ' '.join(question_words[2:-2])
                if user_middle and question_middle:
                    middle_similarity = SequenceMatcher(None, user_middle.lower(), question_middle.lower()).ratio()
                    if middle_similarity > 0.5:
                        score += middle_similarity * 0.15
            
            scored_questions.append((score, question, answer))
        
        # En yüksek skorlu soruları sırala
        scored_questions.sort(reverse=True, key=lambda x: x[0])
        
        if scored_questions:
            best_score, best_question, best_answer = scored_questions[0]
            
            # Minimum eşik değeri - dinamik olarak ayarla
            # Scope/boundary soruları için daha düşük eşik
            scope_keywords = ['scope', 'boundary', 'boundaries']
            user_has_scope = any(keyword in user_message.lower() for keyword in scope_keywords)
            question_has_scope = any(keyword in best_question.lower() for keyword in scope_keywords)
            
            # Eğer soru başlangıcı çok benziyorsa eşiği düşür
            user_start = ' '.join(user_message.split()[:3])
            question_start = ' '.join(best_question.split()[:3])
            threshold = 0.25
            
            # Scope soruları için eşiği düşür
            if user_has_scope or question_has_scope:
                threshold = 0.20  # Scope soruları için daha düşük eşik
                if user_has_scope and question_has_scope:
                    threshold = 0.15  # Her iki tarafta da scope varsa daha da düşük
            
            if user_start.lower() == question_start.lower():
                threshold = min(threshold, 0.15)  # Soru başlangıcı aynıysa eşiği düşür
            elif user_start.lower() in question_start.lower() or question_start.lower() in user_start.lower():
                threshold = min(threshold, 0.20)
            
            if best_score >= threshold:
                if not self._should_merge_answers(user_message, category):
                    return best_answer

                # Daha kapsamlı cevap için: yüksek skorlu birden fazla sorunun cevabını birleştir
                # Ana cevabın sonunda nokta olduğundan emin ol
                comprehensive_answer = best_answer.strip()
                if comprehensive_answer and not comprehensive_answer.endswith('.'):
                    comprehensive_answer += '.'
                
                # Top 3-5 sorudan benzer olanları birleştir
                additional_answers = []
                for i in range(1, min(5, len(scored_questions))):
                    score, question, answer = scored_questions[i]
                    
                    # Sadece yeterince yüksek skorlu ve farklı cevapları ekle
                    # En az threshold*0.7 skora sahip olmalı ve cevap farklı olmalı
                    if score >= threshold * 0.7:
                        # Cevabı temizle ve normalize et
                        answer_clean = answer.strip()
                        answer_normalized = answer_clean.lower()
                        best_answer_normalized = best_answer.lower().strip()
                        
                        # Eğer cevap tamamen farklıysa ve çok benzer değilse ekle
                        if answer_normalized != best_answer_normalized:
                            # Cevapların benzerlik oranını kontrol et
                            similarity = SequenceMatcher(None, answer_normalized, best_answer_normalized).ratio()
                            
                            # %70'den az benzer ve yeterince farklıysa ekle (eşik düşürüldü)
                            if similarity < 0.70:
                                # Çok kısa cevapları ekleme (5 kelimeden az)
                                if len(answer_clean.split()) >= 5:
                                    # Cevabın tam olduğundan emin ol
                                    if not answer_clean.endswith('.'):
                                        answer_clean += '.'
                                    additional_answers.append(answer_clean)
                    else:
                        break  # Skorlar çok düştüyse durdur
                
                # Ek cevaplar varsa birleştir
                if additional_answers:
                    # İlk cevabı ana cevap olarak kullan
                    # Diğer cevapları doğrudan ekle (nokta ile ayrılmış)
                    for additional in additional_answers[:2]:  # Maksimum 2 ek cevap
                        # Cevabı doğrudan ekle (her cevap zaten nokta ile bitiyor)
                        comprehensive_answer += f" {additional}"
                
                return comprehensive_answer
        
        return None
    
    def _select_best_response(self, user_message: str, responses: List[Dict], intent: str) -> str:
        """Select the best response based on keywords in the user's question."""
        
        # Keyword mappings: keywords that indicate which response index to prefer
        keyword_mappings = {
            "ask_management_responsibility": {
                0: ["resources", "commitment", "fundamental", "specific resources", "provide", "human", "skills", "technology", "financial"],
                1: ["representative", "management representative", "responsibilities", "team", "composition", "size", "report", "two key areas", "appointing"],
            },
            "ask_energy_policy": {
                0: ["three primary", "commitments", "continual improvement", "resources", "compliance", "legal requirements", "documented", "communicated"],
                1: ["framework", "setting goals", "reviewing", "objectives", "targets", "purchase", "procurement", "design", "products", "services"],
            },
            "ask_energy_planning": {
                0: ["overall goal", "output", "process", "baseline", "enpis", "objectives", "targets", "action plans"],
                1: ["legal requirements", "energy review", "significant energy uses", "baselines", "enpis", "analyze", "identifying"],
            },
            "ask_energy_baseline": {
                0: ["quantitative reference", "characteristics", "time", "normalized", "adjusted", "variables", "production", "temperature", "degree days"],
                1: ["establish", "information", "initial energy review", "data period", "suitable", "adjustments", "three specific conditions", "regulatory"],
            },
            "ask_enpi": {
                0: ["purpose", "monitoring", "measuring", "methodology", "recorded", "reviewed", "identified", "appropriate"],
                1: ["quantitative values", "expressed", "metric", "ratio", "model", "simple", "complex", "consumption per unit"],
            },
        }
        
        # Get keyword mapping for this intent
        keyword_map = keyword_mappings.get(intent, {})
        
        # Score each response based on keyword matches
        scores = [0] * len(responses)
        
        for response_index, keywords in keyword_map.items():
            if response_index < len(responses):
                for keyword in keywords:
                    if keyword in user_message:
                        scores[response_index] += 2
                    # Also check if keyword appears in response text
                    response_text = responses[response_index].get("text", "").lower()
                    if keyword in response_text:
                        scores[response_index] += 1
        
        # If we have scores, select the response with highest score
        if max(scores) > 0:
            best_index = scores.index(max(scores))
            return responses[best_index].get("text", "")
        
        # Fallback: Use hash of user message to consistently select same response for same question
        # This provides variety while being deterministic
        message_hash = abs(hash(user_message)) % len(responses)
        return responses[message_hash].get("text", "")


class ActionGiveAdvice(Action):
    """Proactive advice system that provides contextual tips and appreciates positive actions.
    Fulfills WASABI proposal commitment to 'warn & advise users for resource efficiency'."""
    
    def name(self) -> Text:
        return "action_give_advice"
    
    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        intent = tracker.latest_message.get('intent', {}).get('name', '')
        user_message = tracker.latest_message.get('text', '').lower()
        
        # Advice map: contextual tips per intent
        advice_map = {
            'ask_portal_anomaly': [
                "💡 **Proactive Tip:** Regular anomaly monitoring prevents energy waste. Set up email alerts for critical anomalies to catch issues early!",
                "💡 **Best Practice:** Review anomalies within 4 hours to minimize wasted energy. Quick action = better savings.",
                "💡 **Advice:** Consider adjusting thresholds per machine - critical equipment benefits from stricter monitoring (1.5σ instead of 2σ)."
            ],
            'ask_energy_baseline': [
                "💡 **Energy Tip:** Retrain your baseline every quarter or after major operational changes for accurate predictions and reliable EnPI tracking.",
                "💡 **Best Practice:** A baseline with R² > 0.8 is good for ISO 50001. Below 0.7? Add more drivers or extend your training period.",
                "💡 **Advice:** Exclude anomalies from training data to prevent skewed models. Enable 'Exclude Anomalies' in training settings."
            ],
            'ask_portal_kpi': [
                "💡 **Performance Tip:** Export KPI reports weekly to track trends and share with management for data-driven decisions.",
                "💡 **Efficiency Advice:** Load Factor > 70% is good. Below that? Consider load scheduling to smooth out peaks and reduce demand charges.",
                "💡 **Best Practice:** Monitor SEC (Specific Energy Consumption) as your primary efficiency metric - it accounts for production volume changes."
            ],
            'ask_portal_forecast': [
                "💡 **Planning Tip:** Use Optimal Load Scheduling to shift energy-intensive tasks to off-peak hours and save 15-30% on demand charges!",
                "💡 **Forecast Advice:** ARIMA for short-term (1-4h), Prophet for medium-term (24h-7d). Different tools for different needs.",
                "💡 **Best Practice:** Validate forecast accuracy monthly. High MAPE (>15%)? Retrain your models with recent data."
            ],
            'ask_concept_seu': [
                "💡 **ISO 50001 Tip:** Focus improvement efforts on SEUs (Significant Energy Uses) - typically 20% of equipment accounts for 80% of consumption.",
                "💡 **Efficiency Advice:** Identify your top 3 energy consumers and monitor them closely. Small improvements here = big impact."
            ],
            'ask_grafana_environmental': [
                "💡 **Sustainability Tip:** Track carbon intensity (kg CO2/unit) not just total emissions. Production-normalized metrics show true efficiency gains.",
                "💡 **Green Advice:** Set carbon reduction targets in Settings → Environmental. Dashboard tracks progress automatically for ESG reporting."
            ],
            'ask_concept_peakdemand': [
                "💡 **Cost Warning:** Peak demand charges can be 30-50% of your electricity bill! A single spike affects the entire month.",
                "💡 **Savings Tip:** Stagger equipment startups by 5-10 minutes to avoid simultaneous peaks. Simple change, major savings."
            ],
            'ask_troubleshooting': [
                "💡 **Support Tip:** Check our comprehensive troubleshooting guide first - covers 90% of common issues. Saves time and gets you back online faster!",
                "💡 **Performance Advice:** If dashboards are slow, check your time range - shorter periods (24h vs 30d) load faster."
            ],
        }
        
        # Appreciation messages for positive actions
        appreciation_triggers = {
            'fix': ["🌟 **Great work!** Fixing issues promptly prevents energy waste and maintains system efficiency.",
                   "👏 **Excellent action!** Quick problem resolution is exactly what ISO 50001 encourages."],
            'reduc': ["🎉 **Congratulations!** Reducing energy consumption shows commitment to sustainability and cost savings.",
                     "🌟 **Well done!** Energy reduction initiatives directly improve your carbon footprint."],
            'improv': ["👏 **Fantastic!** Continuous improvement is the cornerstone of effective energy management.",
                      "🌟 **Excellent progress!** Proactive improvements lead to significant long-term savings."],
            'train': ["🎯 **Smart move!** Regular model retraining ensures accurate predictions and reliable baseline tracking.",
                     "👏 **Good practice!** Keeping models updated is key to maintaining system effectiveness."],
            'invest': ["🌟 **Great decision!** Investing in efficiency improvements has both environmental and economic benefits.",
                      "👏 **Forward thinking!** Energy efficiency projects typically pay back within 2-3 years."],
            'achiev': ["🎉 **Milestone reached!** Celebrating achievements keeps teams motivated for further improvements.",
                      "🌟 **Outstanding!** Recognizing progress is essential for maintaining energy management momentum."],
        }
        
        # Check if user message indicates positive action (appreciation)
        for trigger, messages in appreciation_triggers.items():
            if trigger in user_message:
                dispatcher.utter_message(text=random.choice(messages))
                return []
        
        # Provide contextual advice based on intent
        if intent in advice_map:
            advice = random.choice(advice_map[intent])
            dispatcher.utter_message(text=advice)
        
        return []
