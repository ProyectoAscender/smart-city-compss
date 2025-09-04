import numpy as np
import shutil
import time as tm
import socket
import signal
import sys
import time
import cv2
import os
from os.path import join
from src.timer import Timer
from src.visualize import plot_tracking
from trackers.multi_tracker_zoo import create_tracker
from src.viewTransform import ViewTransformer
from src import utils, event, processing
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import comm_udp as comm_udp

from pycompss.api.api import compss_wait_on

# Kafka and Avro imports for real-time data streaming
from kafka import KafkaProducer
import json
import io
import avro.schema
import avro.io

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

# Hardcoded values
DEFAULT_FPS = 20
VIDEO_OUT_NAME = "video_tracking_output.mp4"
LOG_OUT_NAME = "out.txt"
ALERTS_OUT_NAME = "alarm.txt"
PMAT_DEST_PATH = "./pmat.txt"

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
          { "name": "polygon_type", "type": "int" }
        ]
      },
      "doc": "(UTM_x, UTM_y, velocidad, tipo_poligono)"
    }
  ]
}
"""
#######################################3


# KAFKA_BOOTSTRAP_SERVERS=ascender-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092
# KAFKA_SECURITY_PROTOCOL=SASL_PLAINTEXT
# KAFKA_SASL_MECHANISM=SCRAM-SHA-512
# KAFKA_USERNAME=<your-scram-user>
# KAFKA_PASSWORD=<its-password>

# # Optional SR (HTTP)
# USE_SCHEMA_REGISTRY=true
# SCHEMA_REGISTRY_URL=http://schema-registry.kafka:8081
# AVRO_SCHEMA_SUBJECT=smartcity-tracking-value

###########################################
# KAFKA CONFIGURATION MANAGEMENT
# 
# Environment variable configuration for Kafka and Schema Registry
# Supports both basic Kafka and enterprise Schema Registry deployments
# Compatible with Helm charts and Kubernetes deployments
###########################################

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
    import os
    config = {
        # Basic Kafka connection settings
        'kafka_bootstrap_servers': os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'),
        'kafka_topic': os.getenv('KAFKA_TOPIC', 'smartcity-tracking'),

        # Authentication settings (for KafkaUser in Kubernetes)
        'kafka_username': os.getenv('KAFKA_USERNAME'),
        'kafka_password': os.getenv('KAFKA_PASSWORD'),
        'kafka_security_protocol': os.getenv('KAFKA_SECURITY_PROTOCOL', 'PLAINTEXT'),
        'kafka_sasl_mechanism': os.getenv('KAFKA_SASL_MECHANISM', 'SCRAM-SHA-512'),  # Default to SCRAM

        # SSL/TLS certificate settings
        'kafka_ssl_cafile': os.getenv('KAFKA_SSL_CAFILE'),
        'kafka_ssl_certfile': os.getenv('KAFKA_SSL_CERTFILE'),
        'kafka_ssl_keyfile': os.getenv('KAFKA_SSL_KEYFILE'),

        # Schema Registry configuration
        'schema_registry_url': os.getenv('SCHEMA_REGISTRY_URL'),
        'schema_registry_username': os.getenv('SCHEMA_REGISTRY_USERNAME'),
        'schema_registry_password': os.getenv('SCHEMA_REGISTRY_PASSWORD'),
        'schema_registry_ssl_ca_location': os.getenv('SCHEMA_REGISTRY_SSL_CA_LOCATION'),
        'schema_registry_ssl_cert_location': os.getenv('SCHEMA_REGISTRY_SSL_CERT_LOCATION'),
        'schema_registry_ssl_key_location': os.getenv('SCHEMA_REGISTRY_SSL_KEY_LOCATION'),

        # Avro schema settings
        'avro_schema_subject': os.getenv('AVRO_SCHEMA_SUBJECT', 'smartcity-tracking-value'),
        'use_schema_registry': os.getenv('USE_SCHEMA_REGISTRY', 'false').lower() == 'true',
        
        # Frame-based flush configuration for performance tuning
        'kafka_flush_interval': int(os.getenv('KAFKA_FLUSH_INTERVAL', '100')),  # Default: flush every 100 frames
        'kafka_auto_flush': os.getenv('KAFKA_AUTO_FLUSH', 'true').lower() == 'true',
    }

    # Auto-detection of security protocols based on credentials
    # If user+pass but still PLAINTEXT, switch to SASL_PLAINTEXT
    if config['kafka_username'] and config['kafka_password'] and config['kafka_security_protocol'] == 'PLAINTEXT':
        config['kafka_security_protocol'] = 'SASL_PLAINTEXT'
        print("[Kafka] Auto-switched to SASL_PLAINTEXT")

    # If TLS material is present, prefer SSL/SASL_SSL
    if config['kafka_ssl_cafile']:
        if config['kafka_username'] and config['kafka_password']:
            config['kafka_security_protocol'] = 'SASL_SSL'
            print("[Kafka] Auto-detected SASL_SSL")
        else:
            config['kafka_security_protocol'] = 'SSL'
            print("[Kafka] Auto-detected SSL")

    return config


# Schema Registry client management functions
# These functions handle Schema Registry connectivity and schema registration

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

    conf = {'url': schema_registry_url}
    
    # Configure authentication if provided
    if username and password:
        conf['basic.auth.user.info'] = f"{username}:{password}"
        print(f"[Schema Registry] Using basic auth for user: {username}")
    
    # Configure SSL if certificates are provided
    if ssl_ca_location:
        conf['ssl.ca.location'] = ssl_ca_location
    if ssl_cert_location:
        conf['ssl.certificate.location'] = ssl_cert_location
    if ssl_key_location:
        conf['ssl.key.location'] = ssl_key_location

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
        # Schema not found → register new one
        confluent_schema = Schema(schema_str, 'AVRO')
        schema_id = schema_registry_client.register_schema(subject, confluent_schema)
        print(f"[Schema Registry] Registered subject={subject} id={schema_id}")
        return schema_id, schema_str



def create_kafka_producer(kafka_bootstrap_servers="localhost:9092", kafka_username=None, kafka_password=None, 
                          kafka_security_protocol="PLAINTEXT", kafka_sasl_mechanism="SCRAM-SHA-512", 
                          kafka_ssl_cafile=None, kafka_ssl_certfile=None, kafka_ssl_keyfile=None,
                          schema_registry_client=None, avro_schema_subject=None, topic_name=None):
    """
    Create and configure a Kafka producer with Avro serialization support.
    
    This function creates a high-performance Kafka producer with support for:
    - Schema Registry integration (enterprise)
    - Basic Avro serialization (fallback)
    - Multiple authentication methods (SASL, SSL)
    - Performance optimization settings
    
    Args:
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
        topic_name (str, optional): Kafka topic name for context
    
    Returns:
        KafkaProducer or None: Configured producer instance or None on failure
    """
    use_schema_registry = schema_registry_client is not None

    # Base producer configuration optimized for real-time streaming
    producer_config = {
        'bootstrap_servers': kafka_bootstrap_servers,
        'key_serializer': (lambda x: x.encode('utf-8') if x else None),
        'acks': 'all',              # Wait for all replicas to acknowledge
        'retries': 3,               # Retry failed sends
        'batch_size': 16384,        # Batch size for better throughput
        'linger_ms': 10,            # Wait time for batching
        'buffer_memory': 33554432,  # Producer buffer memory
    }

    # Configure serialization strategy (Schema Registry vs Basic Avro)
    if use_schema_registry and SCHEMA_REGISTRY_AVAILABLE:
        # Enterprise mode: Use Schema Registry for centralized schema management
        _, schema_str = get_or_register_schema(schema_registry_client, avro_schema_subject, TRACKING_AVRO_SCHEMA)
        if schema_str:
            avro_serializer = AvroSerializer(schema_registry_client, schema_str)

            def schema_registry_serializer(data):
                """Serialize data using Schema Registry with fallback to basic Avro."""
                ctx = SerializationContext(topic_name, MessageField.VALUE)
                try:
                    return avro_serializer(data, ctx)  # returns bytes
                except Exception as e:
                    print(f"[Schema Registry] Serialization error: {e}; falling back to basic Avro")
                    return avro_serialize(data)

            producer_config['value_serializer'] = schema_registry_serializer
            print("[Kafka] Using Confluent Avro wire format via Schema Registry")
        else:
            # Schema Registry failed, fallback to basic Avro
            producer_config['value_serializer'] = lambda x: avro_serialize(x)
            print("[Kafka] SR lookup failed; using basic Avro")
    else:
        # Basic mode: Use standard Avro serialization
        producer_config['value_serializer'] = lambda x: avro_serialize(x)
        print("[Kafka] Using basic Avro serialization")

    # Configure security settings based on protocol
    if kafka_security_protocol != "PLAINTEXT":
        producer_config['security_protocol'] = kafka_security_protocol
        
        # Configure SASL authentication if credentials provided
        if kafka_username and kafka_password:
            producer_config['sasl_mechanism'] = kafka_sasl_mechanism
            producer_config['sasl_plain_username'] = kafka_username
            producer_config['sasl_plain_password'] = kafka_password
            print(f"[Kafka] Configuring SASL auth for user: {kafka_username}")
        
        # Configure SSL certificates if provided
        if kafka_ssl_cafile:
            producer_config['ssl_cafile'] = kafka_ssl_cafile
        if kafka_ssl_certfile:
            producer_config['ssl_certfile'] = kafka_ssl_certfile
        if kafka_ssl_keyfile:
            producer_config['ssl_keyfile'] = kafka_ssl_keyfile

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
        # Use cam_id + track_id as the message key for consistent partitioning
        # This ensures all messages from the same track go to the same partition
        key = f"{cam_id}_{data['track_id']}"
        producer.send(topic, key=key, value=data)
        return True
    except Exception as e:
        print(f"Error sending data to Kafka: {e}")
        return False




# Pre-parsed Avro schema for performance optimization
# Parsing the schema once at module level avoids repeated parsing costs
_PARSED_TRACKING_SCHEMA = avro.schema.parse(TRACKING_AVRO_SCHEMA)

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
        writer = avro.io.DatumWriter(_PARSED_TRACKING_SCHEMA)
        bytes_writer = io.BytesIO()
        encoder = avro.io.BinaryEncoder(bytes_writer)
        writer.write(data, encoder)
        return bytes_writer.getvalue()
    except Exception as e:
        print(f"Error serializing Avro data: {e}")
        return None



# Get host IP
HOST_IP = utils.get_local_ip()

# Global flag for exiting the program gracefully
FINISH_PROGRAM = False

def signal_handler(sig, frame):
    global FINISH_PROGRAM
    print("\n[Signal Handler] Ctrl+C clicked! Closing execution...")
    FINISH_PROGRAM = True

signal.signal(signal.SIGINT, signal_handler)

def run_udp(
        edge_ip=None,
        track_thresh = None,
        track_buffer = None,
        match_thresh = None,
        min_box_area = None,
        #yolo_weights=WEIGHTS / 'yolov5m.pt',  # model.pt path(s),
        reid_weights= None,  # model.pt path,
        tracking_method='bytetrack',
        tracking_config=None,
        exp_dir = None,
        expn = None,
        only_results = False, 
        save_results = True,
        save_plot = False,
        view_plot = False,
        get_semantic = True, 
        get_speed = True,
        alerts = False,
        print_time = True,
        # Kafka parameters
        use_kafka = True,
        kafka_bootstrap_servers = "localhost:9092",
        kafka_topic = "smartcity-tracking",
        # Kafka authentication parameters (typically from Helm chart)
        kafka_username = None,
        kafka_password = None,
        kafka_security_protocol = "PLAINTEXT",
        kafka_sasl_mechanism="SCRAM-SHA-512",
        kafka_ssl_cafile = None,
        kafka_ssl_certfile = None,
        kafka_ssl_keyfile = None,
        # Schema Registry parameters
        schema_registry_url = None,
        schema_registry_username = None,
        schema_registry_password = None,
        schema_registry_ssl_ca_location = None,
        schema_registry_ssl_cert_location = None,
        schema_registry_ssl_key_location = None,
        avro_schema_subject = "smartcity-tracking-value",
        use_schema_registry = False,
        # Frame-based flush parameters
        kafka_flush_interval = 100,  # Flush every N frames (0 = disable frame-based flush)
        kafka_auto_flush = True      # Enable automatic periodic flushing
        ):

    global FINISH_PROGRAM
    
    print("\n\n\n[udp_handler] Starting UDP-based tracking...")

    # Maybe this should be inside the for loop? one tracker per edge device????
    # Create as many track instances as there are video sources
    # TO - DO : si cada run se paraleliza para cada vídeo, aqui no paralelizamos nada, pero podriamos tener mas de un tracker para solo una camara -> approach paddle padlle
    tracker_list = []
    # print(f'- Creating tracker for {opt.source} - ')
    tracker = create_tracker(tracking_method, tracking_config, reid_weights)
    tracker_list.append(tracker, )
    
    # Initialize Schema Registry client if enabled
    schema_registry_client = None
    if use_kafka and use_schema_registry:
        schema_registry_client = create_schema_registry_client(
            schema_registry_url=schema_registry_url,
            username=schema_registry_username,
            password=schema_registry_password,
            ssl_ca_location=schema_registry_ssl_ca_location,
            ssl_cert_location=schema_registry_ssl_cert_location,
            ssl_key_location=schema_registry_ssl_key_location
        )
    
    # Initialize Kafka producer if enabled
    kafka_producer = None
    if use_kafka:
        kafka_producer = create_kafka_producer(
            kafka_bootstrap_servers=kafka_bootstrap_servers,
            kafka_username=kafka_username,
            kafka_password=kafka_password,
            kafka_security_protocol=kafka_security_protocol,
            kafka_sasl_mechanism=kafka_sasl_mechanism,
            kafka_ssl_cafile=kafka_ssl_cafile,
            kafka_ssl_certfile=kafka_ssl_certfile,
            kafka_ssl_keyfile=kafka_ssl_keyfile,
            schema_registry_client=schema_registry_client,
            avro_schema_subject=avro_schema_subject,
            topic_name=kafka_topic,   # ← pass the real topic here
        )

        if kafka_producer:
            print(f"[udp_handler] Kafka producer initialized for topic: {kafka_topic}")
        else:
            print(f"[udp_handler] Failed to initialize Kafka producer, falling back to CSV")
            use_kafka = False
    
    # Check MQTT if alerts are activated
    # if (alerts):
    #     # MQTT broker connection
    #     mqtt_client = mqtt.Client()
    #     try:
    #         mqtt_client.connect(MQTT_BROKER_IP, MQTT_BROKER_PORT)
    #         print(f"[main.py] Successfully connected to MQTT broker at {MQTT_BROKER_IP}:{MQTT_BROKER_PORT}")

    #     except Exception as e:
    #         print(f"[main.py] ERROR connecting to MQTT broker at {MQTT_BROKER_IP}:{MQTT_BROKER_PORT}: {e}")

    # if FINISH_PROGRAM:
    #     break
    # after kafka_producer is created
    last_flush_time = time.time() if (use_kafka and kafka_producer) else 0.0
    FLUSH_EVERY_SECS = 5.0  # tune as needed

    print(f"Handling edge_ip: {edge_ip}")
    
    # parse "host:port"
    host, port_str = edge_ip.split(":")
    port = int(port_str)
    
    # Create a UDP socket with configuration params
    udpSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # udpSock.bind(('', port))
    udpSock.settimeout(5.0)  # timeout for individual attempts
    max_retries=150
    retry_delay=1
    

    # handshake to get camera info
    try:
        info = comm_udp.handshake_and_get_info(udpSock, host, port, max_retries, retry_delay)
        print(f"[ {edge_ip}] Camera info: {info}")
    except socket.timeout:
        print(f"[ {edge_ip}] Handshake timeout!")
        return

    # GET EDGE INFO:
    CAM_ID = info["cam_id"]
    MULTICAST = int(info["multicast"])
    NEVEREND = int(info['neverend'])
    NUM_ITERS = int(info["frames_to_process"])
    CAM_HEIGHT = int(info["cam_height"])
    CAM_WIDTH  = int(info["cam_width"])
    DATA_PATH = info["data_path"].replace("'", "")
    DATA_PATH = os.path.join(*(DATA_PATH.split(os.path.sep)[3:-1]))
    # videoPath = os.path.join( 'data', DATA_PATH, "videos/20230721_092248_cam01h264.mp4")
    CITY = DATA_PATH.split(os.path.sep)[0]
    AREA = DATA_PATH.split(os.path.sep)[1]
    DATA_PATH = os.path.join( 'data', DATA_PATH)
    ROI_PATH = DATA_PATH + '/roi/' + AREA.lower() + '_' + CAM_ID + '.json'
    PMAT_PATH = utils.find_files_by_strings(os.path.join(DATA_PATH, 'pmat'), CAM_ID, "ACTIVE")[0]
    if (not os.path.exists(PMAT_DEST_PATH)) or (os.stat(PMAT_PATH).st_mtime - os.stat(PMAT_DEST_PATH).st_mtime > 1) :
        # Load pmat. First we add a local copy to avoid b2drop delay
        # Load Pmat (this works assuming 1 edge camera)
        shutil.copy2 (PMAT_PATH, PMAT_DEST_PATH)
        # view_transformer = ViewTransformer(pmatPath = PMAT_PATH)
        # os.system('cp -u' + PMAT_PATH + ' ./pmat.txt')
    view_transformer = ViewTransformer(pmatPath = "./pmat.txt")
    img_info = [CAM_HEIGHT, CAM_WIDTH]
    test_size = (img_info[0], img_info[1]) # We don't want to re-scale yet

    # Optinal saving or visualizing video. Both ways requires get processed frames from camera-edge.
    if view_plot or save_plot:
        
        # Gstreamer input from camera edge. ONLY processed frames are sent and received trough here.
        gst_str = (
            "udpsrc port=5001 multicast-group=239.255.12.41 auto-multicast=true ! "
            "application/x-rtp,media=video,clock-rate=90000,encoding-name=H264 ! "
            "rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! "
            "queue max-size-buffers=1 leaky=downstream ! "
            "appsink sync=false drop=true max-size-buffers=1 leaky=downstream sync=false"
        )
        
        cap = cv2.VideoCapture(gst_str, cv2.CAP_GSTREAMER)
        
        if not cap.isOpened():
            print(f'{CAM_ID} - Failed to open GStreamer pipeline for receiving processed frames')
            exit(1)
        print(f'{CAM_ID} - Video receiving from camera-edge prepared')
        vid_fps = cap.get(cv2.CAP_PROP_FPS)
        FPS = vid_fps if int(vid_fps) > 0 else DEFAULT_FPS
    current_hour = int(datetime.now().strftime("%M"))
    # Prepare video save output
    if save_plot:

        folder_path = os.path.join(

            exp_dir,

            datetime.now().strftime("%Y%m%d"),

            CAM_ID,

            str(current_hour)

        )

        # Create the folder if it doesn't exist
        os.makedirs(folder_path, exist_ok=True)

        video_path = os.path.join(folder_path, VIDEO_OUT_NAME)

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")

        

        if current_hour % 2 == 0:

            vid_writer = cv2.VideoWriter(video_path, fourcc, FPS, (CAM_WIDTH, CAM_HEIGHT))

        else:

            vid_writer2 = cv2.VideoWriter(video_path, fourcc, FPS, (CAM_WIDTH, CAM_HEIGHT))

        print(f'{CAM_ID} - Prepared saving video. Path: {video_path} | fps: {FPS} | resolution: {CAM_WIDTH}x{CAM_HEIGHT}')
    # View_plot if has display and x11 will be show. But if no display will be re-sent.
    # Re-send inicialization:
    if view_plot and os.environ.get("DISPLAY") is None:

        gst_out_str = (
                        "appsrc ! videoconvert ! video/x-raw,format=NV12 ! nvvidconv ! video/x-raw(memory:NVMM),format=NV12 !" 
                        "nvv4l2h264enc insert-sps-pps=true iframeinterval=5 idrinterval=5 control-rate=1 bitrate=1000000 !" 
                        "h264parse ! rtph264pay config-interval=1 pt=96 ! "
                        "udpsink host=239.255.12.42 port=5002 auto-multicast=true sync=0"  # Cambia IP/puerto según necesidad
                        )
        
        vid_sender = cv2.VideoWriter(gst_out_str, cv2.CAP_GSTREAMER, 0, FPS, (CAM_WIDTH, CAM_HEIGHT), True)
        
        if not vid_sender.isOpened():
            print(f'{CAM_ID} - Failed to open output GStreamer pipeline')
            exit(1)
        print(f'{CAM_ID} Video saving prepared to {HOST_IP} ')
            
    # If semantics enabled, load polygons:
    if(get_semantic):
        print(f'{CAM_ID} - Loading Polygons')
        polys = utils.getPolysRoi(ROI_PATH)
    else:
        polys = []

    frame_idx = 0
    frameId = 0
    ts = 0
    # Time inicialization
    timers = {name: Timer() for name in ['track', 'reception', 'wait_recv', 'processing', 'speed', 'video', 'semantics', 'total']}
            
    # Variable inicialization:
    skiped_frames = 0
    
    
    # Prepare storage for bounding-box results
    results = []
    all_results = []
    if (alerts): alertInfo = []
    current_hour = datetime.now().strftime("%H")
    
    print('Iterating frames')
    ######################### LOOP ITERATING FRAMES ########################
    # We loop indefinitely or until some condition
    # while frame_idx < NUM_ITERS:
    # Loop changed because Smart City can be faster than camera-edge
    while frameId <= NUM_ITERS or NEVEREND == True:
        hex_data = ""
        timers['total'].tic()                 
        new_hour = int(datetime.now().strftime("%M"))  
        frame_idx += 1

        # Loop to get the last message
        udpSock.setblocking(False)
        timers['wait_recv'].tic()
        while True:
            if FINISH_PROGRAM:
                break   
            try: 
                # Receiving boxes
                hex_data, _ = udpSock.recvfrom(16000)  # bigger buffer if needed
            except BlockingIOError:
                if(hex_data==""):   # hex_data is set to "" at the end of the processing loop
                    # print(f"[main.py - {CAM_ID}] No bounding box data, continuing...")
                    continue
                timers['wait_recv'].toc()
                break

        udpSock.setblocking(True)
        if FINISH_PROGRAM:
            break
        
        timers['reception'].tic()
    
        # Receiving frame if needed
        if save_plot or view_plot:
            ret, frame = cap.read()
            if not ret:
                print(f"{CAM_ID} - No hay captura. Salto siguiente iter.")
                break
            else:
                print('--- > frame received')
            # cv2.imwrite(f"./{frame_idx}_received.jpg", frame)
            
        
        # Decode the message as per our template            
        frameData = list(comm_udp.decode_hex_bboxes(hex_data))
        
        try:
            frameId = frameData[0][2]
            ts = frameData[0][3]
        except IndexError:
            print(f"{CAM_ID} - Udp hex data couldn't be decoded, so it has zero information")
            # We simulate iteration info with no aprox. expected info
            frameId = frameId + 1
            ts = ts + (1/(FPS if "FPS" in vars() else DEFAULT_FPS))

        # ... after setting frameId and ts ...
        ###########################################################
        def to_epoch_millis(ts_val):
            """
            Convert a timestamp to epoch milliseconds.
            - If already in ms (>= 1e12), return as int.
            - If in seconds since epoch (>= 1e9), convert to ms.
            - Otherwise assume relative seconds and anchor to 'now'.
            """
            try:
                if ts_val >= 1_000_000_000_000:    # already ms
                    return int(ts_val)
                if ts_val >= 1_000_000_000:        # seconds since epoch
                    return int(round(ts_val * 1000))
                # relative seconds -> anchor to current time
                return int(time.time() * 1000) + int(round(ts_val * 1000))
            except Exception:
                return int(time.time() * 1000)
        # Convert ts to epoch milliseconds
        ts_ms = to_epoch_millis(ts)
        #############################################################################

        det = []
        # Checking case zero info in frameData
        if not frameData:
            print(f'{CAM_ID} - No frameData: UDP hexadecimal decode failed')
        elif len(frameData[0]) <= 4:  #  can have 0 detections, only one row with frame info data
            print(f'{CAM_ID} - 0 detections received')
        else:
            # Last 6 elements from frame data are the detections: [x,y,w,h,score,classId]
            det = np.asarray([box[-6:] for box in frameData])
            
        timers['reception'].toc()

        timers['track'].tic()
        ## TRACKING
        # Frames con detecciones
        if isinstance(det, np.ndarray) and det.size > 0:
            # Update tracker
            online_targets = tracker_list[0].update(det, img_info, test_size)

        # Frames sin detecciones. Actualizamos el tracker
        else:
            tracker_list[0].frame_id += 1  # Avanzamos el frame_id manualmente
            for track in tracker_list[0].tracked_stracks:
                track.frames_since_update += 1  # Incrementamos contador de no actualización
            online_targets = []            
            #print('Actualizando tracker sin nuevas detecciones ')
        
        # Collect and write results if online targets is not empty
        if (get_speed): online_speeds = []
        # Discard non-consolidated data

        
        timers['track'].toc()
        

        
        
        
        # After data processing, if "only_results" we dont need to process anything else of this frame
        if (only_results): 
            # FRAME-BASED FLUSH MANAGEMENT
            # Implement intelligent flushing strategy for optimal performance vs latency
            if use_kafka and kafka_producer:
                # Primary flush strategy: Frame-based intervals for predictable latency
                if kafka_flush_interval > 0 and frame_idx % kafka_flush_interval == 0:
                    kafka_producer.flush()
                    print(f"{CAM_ID} - Kafka producer flushed at frame {frame_idx} (every {kafka_flush_interval} frames)")
                
                # Secondary flush strategy: Hourly backup flush (every 300 frames)
                elif frame_idx % 300 == 0:
                    if new_hour != current_hour:
                        kafka_producer.flush()
                        print(f"{CAM_ID} - Kafka producer flushed due to hour change at frame {frame_idx}")
                        current_hour = new_hour
            else:
                # CSV fallback: save every 300 frames or hour change
                if frame_idx % 300 == 0 and new_hour != current_hour:
                    utils.save_results(results, exp_dir, CAM_ID)
                    results = []
                    print(f"{CAM_ID} - Saving CSV results every 300 frames")
                    current_hour = new_hour
            
            print(f"{CAM_ID} - Acabando {frame_idx} - {frameId}")
            continue
        
        timers['processing'].tic()
        futures = []
        for t in online_targets:
            tModified , alertInfo_thread, online_speeds_thread,  t_speed_thread, t_semantics_thread = processing.process_tracklets(
                t, view_transformer, timers, get_semantic, get_speed, alerts,
                (FPS if "FPS" in vars() else DEFAULT_FPS), polys, ts, frameId
            )
            futures.append((tModified , alertInfo_thread, online_speeds_thread,  t_speed_thread, t_semantics_thread))

        online_speeds = [] if get_speed else None
        frame_results = []  # Initialize frame_results before use
        # Discard non-consolidated data

        
        for i, future in enumerate(futures):
            try:
                online_targets[i] = compss_wait_on(future[0])
                alertInfo_task = compss_wait_on(future[1])
                online_speeds_task = compss_wait_on(future[2])
                t_speed_task = compss_wait_on(future[3])
                t_semantics_task = compss_wait_on(future[4])

                if alerts:
                    alertInfo.append(alertInfo_task)
                if get_speed:
                    online_speeds.append(online_speeds_task)

                # Create frame result string for this target
                frame_result = f"{CAM_ID},{frameId},{ts_ms},{online_targets[i].track_id},{online_targets[i].tlwh[0]:.2f},{online_targets[i].tlwh[1]:.2f},{online_targets[i].tlwh[2]:.2f},{online_targets[i].tlwh[3]:.2f},{online_targets[i].score:.2f},{getattr(online_targets[i], 'cl', 0)}"
                frame_results.append(frame_result)

                all_results.append(

                        f"{frame_results[i]},{online_targets[i].location[0]},{online_targets[i].location[1]},"

                        f"{online_targets[i].median_speed:.2f},{online_targets[i].event.polyType}"

                    )
                timers['speed'].toc(value=t_speed_task)
                timers['semantics'].toc(value=t_semantics_task)
            except Exception as e:
                print(f"{CAM_ID} - Error receiving compss data: {e}")
                sys.exit(1)
        timers['processing'].toc()
        # BUILD AND SEND TRACKING DATA TO KAFKA
        # Process each detected object and send to Kafka or store for CSV
        for i, t in enumerate(online_targets):
            # Skip small objects if minimum area threshold is set
            if min_box_area is not None and (t.tlwh[2] * t.tlwh[3] <= min_box_area):
                continue

            # Extract tracking attributes with safe fallbacks
            utm_x = getattr(t, "utm_x", None)
            utm_y = getattr(t, "utm_y", None)
            polygon_type = getattr(t, "polygon_type", None)
            polygon_geometry_obj = getattr(t, "polygon_geometry", None)
            speed_kmh = getattr(t, "speed_kmh", None)
            
            # Convert Shapely geometry to WKT format
            polygon_geometry_wkt = None
            if polygon_geometry_obj is not None:
                try:
                    polygon_geometry_wkt = polygon_geometry_obj.wkt
                except Exception as e:
                    print(f"{CAM_ID} - Error converting polygon to WKT: {e}")
                    polygon_geometry_wkt = None
            
            # Use computed speed if not available on track object
            if speed_kmh is None and (get_speed and i < len(online_speeds)):
                speed_kmh = online_speeds[i]

            if use_kafka and kafka_producer:
                # KAFKA MODE: Send real-time Avro messages
                # Build Avro record matching the schema structure
                avro_record = {
                    "cam_id": CAM_ID,
                    "frame_id": frameId,
                    "ts": ts_ms,  # Timestamp in epoch milliseconds
                    "track_id": t.track_id,
                    
                    # Bounding box coordinates (top-left width-height format)
                    "coord_box1": float(t.tlwh[0]),
                    "coord_box2": float(t.tlwh[1]),
                    "coord_box3": float(t.tlwh[2]),
                    "coord_box4": float(t.tlwh[3]),
                    
                    "box_score": float(getattr(t, "score", 0.0)),
                    "class_box": int(getattr(t, "cl", 0)),
                    
                    # Nested UTM information structure
                    "utm": {
                        "utm_x_m": float(utm_x) if utm_x is not None else 0.0,
                        "utm_y_m": float(utm_y) if utm_y is not None else 0.0,
                        "speed_kmh": float(speed_kmh) if speed_kmh is not None else 0.0,
                        "polygon_type": polygon_type if polygon_type is not None else None,
                        "polygon_geometry": polygon_geometry_wkt if polygon_geometry_wkt is not None else None,
                    },
                }
                
                # Send to Kafka with error handling
                success = send_tracking_data_to_kafka(kafka_producer, kafka_topic, avro_record, CAM_ID)
                if not success:
                    print(f"{CAM_ID} - Failed to send data to Kafka for track_id: {t.track_id}")
            else:
                # CSV FALLBACK MODE: Store data for batch file writing
                # Format data as CSV string for later batch writing
                results.append(
                    f"{CAM_ID},{frameId},{ts_ms},{t.track_id},"
                    f"{t.tlwh[0]:.2f},{t.tlwh[1]:.2f},{t.tlwh[2]:.2f},{t.tlwh[3]:.2f},"
                    f"{t.score:.2f},{t.cl},"
                    f"{'' if utm_x is None else f'{utm_x:.2f}'},"
                    f"{'' if utm_y is None else f'{utm_y:.2f}'},"
                    f"{'' if speed_kmh is None else f'{float(speed_kmh):.2f}'},"
                    f"{'' if polygon_type is None else polygon_type}\n"
                )

        # AUTOMATIC FLUSH FOR LOW-LATENCY DELIVERY
        # Optional immediate flush after sending data for ultra-low latency scenarios
        # Periodic flush (frame- or time-based, or hour change)
        if use_kafka and kafka_producer:
            do_flush = False
            if kafka_auto_flush and kafka_flush_interval > 0 and (frame_idx % kafka_flush_interval == 0):
                do_flush = True
            if (time.time() - last_flush_time) > FLUSH_EVERY_SECS:
                do_flush = True
            if new_hour != current_hour:  # hour rolled over
                do_flush = True
                current_hour = new_hour

            if do_flush:
                try:
                    kafka_producer.flush(timeout=5.0)
                    last_flush_time = time.time()
                    
                    # print(f"{CAM_ID} - Kafka producer flushed at frame {frame_idx}")
                except Exception as e:
                    print(f"{CAM_ID} - Kafka flush error: {e}")
        # Discard non-consolidated data

        online_targets = [t for t in online_targets if t.tlwh[2] * t.tlwh[3] > min_box_area]
        # # Add track info to results 
        # for i, t in enumerate(online_targets):
        #     # tlwh = t.tlwh
        #     # tid = t.track_id 
        #         online_tlwhs.append(t.tlwh)
        #         online_ids.append(t.track_id)
        #         online_scores.append(t.score)
        #         # online_flags(t.event.alertFlag)
        #         # results.append(
        #         #     f"{CAM_ID},{frameId},{ts},{t.track_id},{t.tlwh[0]:.2f},{t.tlwh[1]:.2f},{t.tlwh[2]:.2f},{t.tlwh[3]:.2f},{t.score:.2f},{t.cl}\n"
        #         # )
        #     else:
        #         print("Tracklet discarded because box size")

        timers['video'].tic()

        # Plotting video
        if save_plot or view_plot:
            online_im = plot_tracking(frame, online_targets, frame_id = frameId, fps = FPS, get_semantic = get_semantic)
            # online_im = plot_tracking(
            #     frame, online_tlwhs, online_ids, online_flags,frame_id=frameId, fps= FPS,
            # )
        # Save video
        if save_plot: 
            if current_hour % 2 == 0:

                vid_writer.write(online_im)

            else:

                vid_writer2.write(online_im)


        
        # View frame with plot
        if view_plot and os.environ.get("DISPLAY") is not None:
            # Show video
            cv2.imshow("Tracking", online_im)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        elif view_plot and os.environ.get("DISPLAY") is None:
            # Send video (rtp)
            assert online_im.dtype == np.uint8 and online_im.shape[2] == 3
            print(f'{CAM_ID} - Sending trough rtp {HOST_IP} port 6000 with resolution {online_im.shape[:2]}')
            vid_sender.write(online_im)
            # print(f"WW2 {frameId}")
            # cv2.imwrite(f"./{frameId}.jpg", frame)

        timers['video'].toc()

        if frameId != frame_idx and frameId - frame_idx != skiped_frames:
            skiped_frames = frameId - frame_idx
            print(f"{CAM_ID} - \tSmartCity skipped one frame!! Total skipped frames: {frameId - frame_idx}")
            # break

        timers['total'].toc() 
        
        
        if (print_time and frame_idx % 30 == 0):
            print(f'{CAM_ID} - Info every 10 frames - frameidx: {frame_idx}')
            for name, timer in timers.items():
                print(f'{CAM_ID} - Avg. {name.capitalize()} Time: {timer.average_time}')
                timer.clear()
        # We check again and save results with speed

        if (frame_idx % 300 == 0 and new_hour != current_hour):

            folder_path = utils.save_results(all_results, exp_dir, CAM_ID)

            all_results , results = [] , []

            print(f"{CAM_ID} - Saving every 300 frames")

            

            video_path = os.path.join(folder_path, VIDEO_OUT_NAME)

            if save_plot:

                if current_hour % 2 == 0:

                    vid_writer.release()

                    vid_writer2 = cv2.VideoWriter(video_path, fourcc, FPS, (CAM_WIDTH, CAM_HEIGHT))

                    print(f"{CAM_ID} - New video file started: {video_path}, vid_writer2")

                else:

                    vid_writer2.release()

                    vid_writer = cv2.VideoWriter(video_path, fourcc, FPS, (CAM_WIDTH, CAM_HEIGHT))

                    print(f"{CAM_ID} - New video file started: {video_path}, vid_writer")

            current_hour = new_hour



        else: 

            print(f"{CAM_ID} - Acabando {frame_idx} - {frameId}")

            continue
        print(f"{CAM_ID} - Finishing iter {frame_idx} ")
        
        # We end loop if not new frames are going to arrive
        # if frameId >= NUM_ITERS and NEVEREND == False: 
        #     break

    # CLEANUP AND FINAL DATA HANDLING
    print(f'{CAM_ID} - Camera edge while loop has ended')
    print(f"{CAM_ID} - \n\n\t SmartCity skipped a total of {frameId - frame_idx} frames.")

    # Final data handling based on output mode
    if use_kafka and kafka_producer:
        # KAFKA MODE: Flush remaining messages and close producer
        kafka_producer.flush()  # Ensure all pending messages are sent
        kafka_producer.close()  # Clean shutdown of producer
        print(f"{CAM_ID} - Kafka producer flushed and closed")
    elif save_results and all_results != []:
        # CSV MODE: Save accumulated results to file
        utils.save_results(results, exp_dir, CAM_ID)
        
    # Save alert information if alerts are enabled
    if alerts:
        alarm_file = join(exp_dir, ALERTS_OUT_NAME)
        print(f"{CAM_ID} - Savedir: {alarm_file}")
        with open(alarm_file, 'w') as f:
            f.writelines(alertInfo)
        print(f"{CAM_ID} - save alarms to {alarm_file}")

    # Clean up video resources
    if save_plot: 
        print(f"{CAM_ID} - Releasing video save...")
        cap.release()
        vid_writer.release()
        cv2.destroyAllWindows()
        
    if view_plot and os.environ.get("DISPLAY") is None: 
        print(f"{CAM_ID} - Releasing video sender...")
        cap.release()
        vid_sender.release()
        cv2.destroyAllWindows()
    
    # Close network connections
    print(f"{CAM_ID} - About to close udp")
    udpSock.close()
    print(f"{CAM_ID} - Done receiving from {edge_ip}.\n")

    # Close MQTT connection if alerts were enabled
    if(alerts):
        print(f"{CAM_ID} - About to close mqtt")
        # MQTT client disconnect
        processing.mqttClose()

def main_udp(opt):
    global FINISH_PROGRAM
    # Prepare experiment folder
    # if not os.path.exists(opt.exp_dir):
    #     os.makedirs(opt.exp_dir)
    # exp_vid_dir = join(opt.exp_dir, opt.expn)
    # if not os.path.exists(exp_vid_dir):
    #     os.makedirs(exp_vid_dir)
    #     # shutil.rmtree(exp_vid_dir)
    # opt.exp_dir = exp_vid_dir
    
    if(opt.only_results and not opt.save_results) or (opt.only_results and (opt.save_plot or opt.view_plot or opt.get_speed or opt.get_semantic or opt.alerts)):
         print("Has introducido argumentos incompatibles con only_results.")
         sys.exit()
    
    # Get Kafka configuration from environment variables (Helm chart)
    kafka_env_config = get_kafka_config_from_env()
    
    # Convert edge_ips to a list if needed
    # if (len(opt.edge_ips) > 1):
    #     edge_ips = opt.edge_ips.split(" ")
    # else:
    #     edge_ips = opt.edge_ips
        
    print(f"- - - -  RUN UDP of: {opt.edge_ips} - - - - ")
    
    with ThreadPoolExecutor(max_workers=len(opt.edge_ips)) as executor:
        futures = [
            executor.submit(
            run_udp,
            edge_ip=edge_ip,
            track_thresh=opt.track_thresh,
            track_buffer=opt.track_buffer,
            match_thresh=opt.match_thresh,
            min_box_area=opt.min_box_area,
            tracking_method=opt.tracking_method,
            tracking_config=opt.tracking_config,
            exp_dir=opt.exp_dir,
            expn=opt.expn,
            only_results=opt.only_results,
            save_results=opt.save_results,
            save_plot=opt.save_plot,
            view_plot=opt.view_plot,
            get_speed=opt.get_speed,
            get_semantic=opt.get_semantic,
            alerts=opt.alerts,
            # Add Kafka parameters (use opt attributes, fallback to environment variables from Helm chart)
            use_kafka=getattr(opt, 'use_kafka', True),
            kafka_bootstrap_servers=getattr(opt, 'kafka_bootstrap_servers', kafka_env_config['kafka_bootstrap_servers']),
            kafka_topic=getattr(opt, 'kafka_topic', kafka_env_config['kafka_topic']),
            # Kafka authentication parameters (typically from Helm chart environment variables)
            kafka_username=getattr(opt, 'kafka_username', kafka_env_config['kafka_username']),
            kafka_password=getattr(opt, 'kafka_password', kafka_env_config['kafka_password']),
            kafka_security_protocol=getattr(opt, 'kafka_security_protocol', kafka_env_config['kafka_security_protocol']),
            kafka_sasl_mechanism=getattr(opt, 'kafka_sasl_mechanism', kafka_env_config['kafka_sasl_mechanism']),
            kafka_ssl_cafile=getattr(opt, 'kafka_ssl_cafile', kafka_env_config['kafka_ssl_cafile']),
            kafka_ssl_certfile=getattr(opt, 'kafka_ssl_certfile', kafka_env_config['kafka_ssl_certfile']),
            kafka_ssl_keyfile=getattr(opt, 'kafka_ssl_keyfile', kafka_env_config['kafka_ssl_keyfile']),
            # Schema Registry parameters
            schema_registry_url=getattr(opt, 'schema_registry_url', kafka_env_config['schema_registry_url']),
            schema_registry_username=getattr(opt, 'schema_registry_username', kafka_env_config['schema_registry_username']),
            schema_registry_password=getattr(opt, 'schema_registry_password', kafka_env_config['schema_registry_password']),
            schema_registry_ssl_ca_location=getattr(opt, 'schema_registry_ssl_ca_location', kafka_env_config['schema_registry_ssl_ca_location']),
            schema_registry_ssl_cert_location=getattr(opt, 'schema_registry_ssl_cert_location', kafka_env_config['schema_registry_ssl_cert_location']),
            schema_registry_ssl_key_location=getattr(opt, 'schema_registry_ssl_key_location', kafka_env_config['schema_registry_ssl_key_location']),
            avro_schema_subject=getattr(opt, 'avro_schema_subject', kafka_env_config['avro_schema_subject']),
            use_schema_registry=getattr(opt, 'use_schema_registry', kafka_env_config['use_schema_registry']),
            # Frame-based flush parameters
            kafka_flush_interval=getattr(opt, 'kafka_flush_interval', kafka_env_config['kafka_flush_interval']),
            kafka_auto_flush=getattr(opt, 'kafka_auto_flush', kafka_env_config['kafka_auto_flush'])
            )
            for edge_ip in opt.edge_ips
        ]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"Error en una tarea: {e}")
        
        # reid_weights=opt.reid_weights,
