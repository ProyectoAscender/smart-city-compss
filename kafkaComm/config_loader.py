# config_loader.py
import os

def get_kafka_config_from_env():
    """
    Load Kafka and Schema Registry configuration from environment variables.
    
    This function provides a centralized way to configure Kafka connectivity
    for different deployment environments (development, staging, production).
    
    Environment Variables:
    - KAFKA_BOOTSTRAP_SERVERS: Kafka cluster endpoints
    - KAFKA_TOPIC: Topic name for tracking data
    - KAFKA_USERNAME/PASSWORD: SASL authentication credentials
    - KAFKA_SECURITY_PROTOCOL: Security protocol (PLAINTEXT, SASL_PLAINTEXT, SSL, SASL_SSL)
    - KAFKA_FLUSH_INTERVAL: Number of frames between producer flushes
    - USE_SCHEMA_REGISTRY: Enable Schema Registry integration
    - SCHEMA_REGISTRY_URL: Schema Registry endpoint
    
    Returns:
        dict: Complete Kafka configuration dictionary
    """
    config = {
        # Basic Kafka connection settings
        "use_kafka": os.getenv("USE_KAFKA", "false").lower(),
        "kafka_bootstrap_servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        "kafka_topic": os.getenv("KAFKA_TOPIC", "smartcity-tracking"),

        # Authentication settings (for KafkaUser in Kubernetes)
        "kafka_username": os.getenv("KAFKA_USERNAME"),
        "kafka_password": os.getenv("KAFKA_PASSWORD"),
        "kafka_security_protocol": os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"),
        "kafka_sasl_mechanism": os.getenv("KAFKA_SASL_MECHANISM", "SCRAM-SHA-512"),  # Default to SCRAM

        # SSL/TLS certificate settings
        "kafka_ssl_cafile": os.getenv("KAFKA_SSL_CAFILE"),
        "kafka_ssl_certfile": os.getenv("KAFKA_SSL_CERTFILE"),
        "kafka_ssl_keyfile": os.getenv("KAFKA_SSL_KEYFILE"),

        # Schema Registry configuration
        "schema_registry_url": os.getenv("SCHEMA_REGISTRY_URL"),
        "schema_registry_username": os.getenv("SCHEMA_REGISTRY_USERNAME"),
        "schema_registry_password": os.getenv("SCHEMA_REGISTRY_PASSWORD"),
        "schema_registry_ssl_ca_location": os.getenv("SCHEMA_REGISTRY_SSL_CA_LOCATION"),
        "schema_registry_ssl_cert_location": os.getenv("SCHEMA_REGISTRY_SSL_CERT_LOCATION"),
        "schema_registry_ssl_key_location": os.getenv("SCHEMA_REGISTRY_SSL_KEY_LOCATION"),

        # Avro schema settings
        "avro_schema_subject": os.getenv("AVRO_SCHEMA_SUBJECT", "smartcity-tracking-value"),
        "use_schema_registry": os.getenv("USE_SCHEMA_REGISTRY", "false").lower(),
        
        # Frame-based flush configuration for performance tuning
        "kafka_flush_interval": int(os.getenv("KAFKA_FLUSH_INTERVAL", "100")),  # Default: flush every 100 frames
        "kafka_auto_flush": os.getenv("KAFKA_AUTO_FLUSH", "true").lower(),
    }

    # Auto-detection of security protocols based on credentials
    # If user+pass but still PLAINTEXT, switch to SASL_PLAINTEXT
    if config["kafka_username"] and config["kafka_password"] and config["kafka_security_protocol"] == "PLAINTEXT":
        config["kafka_security_protocol"] = "SASL_PLAINTEXT"
        print("[Kafka] Auto-switched to SASL_PLAINTEXT")

    # If TLS material is present, prefer SSL/SASL_SSL
    if config["kafka_ssl_cafile"]:
        if config["kafka_username"] and config["kafka_password"]:
            config["kafka_security_protocol"] = "SASL_SSL"
            print("[Kafka] Auto-detected SASL_SSL")
        else:
            config["kafka_security_protocol"] = "SSL"
            print("[Kafka] Auto-detected SSL")

    return config

def load_kafka_config(opt):
    """
    Load Kafka/Schema Registry configuration.
    Priority: values from `opt` if present, otherwise from env.
    """
    kafka_env_config = get_kafka_config_from_env()

    keys = [
        "use_kafka",
        "kafka_bootstrap_servers",
        "kafka_topic",
        "kafka_username",
        "kafka_password",
        "kafka_security_protocol",
        "kafka_sasl_mechanism",
        "kafka_ssl_cafile",
        "kafka_ssl_certfile",
        "kafka_ssl_keyfile",
        "schema_registry_url",
        "schema_registry_username",
        "schema_registry_password",
        "schema_registry_ssl_ca_location",
        "schema_registry_ssl_cert_location",
        "schema_registry_ssl_key_location",
        "avro_schema_subject",
        "use_schema_registry",
        "kafka_flush_interval",
        "kafka_auto_flush",
    ]

    config = {}
    for key in keys:
        config[key] = getattr(opt, key, kafka_env_config[key])
    return config
