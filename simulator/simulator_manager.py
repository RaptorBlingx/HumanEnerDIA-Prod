"""
EnMS - Factory Simulator Service
Simulator Manager - Orchestrates all machine simulators
"""

import asyncio
import logging
import random
from datetime import datetime
from typing import Dict, List, Optional
import asyncpg

from config import settings
from models import SimulatorStatus, MachineType
from mqtt_publisher import mqtt_publisher
from machines import (
    CompressorSimulator,
    HVACSimulator,
    MotorSimulator,
    HydraulicPumpSimulator,
    InjectionMoldingSimulator,
    BoilerSimulator
)

logger = logging.getLogger(__name__)


class SimulatorManager:
    """Manages all machine simulators and coordinates data generation"""
    
    def __init__(self):
        self.status = SimulatorStatus.STOPPED
        self.machines: Dict[str, any] = {}
        self.tasks: Dict[str, asyncio.Task] = {}
        self.db_pool: Optional[asyncpg.Pool] = None
        self.start_time: Optional[datetime] = None
        
    async def initialize(self):
        """Initialize simulator manager"""
        try:
            # Connect to database
            await self._connect_database()
            
            # Connect to MQTT
            mqtt_publisher.connect()
            
            # Load machines from database
            await self._load_machines()
            
            logger.info(f"Simulator manager initialized with {len(self.machines)} machines")
            
        except Exception as e:
            logger.error(f"Failed to initialize simulator: {e}")
            raise
    
    async def start(self, machine_ids: Optional[List[str]] = None):
        """Start the simulator"""
        if self.status == SimulatorStatus.RUNNING:
            logger.warning("Simulator is already running")
            return
        
        try:
            self.status = SimulatorStatus.STARTING
            self.start_time = datetime.utcnow()
            
            # Start specified machines or all machines
            machines_to_start = machine_ids if machine_ids else list(self.machines.keys())
            
            for machine_id in machines_to_start:
                if machine_id in self.machines:
                    await self._start_machine(machine_id)
            
            self.status = SimulatorStatus.RUNNING
            logger.info(f"Simulator started with {len(machines_to_start)} machines")
            
        except Exception as e:
            logger.error(f"Failed to start simulator: {e}")
            self.status = SimulatorStatus.ERROR
            raise
    
    async def stop(self, machine_ids: Optional[List[str]] = None):
        """Stop the simulator"""
        if self.status == SimulatorStatus.STOPPED:
            logger.warning("Simulator is already stopped")
            return
        
        try:
            self.status = SimulatorStatus.STOPPING
            
            # Stop specified machines or all machines
            machines_to_stop = machine_ids if machine_ids else list(self.machines.keys())
            
            for machine_id in machines_to_stop:
                if machine_id in self.machines:
                    await self._stop_machine(machine_id)
            
            # If all machines stopped, set status to STOPPED
            if not any(m.is_running for m in self.machines.values()):
                self.status = SimulatorStatus.STOPPED
            else:
                self.status = SimulatorStatus.RUNNING
            
            logger.info("Simulator stopped")
            
        except Exception as e:
            logger.error(f"Failed to stop simulator: {e}")
            self.status = SimulatorStatus.ERROR
            raise
    
    async def inject_anomaly(self, machine_id: str, anomaly_type: str, duration_seconds: int, severity: float):
        """Inject an anomaly into a specific machine"""
        if machine_id not in self.machines:
            raise ValueError(f"Machine {machine_id} not found")
        
        machine = self.machines[machine_id]
        machine.inject_anomaly(anomaly_type, duration_seconds, severity)
        logger.info(f"Anomaly injected: {anomaly_type} on {machine.machine_name}")
    
    def get_status(self) -> Dict:
        """Get simulator status"""
        uptime = 0.0
        if self.start_time:
            uptime = (datetime.utcnow() - self.start_time).total_seconds()
        
        running_machines = sum(1 for m in self.machines.values() if m.is_running)
        total_readings = sum(m.readings_generated for m in self.machines.values())
        
        mqtt_stats = mqtt_publisher.get_stats()
        
        return {
            "status": self.status.value,
            "uptime_seconds": uptime,
            "factories_count": 1,  # Currently single factory
            "machines_count": len(self.machines),
            "running_machines": running_machines,
            "total_readings_generated": total_readings,
            "mqtt_connected": mqtt_stats["connected"],
            "mqtt_messages_published": mqtt_stats["messages_published"],
            "configuration": {
                "enable_anomalies": settings.SIMULATOR_ENABLE_ANOMALIES,
                "anomaly_probability": settings.ANOMALY_PROBABILITY,
                "mqtt_broker": f"{settings.MQTT_HOST}:{settings.MQTT_PORT}"
            }
        }
    
    def get_machine_status(self, machine_id: str) -> Optional[Dict]:
        """Get status of a specific machine"""
        if machine_id not in self.machines:
            return None
        
        machine = self.machines[machine_id]
        return machine.get_state()
    
    def get_all_machines_status(self) -> List[Dict]:
        """Get status of all machines"""
        return [machine.get_state() for machine in self.machines.values()]

    def _get_supported_anomaly_types(self, machine) -> List[str]:
        """Return supported anomaly types for automatic injection."""
        machine_type = machine.machine_type.value
        return {
            "compressor": ["leak", "efficiency_loss", "bearing_fault"],
            "hvac": ["refrigerant_leak", "dirty_coils", "compressor_fault"],
            "motor": ["bearing_wear", "belt_slip", "overload"],
            "pump": ["seal_leak", "pump_wear", "valve_fault"],
            "injection_molding": ["heater_fault", "cooling_insufficient", "hydraulic_leak"],
        }.get(machine_type, [])

    def _maybe_inject_random_anomaly(self, machine):
        """Inject anomalies probabilistically based on the configured daily rate."""
        if not settings.SIMULATOR_ENABLE_ANOMALIES or not machine.is_running or machine.anomaly_active:
            return

        anomaly_types = self._get_supported_anomaly_types(machine)
        if not anomaly_types:
            return

        interval_probability = settings.ANOMALY_PROBABILITY * (
            machine.data_interval_seconds / 86400
        )
        if random.random() >= interval_probability:
            return

        anomaly_type = random.choice(anomaly_types)
        duration_seconds = random.randint(1800, 5400)
        severity = round(random.uniform(1.4, 2.2), 2)

        machine.inject_anomaly(anomaly_type, duration_seconds, severity)
        logger.warning(
            "Auto anomaly injected on %s: %s (duration=%ss, severity=%s)",
            machine.machine_name,
            anomaly_type,
            duration_seconds,
            severity,
        )
    
    async def _connect_database(self):
        """Connect to PostgreSQL database"""
        try:
            self.db_pool = await asyncpg.create_pool(
                host=settings.POSTGRES_HOST,
                port=settings.POSTGRES_PORT,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                database=settings.POSTGRES_DB,
                min_size=2,
                max_size=10
            )
            logger.info("Connected to database")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    async def _load_machines(self):
        """Load machines from database and create simulators"""
        try:
            async with self.db_pool.acquire() as conn:
                machines_data = await conn.fetch("""
                    SELECT 
                        id, name, type, rated_power_kw, 
                        data_interval_seconds, mqtt_topic
                    FROM machines
                    WHERE is_active = TRUE
                    ORDER BY name
                """)
            
            for row in machines_data:
                machine_id = str(row['id'])
                machine_name = row['name']
                machine_type = row['type']
                rated_power_kw = float(row['rated_power_kw'])
                mqtt_topic = row['mqtt_topic']
                
                # Create appropriate simulator based on type
                simulator = self._create_simulator(
                    machine_type,
                    machine_id,
                    machine_name,
                    rated_power_kw,
                    mqtt_topic
                )
                
                if simulator:
                    self.machines[machine_id] = simulator
                    logger.info(f"Loaded machine: {machine_name} ({machine_type})")
            
        except Exception as e:
            logger.error(f"Failed to load machines: {e}")
            raise
    
    def _create_simulator(self, machine_type: str, machine_id: str, machine_name: str, 
                         rated_power_kw: float, mqtt_topic: str):
        """Create simulator instance based on machine type"""
        if machine_type == "compressor":
            return CompressorSimulator(machine_id, machine_name, rated_power_kw, mqtt_topic)
        elif machine_type == "hvac":
            return HVACSimulator(machine_id, machine_name, rated_power_kw, mqtt_topic)
        elif machine_type == "motor":
            return MotorSimulator(machine_id, machine_name, rated_power_kw, mqtt_topic)
        elif machine_type == "pump":
            return HydraulicPumpSimulator(machine_id, machine_name, rated_power_kw, mqtt_topic)
        elif machine_type == "injection_molding":
            return InjectionMoldingSimulator(machine_id, machine_name, rated_power_kw, mqtt_topic)
        elif machine_type == "boiler":
            return BoilerSimulator(machine_id, machine_name, rated_power_kw, mqtt_topic)
        else:
            logger.warning(f"Unknown machine type: {machine_type}")
            return None
    
    async def _start_machine(self, machine_id: str):
        """Start a specific machine simulator"""
        machine = self.machines[machine_id]
        machine.start()
        
        # Create asyncio task for this machine
        task = asyncio.create_task(self._run_machine(machine_id))
        self.tasks[machine_id] = task
        
        logger.info(f"Started machine: {machine.machine_name}")
    
    async def _stop_machine(self, machine_id: str):
        """Stop a specific machine simulator"""
        machine = self.machines[machine_id]
        machine.stop()
        
        # Cancel the task
        if machine_id in self.tasks:
            self.tasks[machine_id].cancel()
            try:
                await self.tasks[machine_id]
            except asyncio.CancelledError:
                pass
            del self.tasks[machine_id]
        
        logger.info(f"Stopped machine: {machine.machine_name}")
    
    async def _run_machine(self, machine_id: str):
        """Run simulation loop for a machine"""
        machine = self.machines[machine_id]
        
        try:
            while machine.is_running:
                timestamp = datetime.utcnow()

                # Periodically inject realistic anomalies so the analytics and
                # notification pipeline has actionable events to detect.
                self._maybe_inject_random_anomaly(machine)
                
                # Generate all data types
                energy_data = machine.generate_energy_reading(timestamp)
                production_data = machine.generate_production_data(timestamp)
                environmental_data = machine.generate_environmental_data(timestamp)
                status_data = machine.generate_machine_status(timestamp)
                
                # Check if machine supports multi-energy (has _generate_sensor_data method)
                if hasattr(machine, '_generate_sensor_data'):
                    # Multi-energy machine (e.g., Boiler)
                    sensor_data = machine._generate_sensor_data(timestamp)
                    sensor_data['timestamp'] = timestamp.isoformat()
                    mqtt_publisher.publish_multi_energy_reading(
                        machine.machine_id,
                        machine.mqtt_topic,
                        sensor_data
                    )
                else:
                    # Legacy single-energy machine
                    mqtt_publisher.publish_energy_reading(
                        machine.machine_id,
                        machine.mqtt_topic,
                        energy_data
                    )
                
                # Always publish production, environmental, and status
                mqtt_publisher.publish_production_data(
                    machine.machine_id,
                    machine.mqtt_topic,
                    production_data
                )
                
                mqtt_publisher.publish_environmental_data(
                    machine.machine_id,
                    machine.mqtt_topic,
                    environmental_data
                )
                
                mqtt_publisher.publish_machine_status(
                    machine.machine_id,
                    machine.mqtt_topic,
                    status_data
                )
                
                # Wait for next interval
                await asyncio.sleep(machine.data_interval_seconds)
                
        except asyncio.CancelledError:
            logger.info(f"Machine {machine.machine_name} task cancelled")
        except Exception as e:
            logger.error(f"Error in machine {machine.machine_name}: {e}")


# Global simulator manager instance
simulator_manager = SimulatorManager()