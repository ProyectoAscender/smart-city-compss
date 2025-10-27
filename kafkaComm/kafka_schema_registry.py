# Kafka Schema Registry Module (unificado a <topic>-value)

import io
import os
import json
import avro.schema
import avro.io

# Confluent Schema Registry
try:
    from confluent_kafka.schema_registry import Schema, SchemaRegistryClient
    from confluent_kafka.schema_registry.avro import AvroSerializer
    from confluent_kafka.serialization import SerializationContext, MessageField
    _CONFLUENT_KAFKA_INSTALLED = True
except ImportError:
    _CONFLUENT_KAFKA_INSTALLED = False
    print("[Warning] confluent-kafka not available, using basic Avro serialization")


# ---------- Load & cache Avro schema ----------
def load_schema_from_file(filepath="smartcity-tracking.avsc"):
    with open(filepath, "r") as f:
        # Return canonical JSON string (sorted keys helps deterministic compares)
        return json.dumps(json.load(f), sort_keys=True)

filepath = os.path.join(os.path.dirname(__file__), "smartcity-tracking.avsc")
print(f"Schema path: {filepath}")
TRACKING_AVRO_SCHEMA = load_schema_from_file(filepath)

_PARSED_TRACKING_SCHEMA = None
def get_parsed_schema():
    global _PARSED_TRACKING_SCHEMA
    if _PARSED_TRACKING_SCHEMA is None:
        _PARSED_TRACKING_SCHEMA = avro.schema.parse(TRACKING_AVRO_SCHEMA)
    return _PARSED_TRACKING_SCHEMA


# ---------- Schema Registry client ----------
def create_schema_registry_client(schema_registry_url, username=None, password=None,
                                  ssl_ca_location=None, ssl_cert_location=None, ssl_key_location=None):
    """
    Devuelve un SchemaRegistryClient si hay URL; en caso contrario, None.
    No dependemos de variables de entorno: si hay cliente, lo usamos.
    """
    if not _CONFLUENT_KAFKA_INSTALLED or not schema_registry_url:
        print("[Schema Registry] Disabled (missing client or URL). Falling back to basic Avro.")
        return None

    conf = {"url": schema_registry_url}
    if username and password:
        conf["basic.auth.user.info"] = f"{username}:{password}"
    if ssl_ca_location:
        conf["ssl.ca.location"] = ssl_ca_location
    if ssl_cert_location:
        conf["ssl.certificate.location"] = ssl_cert_location
    if ssl_key_location:
        conf["ssl.key.location"] = ssl_key_location

    try:
        return SchemaRegistryClient(conf)
    except Exception as e:
        print(f"[Schema Registry] Client init failed: {e}")
        return None


# ---------- Robust register/get (unifica subject a <topic>-value) ----------
def get_or_register_schema(schema_registry_client, subject, schema_str):
    """
    - Reutiliza versión si el schema es idéntico (lookup).
    - Testea compatibilidad con la última versión antes de registrar.
    - Registra solo si hace falta.
    Devuelve (schema_id, schema_str) o (None, None) si no hay SR.
    """
    if not schema_registry_client:
        return None, None

    new_schema = Schema(schema_str, "AVRO")

    # 1) ¿Ya existe exactamente este schema bajo este subject?
    try:
        looked_up = schema_registry_client.lookup_schema(subject, new_schema)
        if looked_up and looked_up.schema_id is not None:
            return looked_up.schema_id, looked_up.schema.schema_str
    except Exception:
        pass  # subject inexistente o lookup no disponible → seguimos

    # 2) Si hay última versión, probamos compatibilidad BACKWARD
    try:
        latest = schema_registry_client.get_latest_version(subject)
        compatible = schema_registry_client.test_compatibility(subject, latest.version, new_schema)
        if not compatible:
            raise ValueError(
                f"[Schema Registry] Incompatible new schema vs latest v{latest.version} for subject '{subject}'."
            )
    except Exception:
        # subject nuevo o sin versiones → OK registrar
        pass

    # 3) Registrar nueva versión
    schema_id = schema_registry_client.register_schema(subject, new_schema)
    return schema_id, schema_str


# ---------- Serializers ----------
def schema_registry_serializer(data, topic_name, avro_serializer):
    ctx = SerializationContext(topic_name, MessageField.VALUE)
    try:
        return avro_serializer(data, ctx)  # bytes (Confluent wire format)
    except Exception as e:
        print(f"[Schema Registry] Serialization error: {e}; falling back to basic Avro")
        return avro_serialize(data)

def avro_serialize(data):
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


# ---------- Producer factory (unificado a <topic>-value) ----------
def create_kafka_producer(topic_name, kafka_bootstrap_servers="localhost:9092",
                          kafka_username=None, kafka_password=None,
                          kafka_security_protocol="PLAINTEXT", kafka_sasl_mechanism="SCRAM-SHA-512",
                          kafka_ssl_cafile=None, kafka_ssl_certfile=None, kafka_ssl_keyfile=None,
                          schema_registry_client=None, use_schema_registry=False):
    """
    Unifica el subject a '<topic>-value' si se usa Schema Registry.
    """
    from kafka import KafkaProducer
    if not topic_name:
        raise ValueError("topic_name is required")

    subject = f"{topic_name}-value"  # <-- Unificación aquí

    producer_config = {
        "bootstrap_servers": kafka_bootstrap_servers,
        "key_serializer": (lambda x: x.encode("utf-8") if x else None),
        "acks": "all",
        "retries": 3,
        "batch_size": 16384,
        "linger_ms": 10,
        "buffer_memory": 33554432,
    }

    use_sr = bool(schema_registry_client) and bool(use_schema_registry)

    if use_sr:
        # Registrar/obtener el schema bajo <topic>-value
        _, schema_str = get_or_register_schema(schema_registry_client, subject, TRACKING_AVRO_SCHEMA)
        if schema_str:
            avro_serializer = AvroSerializer(
                schema_registry_client,
                schema_str,
                conf={
                    "auto.register.schemas": True,  # o False si quieres exigir existencia previa
                    "normalize.schemas": True
                    # NO pasar subject.name.strategy (por defecto TopicNameStrategy)
                }
            )
            producer_config["value_serializer"] = lambda x: schema_registry_serializer(x, topic_name, avro_serializer)
            print(f"[Kafka] Using Schema Registry with subject: {subject}")
        else:
            print("[Kafka] SR unavailable during setup; using basic Avro")
            producer_config["value_serializer"] = avro_serialize
    else:
        producer_config["value_serializer"] = avro_serialize
        if use_schema_registry and not schema_registry_client:
            print("[Kafka] SR requested but no client provided; using basic Avro")

    # Seguridad
    if kafka_security_protocol != "PLAINTEXT":
        producer_config["security_protocol"] = kafka_security_protocol
        if kafka_username and kafka_password:
            producer_config["sasl_mechanism"] = kafka_sasl_mechanism
            producer_config["sasl_plain_username"] = kafka_username
            producer_config["sasl_plain_password"] = kafka_password
            print(f"[Kafka] Configuring SASL user: {kafka_username}")
        if kafka_ssl_cafile:
            producer_config["ssl_cafile"] = kafka_ssl_cafile
        if kafka_ssl_certfile:
            producer_config["ssl_certfile"] = kafka_ssl_certfile
        if kafka_ssl_keyfile:
            producer_config["ssl_keyfile"] = kafka_ssl_keyfile

    try:
        producer = KafkaProducer(**producer_config)
        print(f"[Kafka] Producer created (protocol: {kafka_security_protocol})")
        return producer
    except Exception as e:
        print(f"Error creating Kafka producer: {e}")
        return None



# ---------- Senders ----------
def send_tracking_data_to_kafka(producer, topic, data, cam_id):
    try:
        key = f"{cam_id}_{data['track_id']}"
        producer.send(topic, key=key, value=data)
        print(f"[Kafka] Sent data to topic '{topic}' with key '{key}' for cam_id '{cam_id}'")
        return True
    except Exception as e:
        print(f"[Kafka] Error sending data to topic '{topic}': {e}")
        return False


def send_target_to_kafka(t, i, CAM_ID, frameId, ts_reception, use_kafka, kafka_producer, 
                         kafka_topic, results):
    print(f"{CAM_ID} - Debug: Processing target {i}: {t}")
    print(f"{CAM_ID} - Debug: t.location: {getattr(t, 'location', 'NO LOCATION ATTR')}")
    print(f"{CAM_ID} - Debug: t.median_speed: {getattr(t, 'median_speed', 'NO SPEED ATTR')}")
    print(f"{CAM_ID} - Debug: t.event: {getattr(t, 'event', 'NO EVENT ATTR')}")

    utm_x_m = float(t.location[0])
    utm_y_m = float(t.location[1])
    speed_kmh = float(getattr(t, "median_speed", 0.0))
    polygon_type = getattr(getattr(t, "event", None), "polyType", None)

    utm_valid = (utm_x_m is not None and utm_y_m is not None and utm_x_m != 0.0 and utm_y_m != 0.0)

    if use_kafka and kafka_producer and utm_valid:
        data = {
            "cam_id": str(CAM_ID),
            "frame_id": int(frameId),
            "ts": int(ts_reception),  # ⚠️ Asegúrate que coincide con tu .avsc (string vs long)
            "track_id": int(t.track_id),
            "coord_box1": float(t.tlwh[0]),
            "coord_box2": float(t.tlwh[1]),
            "coord_box3": float(t.tlwh[2]),
            "coord_box4": float(t.tlwh[3]),
            "box_score": float(t.score),
            "class_box": int(getattr(t, 'cl', 0)),
            "utm": {
                "utm_x_m": utm_x_m,
                "utm_y_m": utm_y_m,
                "speed_kmh": speed_kmh,
                "polygon_type": polygon_type
            }
        }
        return send_tracking_data_to_kafka(kafka_producer, kafka_topic, data, CAM_ID)
    elif use_kafka and kafka_producer and not utm_valid:
        print(f"{CAM_ID} - Skipping Kafka send - invalid UTM values "
              f"(utm_x_m: {utm_x_m}, utm_y_m: {utm_y_m}, track_id: {t.track_id})")
        return False
    return False
