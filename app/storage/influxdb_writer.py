"""InfluxDB writer for storing sensor data for historical analysis."""
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

logger = logging.getLogger(__name__)


class InfluxDBWriter:
    """Writes sensor data to InfluxDB for Grafana visualization."""

    def __init__(
        self,
        url: str = "http://localhost:8086",
        token: Optional[str] = None,
        org: str = "imt",
        bucket: str = "python",
    ):
        """
        Initialize InfluxDB writer.

        Args:
            url: InfluxDB server URL
            token: Authentication token (if None, uses default admin token)
            org: Organization name
            bucket: Bucket name for storing data
        """
        self.url = url
        self.token = token or "admin-token-secret-2024"
        self.org = org
        self.bucket = bucket
        
        try:
            self.client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            logger.info(f"[INFLUXDB] Connected to {self.url}, org={self.org}, bucket={self.bucket}")
        except Exception as e:
            logger.error(f"[INFLUXDB] Failed to connect: {e}")
            raise

    def write_sensor_data(
        self,
        sensor_id: str,
        timestamp: datetime,
        acceleration: Dict[str, float],
        tension: Optional[float] = None,
        frequency: Optional[float] = None,
    ) -> bool:
        """
        Write sensor measurement to InfluxDB.

        Args:
            sensor_id: Sensor identifier
            timestamp: Measurement timestamp
            acceleration: Dict with x, y, z acceleration values (in g).
                         Only configured axes will be written. Non-configured axes
                         can be None or omitted.
            tension: Calculated tension (in N)
            frequency: Fundamental frequency (in Hz)

        Returns:
            True if write was successful
        """
        try:
            # Create point with sensor_id tag
            point = Point("sensor_data").tag("sensor_id", sensor_id)
            
            # Add acceleration fields only for axes that have valid values
            fields_added = 0
            for axis in ['x', 'y', 'z']:
                if axis in acceleration and acceleration[axis] is not None:
                    point = point.field(f"acceleration_{axis}", float(acceleration[axis]))
                    fields_added += 1
            
            # Validate that at least one axis was added
            if fields_added == 0:
                logger.warning(f"[INFLUXDB] No valid acceleration data for {sensor_id}")
                return False
            
            # Add timestamp
            point = point.time(timestamp, WritePrecision.MS)

            # Add optional fields if available
            if tension is not None:
                point = point.field("tension", float(tension))
            
            if frequency is not None:
                point = point.field("frequency", float(frequency))

            # Write to InfluxDB
            self.write_api.write(bucket=self.bucket, org=self.org, record=point)
            return True

        except Exception as e:
            logger.error(f"[INFLUXDB] Error writing data for {sensor_id}: {e}")
            return False

    def write_batch(self, points: list) -> bool:
        """
        Write multiple points in batch.

        Args:
            points: List of Point objects

        Returns:
            True if write was successful
        """
        try:
            self.write_api.write(bucket=self.bucket, org=self.org, record=points)
            return True
        except Exception as e:
            logger.error(f"[INFLUXDB] Error writing batch: {e}")
            return False

    def close(self):
        """Close InfluxDB connection."""
        try:
            self.write_api.close()
            self.client.close()
            logger.info("[INFLUXDB] Connection closed")
        except Exception as e:
            logger.error(f"[INFLUXDB] Error closing connection: {e}")
