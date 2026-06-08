"""
EnMS - Factory Simulator Service
MQTT Publisher Module
"""

import json
import logging
import paho.mqtt.client as mqtt
from typing import Dict, Any, Optional
from datetime import datetime
from config import settings

logger = logging.getLogger(__name__)


class MQTTPublisher:
    """MQTT Publisher for factory data"""
    
    def __init__(self):
        self.client: Optional[mqtt.Client] = None
        self.connected = False
        self.messages_published = 0
        self.connection_errors = 0
        
    def connect(self) -> bool:
        """Connect to MQTT broker"""
        try:
            # Create MQTT client
            self.client = mqtt.Client(
                client_id=settings.MQTT_CLIENT_ID,
                clean_session=True,
                protocol=mqtt.MQTTv311
            )
            
            # Set username and password
            self.client.username_pw_set(
                settings.MQTT_USERNAME,
                settings.MQTT_PASSWORD
            )
            
            # Set callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_publish = self._on_publish
            
            # Connect to broker
            logger.info(f"Connecting to MQTT broker at {settings.MQTT_HOST}:{settings.MQTT_PORT}")
            self.client.connect(
                settings.MQTT_HOST,
                settings.MQTT_PORT,
                settings.MQTT_KEEPALIVE
            )
            
            # Start network loop in background
            self.client.loop_start()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            self.connection_errors += 1
            return False
    
    def disconnect(self):
        """Disconnect from MQTT broker"""
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
                logger.info("Disconnected from MQTT broker")
            except Exception as e:
                logger.error(f"Error disconnecting from MQTT: {e}")
        
        self.connected = False
    
    def publish(self, topic: str, payload: Dict[str, Any], retain: bool = False) -> bool:
        """
        Publish message to MQTT broker
        
        Args:
            topic: MQTT topic
            payload: Message payload (will be JSON-encoded)
            retain: Whether to retain the message
            
        Returns:
            True if published successfully
        """
        if not self.connected:
            logger.warning("Not connected to MQTT broker. Attempting to reconnect...")
            if not self.connect():
                return False
        
        try:
            # Convert datetime objects to ISO format strings
            payload_str = self._serialize_payload(payload)
            
            # Publish message
            result = self.client.publish(
                topic,
                payload_str,
                qos=settings.MQTT_QOS,
                retain=retain
            )
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.messages_published += 1
                logger.debug(f"Published to {topic}")
                return True
            else:
                logger.error(f"Failed to publish to {topic}: {result.rc}")
                return False
                
        except Exception as e:
            logger.error(f"Error publishing message: {e}")
            return False
    
    def publish_energy_reading(self, machine_id: str, mqtt_topic: str, data: Dict[str, Any]) -> bool:
        """Publish energy reading (electricity only - legacy)"""
        return self.publish(f"{mqtt_topic}/energy", data)
    
    def publish_multi_energy_reading(self, machine_id: str, mqtt_topic: str, sensor_data: Dict[str, Any]) -> bool:
        """
        Publish multi-energy readings to separate topics.
        Detects energy types in sensor_data and publishes each separately.
        
        Supports:
        - Electricity: power_kw, energy_kwh, voltage_v, current_a
        - Natural Gas: flow_rate_m3h, consumption_m3, pressure_bar
        - Steam: flow_rate_kg_h, consumption_kg, steam_pressure_bar
        """
        published_count = 0
        
        # Extract timestamp (should be in all sensor data)
        timestamp = sensor_data.get('timestamp', datetime.utcnow().isoformat())
        
        # Publish electricity data (if present)
        if 'power_kw' in sensor_data:
            electricity_payload = {
                'timestamp': timestamp,
                'machine_id': machine_id,
                'power_kw': sensor_data['power_kw'],
                'energy_kwh': sensor_data.get('energy_kwh', 0),
                'voltage_v': sensor_data.get('voltage_v'),
                'current_a': sensor_data.get('current_a'),
                'power_factor': sensor_data.get('power_factor', 0.95)
            }
            if self.publish(f"{mqtt_topic}/electricity", electricity_payload):
                published_count += 1
        
        # Publish natural gas data (if present)
        if 'flow_rate_m3h' in sensor_data or 'natural_gas_m3h' in sensor_data:
            gas_payload = {
                'timestamp': timestamp,
                'machine_id': machine_id,
                'flow_rate_m3h': sensor_data.get('flow_rate_m3h', sensor_data.get('natural_gas_m3h', 0)),
                'consumption_m3': sensor_data.get('consumption_m3', sensor_data.get('natural_gas_m3', 0)),
                'pressure_bar': sensor_data.get('pressure_bar', sensor_data.get('gas_pressure_bar')),
                'temperature_c': sensor_data.get('temperature_c', sensor_data.get('gas_temp_c')),
                'calorific_value_kwh_m3': sensor_data.get('calorific_value_kwh_m3', 10.55)
            }
            if self.publish(f"{mqtt_topic}/natural_gas", gas_payload):
                published_count += 1
        
        # Publish steam data (if present)
        if 'flow_rate_kg_h' in sensor_data or 'steam_production_kgh' in sensor_data:
            steam_payload = {
                'timestamp': timestamp,
                'machine_id': machine_id,
                'flow_rate_kg_h': sensor_data.get('flow_rate_kg_h', sensor_data.get('steam_production_kgh', 0)),
                'consumption_kg': sensor_data.get('consumption_kg', sensor_data.get('steam_production_kg', 0)),
                'pressure_bar': sensor_data.get('steam_pressure_bar', sensor_data.get('pressure_bar')),
                'temperature_c': sensor_data.get('steam_temperature_c', sensor_data.get('steam_temp_c')),
                'enthalpy_kj_kg': sensor_data.get('enthalpy_kj_kg')
            }
            if self.publish(f"{mqtt_topic}/steam", steam_payload):
                published_count += 1
        
        return published_count > 0
    
    def publish_production_data(self, machine_id: str, mqtt_topic: str, data: Dict[str, Any]) -> bool:
        """Publish production data"""
        return self.publish(f"{mqtt_topic}/production", data)
    
    def publish_environmental_data(self, machine_id: str, mqtt_topic: str, data: Dict[str, Any]) -> bool:
        """Publish environmental data"""
        return self.publish(f"{mqtt_topic}/environmental", data)
    
    def publish_machine_status(self, machine_id: str, mqtt_topic: str, data: Dict[str, Any]) -> bool:
        """Publish machine status (retained message)"""
        return self.publish(f"{mqtt_topic}/status", data, retain=True)
    
    def _serialize_payload(self, payload: Dict[str, Any]) -> str:
        """Serialize payload to JSON, handling datetime objects"""
        def default_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")
        
        return json.dumps(payload, default=default_serializer)
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connected to MQTT broker"""
        if rc == 0:
            self.connected = True
            logger.info(f"Connected to MQTT broker successfully")
        else:
            self.connected = False
            logger.error(f"Failed to connect to MQTT broker. Return code: {rc}")
            self.connection_errors += 1
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback when disconnected from MQTT broker"""
        self.connected = False
        if rc != 0:
            logger.warning(f"Unexpected MQTT disconnection. Return code: {rc}")
        else:
            logger.info("Disconnected from MQTT broker")
    
    def _on_publish(self, client, userdata, mid):
        """Callback when message is published"""
        logger.debug(f"Message {mid} published")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get publisher statistics"""
        return {
            "connected": self.connected,
            "messages_published": self.messages_published,
            "connection_errors": self.connection_errors,
            "broker": f"{settings.MQTT_HOST}:{settings.MQTT_PORT}"
        }


# Global MQTT publisher instance
mqtt_publisher = MQTTPublisher()