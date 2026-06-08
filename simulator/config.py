"""
EnMS - Factory Simulator Service
Configuration Module
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Service Configuration
    SERVICE_NAME: str = "EnMS Factory Simulator"
    SERVICE_VERSION: str = "1.0.0"
    API_PORT: int = 8003
    LOG_LEVEL: str = "INFO"
    
    # MQTT Configuration - Host Mosquitto Broker
    MQTT_HOST: str = "mqtt"
    MQTT_PORT: int = 1883
    MQTT_USERNAME: str = "enms_mqtt"
    MQTT_PASSWORD: str = ""
    MQTT_KEEPALIVE: int = 60
    MQTT_QOS: int = 1
    MQTT_CLIENT_ID: str = "enms-simulator"
    
    # Database Configuration
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "enms_app"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "enms"
    
    # Simulator Configuration
    SIMULATOR_AUTO_START: bool = True
    SIMULATOR_FACTORIES: int = 1
    SIMULATOR_ENABLE_ANOMALIES: bool = True
    ANOMALY_PROBABILITY: float = 0.10  # 10% chance per day
    
    # Machine Configuration (default intervals in seconds)
    COMPRESSOR_INTERVAL: int = 1
    HVAC_INTERVAL: int = 10
    MOTOR_INTERVAL: int = 10
    PUMP_INTERVAL: int = 30
    INJECTION_MOLDING_INTERVAL: int = 30
    
    # Shift Configuration (24-hour format)
    SHIFT_1_START: int = 6   # 06:00
    SHIFT_1_END: int = 14    # 14:00
    SHIFT_2_START: int = 14  # 14:00
    SHIFT_2_END: int = 22    # 22:00
    SHIFT_3_START: int = 22  # 22:00
    SHIFT_3_END: int = 6     # 06:00
    
    # Production Configuration
    WEEKEND_PRODUCTION_FACTOR: float = 0.3  # 30% production on weekends
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()
