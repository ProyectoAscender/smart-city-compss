# Kafka Schema Registry Module
# This module provides functions for Avro schema management with Confluent Schema Registry
import json
import io
import avro.schema
import avro.io
import os
import time

# Schema Registry imports for enterprise Avro schema management
try:
    # Confluent Kafka Schema Registry client for centralized schema management
    from confluent_kafka.schema_registry import Schema
    from confluent_kafka.schema_registry import SchemaRegistryClient
    from confluent_kafka.schema_registry.avro import AvroSerializer
    from confluent_kafka.serialization import SerializationContext, MessageField
    SCHEMA_REGISTRY_AVAILABLE = True
except ImportError:
    # Graceful fallback if confluent-kafka is not installed
    SCHEMA_REGISTRY_AVAILABLE = False
    print("[Warning] confluent-kafka not available, using basic avro serialization")

# Avro schema definition for tracking data
# This schema defines the structure for real-time object tracking messages
# Compatible with Confluent Schema Registry and basic Avro serialization
TRACKING_AVRO_SCHEMA = """
{
  "namespace": "alert.avro",
  "type": "record",
  "name": "AlertData",
  "fields": [
    { "name": "cam_id", "type": "string", "doc": "Camera ID (keep as string to preserve leading zeros, e.g., '0003')" },
    { "name": "frame_id", "type": "int" },
    { "name": "ts", "type": { "type": "long", "logicalType": "timestamp-millis" }, "doc": "Producer timestamp" },
    { "name": "track_id", "type": "int" },

    { "name": "coord_box1", "type": "double", "doc": "Bounding box coordinate 1" },
    { "name": "coord_box2", "type": "double", "doc": "Bounding box coordinate 2" },
    { "name": "coord_box3", "type": "double", "doc": "Bounding box coordinate 3" },
    { "name": "coord_box4", "type": "double", "doc": "Bounding box coordinate 4" },

    { "name": "box_score", "type": "float" },
    { "name": "class_box", "type": "int" },

    {
      "name": "utm",
      "type": {
        "type": "record",
        "name": "UtmInfo",
        "fields": [
          { "name": "utm_x_m", "type": "double" },
          { "name": "utm_y_m", "type": "double" },
          { "name": "speed_kmh", "type": "float" },
          { "name": "polygon_type", "type": ["null", "string"], "doc": "Semantic polygon type (road, tramway, bikeLane, etc.)" }
        ]
      },
      "doc": "(UTM_x, UTM_y, velocidad, tipo_poligono)"
    }
  ]
}
"""

# Pre-parsed Avro schema for performance optimization
# Parsing the schema once at module level avoids repeated parsing costs
_PARSED_TRACKING_SCHEMA = None

def get_parsed_schema():
    """Get the parsed Avro schema, parsing it if not already done."""
    global _PARSED_TRACKING_SCHEMA
    if _PARSED_TRACKING_SCHEMA is None:
        _PARSED_TRACKING_SCHEMA = avro.schema.parse(TRACKING_AVRO_SCHEMA)
    return _PARSED_TRACKING_SCHEMA

def create_schema_registry_client(schema_registry_url, username=None, password=None,
                                  ssl_ca_location=None, ssl_cert_location=None, ssl_key_location=None):
    """
    Create a Schema Registry client for centralized Avro schema management.
    
    This enables enterprise-grade schema evolution and compatibility checking.
    Falls back gracefully if Schema Registry is not available.
    
    Args:
        schema_registry_url (str): Schema Registry endpoint URL
        username (str, optional): Basic auth username
        password (str, optional): Basic auth password
        ssl_ca_location (str, optional): Path to CA certificate file
        ssl_cert_location (str, optional): Path to client certificate file
        ssl_key_location (str, optional): Path to client private key file
    
    Returns:
        SchemaRegistryClient or None: Configured client or None if unavailable
    """
    if not SCHEMA_REGISTRY_AVAILABLE or not schema_registry_url:
        print("[Schema Registry] Not available or URL missing; using basic Avro serialization")
        return None

    conf = {"url": schema_registry_url}
    
    # Configure authentication if provided
    if username and password:
        conf["basic.auth.user.info"] = f"{username}:{password}"
        print(f"[Schema Registry] Using basic auth for user: {username}")
    
    # Configure SSL if certificates are provided
    if ssl_ca_location:
        conf["ssl.ca.location"] = ssl_ca_location
    if ssl_cert_location:
        conf["ssl.certificate.location"] = ssl_cert_location
    if ssl_key_location:
        conf["ssl.key.location"] = ssl_key_location

    return SchemaRegistryClient(conf)

def get_or_register_schema(schema_registry_client, subject, schema_str):
    """
    Retrieve existing schema or register a new one in Schema Registry.
    
    This function handles schema versioning and ensures compatibility
    across different application instances.
    
    Args:
        schema_registry_client: Schema Registry client instance
        subject (str): Schema subject name (e.g., 'smartcity-tracking-value')
        schema_str (str): Avro schema definition as JSON string
    
    Returns:
        tuple: (schema_id, schema_str) or (None, None) if client unavailable
    """
    if not schema_registry_client:
        return None, None  # (schema_id, schema_str)

    try:
        # Try to get existing schema version
        v = schema_registry_client.get_latest_version(subject)
        print(f"[Schema Registry] Using existing subject={subject} version={v.version}")
        return v.schema_id, v.schema.schema_str
    except Exception:
        # Schema not found  register new one
        confluent_schema = Schema(schema_str, "AVRO")
        schema_id = schema_registry_client.register_schema(subject, confluent_schema)
        print(f"[Schema Registry] Registered subject={subject} id={schema_id}")
        return schema_id, schema_str

def schema_registry_serializer(data, topic_name, avro_serializer):
    """
    Serialize data using Schema Registry with fallback to basic Avro.
    
    Args:
        data: Data to serialize
        topic_name: Kafka topic name for context
        avro_serializer: AvroSerializer instance
        
    Returns:
        bytes: Serialized data
    """
    ctx = SerializationContext(topic_name, MessageField.VALUE)
    try:
        return avro_serializer(data, ctx)  # returns bytes
    except Exception as e:
        print(f"[Schema Registry] Serialization error: {e}; falling back to basic Avro")
        return avro_serialize(data)

def avro_serialize(data):
    """
    Serialize data using basic Avro format (no Schema Registry).
    
    This function provides fallback serialization when Schema Registry
    is not available or configured. Uses the pre-parsed schema for efficiency.
    
    Args:
        data (dict): Data dictionary matching the Avro schema
    
    Returns:
        bytes or None: Serialized Avro bytes or None on error
    """
    try:
        schema = get_parsed_schema()
        writer = avro.io.DatumWriter(schema)
        bytes_writer = io.BytesIO()
        encoder = avro.io.BinaryEncoder(bytes_writer)
        writer.write(data, encoder)
        return bytes_writer.getvalue()
    except Exception as e:
        print(f"Error serializing Avro data: {e}")
        return None





def create_kafka_producer(topic_name, kafka_bootstrap_servers="localhost:9092", kafka_username=None, kafka_password=None, 
                          kafka_security_protocol="PLAINTEXT", kafka_sasl_mechanism="SCRAM-SHA-512", 
                          kafka_ssl_cafile=None, kafka_ssl_certfile=None, kafka_ssl_keyfile=None,
                          schema_registry_client=None, avro_schema_subject=None):
    """
    Create and configure a Kafka producer with Avro serialization support.
    
    This function creates a high-performance Kafka producer with support for:
    - Schema Registry integration (enterprise)
    - Basic Avro serialization (fallback)
    - Multiple authentication methods (SASL, SSL)
    - Performance optimization settings
    
    Args:
        topic_name (str): Kafka topic name for context (required)
        kafka_bootstrap_servers (str): Comma-separated list of Kafka brokers
        kafka_username (str, optional): SASL username for authentication
        kafka_password (str, optional): SASL password for authentication
        kafka_security_protocol (str): Security protocol (PLAINTEXT, SASL_PLAINTEXT, SSL, SASL_SSL)
        kafka_sasl_mechanism (str): SASL mechanism (SCRAM-SHA-512, PLAIN, etc.)
        kafka_ssl_cafile (str, optional): Path to CA certificate file
        kafka_ssl_certfile (str, optional): Path to client certificate file  
        kafka_ssl_keyfile (str, optional): Path to client private key file
        schema_registry_client: Schema Registry client for enterprise deployments
        avro_schema_subject (str, optional): Schema subject name in Schema Registry
    
    Returns:
        KafkaProducer or None: Configured producer instance or None on failure
    """
    from kafka import KafkaProducer
    
    # Validate required parameters
    if not topic_name:
        raise ValueError("topic_name is required and cannot be None or empty")
    
    use_schema_registry = schema_registry_client is not None

    # Base producer configuration optimized for real-time streaming
    producer_config = {
        "bootstrap_servers": kafka_bootstrap_servers,
        "key_serializer": (lambda x: x.encode("utf-8") if x else None),
        "acks": "all",              # Wait for all replicas to acknowledge
        "retries": 3,               # Retry failed sends
        "batch_size": 16384,        # Batch size for better throughput
        "linger_ms": 10,            # Wait time for batching
        "buffer_memory": 33554432,  # Producer buffer memory
    }

    # Configure serialization strategy (Schema Registry vs Basic Avro)
    if use_schema_registry and SCHEMA_REGISTRY_AVAILABLE:
        # Enterprise mode: Use Schema Registry for centralized schema management
        _, schema_str = get_or_register_schema(schema_registry_client, avro_schema_subject, TRACKING_AVRO_SCHEMA)
        if schema_str:
            avro_serializer = AvroSerializer(schema_registry_client, schema_str)
            producer_config["value_serializer"] = lambda x: schema_registry_serializer(x, topic_name, avro_serializer)
            print("[Kafka] Using Confluent Avro wire format via Schema Registry")
        else:
            # Schema Registry failed, fallback to basic Avro
            producer_config["value_serializer"] = lambda x: avro_serialize(x)
            print("[Kafka] SR lookup failed; using basic Avro")
    else:
        # Basic mode: Use standard Avro serialization
        producer_config["value_serializer"] = lambda x: avro_serialize(x)
        print("[Kafka] Using basic Avro serialization")

    # Configure security settings based on protocol
    if kafka_security_protocol != "PLAINTEXT":
        producer_config["security_protocol"] = kafka_security_protocol
        
        # Configure SASL authentication if credentials provided
        if kafka_username and kafka_password:
            producer_config["sasl_mechanism"] = kafka_sasl_mechanism
            producer_config["sasl_plain_username"] = kafka_username
            producer_config["sasl_plain_password"] = kafka_password
            print(f"[Kafka] Configuring SASL auth for user: {kafka_username}")
        
        # Configure SSL certificates if provided
        if kafka_ssl_cafile:
            producer_config["ssl_cafile"] = kafka_ssl_cafile
        if kafka_ssl_certfile:
            producer_config["ssl_certfile"] = kafka_ssl_certfile
        if kafka_ssl_keyfile:
            producer_config["ssl_keyfile"] = kafka_ssl_keyfile

    try:
        producer = KafkaProducer(**producer_config)
        print(f"[Kafka] Producer created with security protocol: {kafka_security_protocol}")
        return producer
    except Exception as e:
        print(f"Error creating Kafka producer: {e}")
        return None

def send_tracking_data_to_kafka(producer, topic, data, cam_id):
    """
    Send tracking data to Kafka topic with proper partitioning.
    
    Uses camera ID and track ID as message key to ensure related messages
    are sent to the same partition for ordered processing.
    
    Args:
        producer: Kafka producer instance
        topic (str): Kafka topic name
        data (dict): Avro-serialized tracking data
        cam_id (str): Camera identifier for partitioning
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Validate timestamp value
        if 'ts' in data:
            ts_val = data['ts']
            if not isinstance(ts_val, int) or ts_val <= 0:
                print(f"[Kafka] Warning: Invalid timestamp {ts_val}, using current time")
                data['ts'] = int(time.time() * 1000)
        
        # Validate polygon_type in utm field
        if 'utm' in data and 'polygon_type' in data['utm']:
            polygon_val = data['utm']['polygon_type']
            if polygon_val is not None and not isinstance(polygon_val, str):
                print(f"[Kafka] Warning: Invalid polygon_type {polygon_val} (type: {type(polygon_val)}), converting to None")
                data['utm']['polygon_type'] = None
        
        # Use cam_id + track_id as the message key for consistent partitioning
        # This ensures all messages from the same track go to the same partition
        key = f"{cam_id}_{data['track_id']}"
        producer.send(topic, key=key, value=data)
        return True
    except Exception as e:
        print(f"Error sending data to Kafka: {e}")
        return False

