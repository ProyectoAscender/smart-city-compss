# -*- coding: utf-8 -*-

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
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from kafkaComm.config_loader import load_kafka_config
import comm_udp as comm_udp

# Use datetime timezone instead of ZoneInfo for better compatibility
import pytz
from pycompss.api.api import compss_wait_on
###################################################################
# Import Schema Registry functions from the new module
###################################################################
from kafkaComm.kafka_schema_registry import (
    create_schema_registry_client,
    create_kafka_producer,
    send_tracking_data_to_kafka,
    send_target_to_kafka_or_csv
)
####################################################################
###################################################################
# Hardcoded values
DEFAULT_FPS = 20
VIDEO_OUT_NAME = "video_tracking_output.mp4"
LOG_OUT_NAME = "out.txt"
ALERTS_OUT_NAME = "alarm.txt"
PMAT_DEST_PATH = "./pmat.txt"

# Get host IP
HOST_IP = utils.get_local_ip()

# Global flag for exiting the program gracefully
FINISH_PROGRAM = False
EMPTY_DET = np.empty((0, 6), dtype=np.float32)
def signal_handler(sig, frame):
    global FINISH_PROGRAM
    print("\n[Signal Handler] Ctrl+C clicked! Closing execution...")
    FINISH_PROGRAM = True

signal.signal(signal.SIGINT, signal_handler)

# def save_results_to_csv(results, output_dir, cam_id, frame_idx):
#     """Save tracking results to CSV file"""
#     if not results:
#         return
        
#     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#     csv_filename = f"tracking_results_{cam_id}_{timestamp}.csv"
#     csv_path = os.path.join(output_dir, csv_filename)
    
#     try:
#         with open(csv_path, 'w') as f:
#             # Write header
#             f.write("cam_id,frame_id,timestamp,track_id,x1,y1,w,h,confidence,class\n")
#             # Write results
#             for result in results:
#                 f.write(result)
#         print(f"{cam_id} - Saved {len(results)} results to {csv_path}")
#     except Exception as e:
#         print(f"{cam_id} - Error saving CSV: {e}")

######################################################################
# ======================================================
# Capture base timestamp once at process start (Europe/Madrid local time)
# ======================================================
BASE_TZ = pytz.timezone("Europe/Madrid")
BASE_TIME = datetime.now(BASE_TZ)
BASE_EPOCH_MS = int(BASE_TIME.timestamp() * 1000)

def to_epoch_millis(ts_val):
    """
    Convert various timestamp formats to epoch milliseconds (UTC reference),
    interpreting naive datetimes as Europe/Madrid local time.
    
    If a relative timestamp (seconds/ms/µs) is provided, it is added to BASE_TIME.
    """
    try:
        # --- Case 1: ISO 8601 string ---
        if isinstance(ts_val, str):
            if ts_val.endswith("Z"):
                dt = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
            else:
                dt = datetime.fromisoformat(ts_val)

            # If no timezone → assume Europe/Madrid local time
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=BASE_TZ)

            # Convert to UTC epoch ms
            return int(dt.astimezone(timezone.utc).timestamp() * 1000)

        # --- Case 2: Numeric value ---
        if isinstance(ts_val, (int, float)):
            # Detect scale
            if ts_val > 1e15:       # nanoseconds
                return int(ts_val / 1_000_000)
            elif ts_val > 1e12:     # milliseconds
                return int(ts_val)
            elif ts_val > 1e9:      # seconds
                return int(ts_val * 1000)
            else:
                # Relative seconds → add to base timestamp
                return BASE_EPOCH_MS + int(ts_val * 1000)

    except Exception as e:
        print(f"[to_epoch_millis] Error parsing '{ts_val}': {e}")

    # --- Fallback: current local time ---
    return int(datetime.now(BASE_TZ).timestamp() * 1000)


def run_udp(
        edge_ip=None,
        track_thresh=None,
        track_buffer=None,
        match_thresh=None,
        min_box_area=0,
        #yolo_weights=WEIGHTS / 'yolov5m.pt',  # model.pt path(s),
        reid_weights=None,  # model.pt path,
        tracking_method='bytetrack',
        tracking_config=None,
        exp_dir=None,
        expn=None,
        only_results=False, 
        save_results=True,
        save_plot=False,
        view_plot=False,
        get_semantic=True, 
        get_speed=True,
        alerts=False,
        print_time=True,
        # Kafka configuration dictionary
        kafka_config=None
        ):

    global FINISH_PROGRAM
    #######################################################################################
    # Extract Kafka configuration variables with defaults
    ######################################################################################
    if kafka_config is None:
        kafka_config = {}
    
    # Basic Kafka settings
    use_kafka = kafka_config.get('use_kafka', True)
    kafka_bootstrap_servers = kafka_config.get('kafka_bootstrap_servers', 'localhost:9092')
    kafka_topic = kafka_config.get('kafka_topic', 'smartcity-tracking')
    
    # Authentication settings
    kafka_username = kafka_config.get('kafka_username')
    kafka_password = kafka_config.get('kafka_password')
    kafka_security_protocol = kafka_config.get('kafka_security_protocol', 'PLAINTEXT')
    kafka_sasl_mechanism = kafka_config.get('kafka_sasl_mechanism', 'SCRAM-SHA-512')
    
    # SSL/TLS settings
    kafka_ssl_cafile = kafka_config.get('kafka_ssl_cafile')
    kafka_ssl_certfile = kafka_config.get('kafka_ssl_certfile')
    kafka_ssl_keyfile = kafka_config.get('kafka_ssl_keyfile')
    
    # Schema Registry settings
    schema_registry_url = kafka_config.get('schema_registry_url')
    schema_registry_username = kafka_config.get('schema_registry_username')
    schema_registry_password = kafka_config.get('schema_registry_password')
    schema_registry_ssl_ca_location = kafka_config.get('schema_registry_ssl_ca_location')
    schema_registry_ssl_cert_location = kafka_config.get('schema_registry_ssl_cert_location')
    schema_registry_ssl_key_location = kafka_config.get('schema_registry_ssl_key_location')
    avro_schema_subject = kafka_config.get('avro_schema_subject', 'smartcity-tracking-value')
    use_schema_registry = kafka_config.get('use_schema_registry', False)
    
    # Performance settings
    kafka_flush_interval = kafka_config.get('kafka_flush_interval', 100)
    kafka_auto_flush = kafka_config.get('kafka_auto_flush', True)
    
    print("\n\n\n[udp_handler] Starting UDP-based tracking...")
    print(f"[udp_handler] Configuration - use_kafka: {use_kafka}, only_results: {only_results}")
    print(f"[udp_handler] Kafka config - servers: {kafka_bootstrap_servers}, topic: {kafka_topic}")
    if kafka_username:
        print(f"[udp_handler] Kafka authentication enabled - username: {kafka_username}, protocol: {kafka_security_protocol}")
    else:
        print(f"[udp_handler] Kafka authentication disabled - protocol: {kafka_security_protocol}")
###############################################################################################
#############################################################################################
    # Maybe this should be inside the for loop? one tracker per edge device????
    # Create as many track instances as there are video sources
    # TO - DO : si cada run se paraleliza para cada vídeo, aqui no paralelizamos nada, pero podriamos tener mas de un tracker para solo una camara -> approach paddle padlle
    tracker_list = []
    # print(f'- Creating tracker for {opt.source} - ')
    tracker = create_tracker(tracking_method, tracking_config, reid_weights)
    tracker_list.append(tracker, )
    ###################################################################################################
    # Initialize Schema Registry client if enabled
    ################################################################################################
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
            topic_name=kafka_topic,   #  pass the real topic here (now required)
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
            use_schema_registry=use_schema_registry,
        )

        if kafka_producer:
            print(f"[udp_handler] Kafka producer initialized for topic: {kafka_topic}")
        else:
            print(f"[udp_handler] Failed to initialize Kafka producer, falling back to CSV")
            use_kafka = False
    ################################################################################################
    #################################################################################################
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
    #############################################################################################
    # after kafka_producer is created
    last_flush_time = time.time() if (use_kafka and kafka_producer) else 0.0
    FLUSH_EVERY_SECS = 5.0  # tune as needed
    ###########################################################################################
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
    timers = {name: Timer() for name in ['track', 'frame_reception', 'udp_decoding','udp_wait_reception', 'processing', 'speed', 'video', 'semantics', 'total', 'saving_results']}
            
    # Variable inicialization:
    skiped_frames = 0
    fps_est = DEFAULT_FPS  # Initialize FPS estimation
    
    # # Initialize output directory for saving results
    # if exp_dir:
    #     output_dir = os.path.join(exp_dir, datetime.now().strftime("%Y%m%d"), CAM_ID)
    #     os.makedirs(output_dir, exist_ok=True)
    # else:
    #     output_dir = "./output"
    #     os.makedirs(output_dir, exist_ok=True)
    
    # Prepare storage for bounding-box results
    results = []
    all_results = []
    if (alerts): alertInfo = []
    # current_hour = datetime.now().strftime("%H")
    
    print('Iterating frames')
    ######################### LOOP ITERATING FRAMES ########################
    # We loop indefinitely or until some condition
    # while frame_idx < NUM_ITERS:
    # Loop changed because Smart City can be faster than camera-edge
    while frameId <= NUM_ITERS or NEVEREND == True:
          
        timers['total'].tic()
        hex_data = ""                 
        new_hour = int(datetime.now().strftime("%M"))  
        frame_idx += 1
        ###         Probably moving this to a separate thread would be nice... to fully decouples compute from IO.

        timers['udp_wait_reception'].tic()
        # Loop to get the last message
        udpSock.setblocking(False)
        
        while True:
            if FINISH_PROGRAM:
                break   
            try: 
                # Receiving boxes. Como address no nos importa, no lo guardamos como _
                hex_data, _ = udpSock.recvfrom(16000)  # bigger buffer if needed
            except BlockingIOError as b:
                if(hex_data==""):   # hex_data is set to "" at the end of the processing loop
                    # print(f"[main.py - {CAM_ID}] No bounding box data, continuing...")
                    continue
                timers['udp_wait_reception'].toc()
                break

        udpSock.setblocking(True)
        if FINISH_PROGRAM:
            break
        
        timers['frame_reception'].tic()
    
        # Receiving frame if needed
        if save_plot or view_plot:
            ret, frame = cap.read()
            if not ret:
                print(f"{CAM_ID} - No hay captura. Salto siguiente iter.")
                break
            else:
                print('--- > frame received')
            # cv2.imwrite(f"./{frame_idx}_received.jpg", frame)
            
        timers['frame_reception'].toc()
        timers['udp_decoding'].tic()
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
        
        ###############################################################################
        # Convert to epoch milliseconds (UTC reference)
        # Ensure timestamp is properly converted to long integer for Avro schema compatibility
        try:
            ts_ms = int(to_epoch_millis(ts))
        except (ValueError, TypeError):
            # Fallback to current timestamp if conversion fails
            ts_ms = int(time.time() * 1000)
            print(f"{CAM_ID} - Warning: Invalid timestamp '{ts}', using current time: {ts_ms}")

        #############################################################################

        det = EMPTY_DET
        # Checking case zero info in frameData
        if not frameData:
            print(f'{CAM_ID} - No frameData: UDP hexadecimal decode failed')
        elif len(frameData[0]) <= 4:  #  can have 0 detections, only one row with frame info data
            print(f'{CAM_ID} - 0 detections received')
        else:
            # Last 6 elements from frame data are the detections: [x,y,w,h,score,classId]
            det = np.asarray([box[-6:] for box in frameData])
            
        timers['udp_decoding'].toc()

        timers['track'].tic()
        # ## TRACKING
         

        ### Bug REPORT  -   Tracker, according to the log analysis, seems to be the sole responsible for loosing 

        ###                 Real Time processing over time. 

        ###                 ByteTrack/StrongSORT-like trackers expect update every frame to age/prune tracks 

        ###                 (track_buffer, timeouts, merges, duplicate removal, etc.). Skipping it lets 

        ###                 tracked_stracks/lost_stracks quietly balloon, making each subsequent update slower and 

        ###                 the downstream processing loop heavier.

        ###                 Possibly issues caused by:
        # # Frames con detecciones
        # if isinstance(det, np.ndarray) and det.size > 0:
        #     # Update tracker
        #     online_targets = tracker_list[0].update(det, img_info, test_size)

        # # Frames sin detecciones. Actualizamos el tracker
        # else:
        #     tracker_list[0].frame_id += 1  # Avanzamos el frame_id manualmente
        #     for track in tracker_list[0].tracked_stracks:
        #         track.frames_since_update += 1  # Incrementamos contador de no actualización
        #     online_targets = []            
        #     #print('Actualizando tracker sin nuevas detecciones ')
        ###                 Attempt to fix it 1:
        ###                 det gets created already with the correct shape, only fills if boxes okay
        
        online_targets = tracker_list[0].update(det, img_info, test_size)

        # Collect and write results if online targets is not empty
        online_tlwhs = []
        online_ids = []
        online_scores = []
        if (get_speed): online_speeds = []
        # Discard non-consolidated data

        online_targets = [t for t in online_targets if t.tlwh[2] * t.tlwh[3] > min_box_area]
        # Add track info to results 
        frame_results = []
        for i, t in enumerate(online_targets):

            # tlwh = t.tlwh

            # tid = t.track_id

            online_tlwhs.append(t.tlwh)

            online_ids.append(t.track_id)

            online_scores.append(t.score)

            

            line = (f"\n{CAM_ID},{frameId},{ts},{t.track_id},"

                    f"{t.tlwh[0]:.2f},{t.tlwh[1]:.2f},{t.tlwh[2]:.2f},{t.tlwh[3]:.2f},"

                    f"{t.score:.2f},{t.cl}")

            frame_results.append(line)

            results.append(line)  # results global, si lo quieres

            # online_flags(t.event.alertFlag)

            

        timers['track'].toc()
        
        # After results append, if "only_results" we dont need to process anything else of this frame
        ##########################################################################################
        #ADD option to only send results to Kafka or CSV, without any other processing
        #########################################################################################
        print(f"[UDP DEBUG] Checking only_results condition - only_results: {only_results} (type: {type(only_results)})")
        if (only_results): 
            timers['saving_results'].tic()
            
            print(f"\t -> Running on ONLY_RESULTS mode - only_results={only_results}")
            # FRAME-BASED FLUSH MANAGEMENT
            # Implement intelligent flushing strategy for optimal performance vs latency
            if use_kafka and kafka_producer:
                # In only_results mode, we don't have valid UTM data (would be 0.0)
                # So we skip Kafka and only use CSV mode for basic tracking data
                print(f"{CAM_ID} - Skipping Kafka in only_results mode - no valid UTM data available")
                # Convert to CSV mode for only_results
                for i, t in enumerate(online_targets):
                    results.append(
                        f"{CAM_ID},{frameId},{ts},{t.track_id},{t.tlwh[0]:.2f},{t.tlwh[1]:.2f},{t.tlwh[2]:.2f},{t.tlwh[3]:.2f},{t.score:.2f},{getattr(t, 'cl', 0)}\n"
                    )
            else:
                # CSV mode: accumulate results
                for i, t in enumerate(online_targets):
                    results.append(
                        f"{CAM_ID},{frameId},{ts},{t.track_id},{t.tlwh[0]:.2f},{t.tlwh[1]:.2f},{t.tlwh[2]:.2f},{t.tlwh[3]:.2f},{t.score:.2f},{getattr(t, 'cl', 0)}\n"
                    )
            
            timers['saving_results'].toc()
            print(f"{CAM_ID} - Acabando {frame_idx} - {frameId}")
            continue
        

        #Calcualte speed and semantics if needed
        #####################################################################################
        print(f"[UDP DEBUG] Entering normal processing mode (NOT only_results)")
        timers['processing'].tic()
        futures = []
        for t in online_targets:
            tModified , alertInfo_thread, online_speeds_thread,  t_speed_thread, t_semantics_thread = processing.process_tracklets(t, view_transformer, timers, get_semantic, 

                                                            get_speed , alerts , polys, ts, frameId) 

            futures.append((tModified , alertInfo_thread, online_speeds_thread,  t_speed_thread, t_semantics_thread))
        # Discard non-consolidated data

        
        for i, future in enumerate(futures):
            try:

                # print('XX compss_wait_on...')

                t = online_targets[i] = compss_wait_on(future[0])

                alertInfo_task = compss_wait_on(future[1])

                online_speeds_task = compss_wait_on(future[2])

                t_speed_task = compss_wait_on(future[3])

                t_semantics_task = compss_wait_on(future[4])



                # print(f'XX Task output: {online_targets[i]} {alertInfo_task} {online_speeds_task} {t_speed_task} {t_semantics_task}')

                if(alerts):

                    alertInfo.append(alertInfo_task)

                if(get_speed):

                    online_speeds.append(online_speeds_task)

                all_results.append(

                        f"{frame_results[i]},{online_targets[i].location[0]},{online_targets[i].location[1]},"

                        f"{online_targets[i].median_speed:.2f},{online_targets[i].event.polyType}"

                    )
                
                timers['speed'].toc(value=t_speed_task)

                timers['semantics'].toc(value=t_semantics_task) 
                
                # Send tracking data to Kafka or append to CSV results
                send_target_to_kafka_or_csv(t, i, CAM_ID, frameId, ts_ms, use_kafka, 
                                          kafka_producer, kafka_topic, results)



            except Exception as e:

                print(f"{CAM_ID} - Error receiving compss data: {e}")

                sys.exit(1)
                
        timers['processing'].toc()
        #####################################################################################
        # BUILD AND SEND TRACKING DATA TO KAFKA
        # 
        # IMPORTANT: Kafka processing is placed OUTSIDE the COMPSs futures loop for the following reasons:
        # 
        # 1. AVOID DUPLICATE SENDS: Previously, Kafka processing was inside the COMPSs loop,
        #    causing the same tracking data to be sent multiple times to Kafka (once per future).
        # 
        # 2. CORRECT TIMING: We need to wait until ALL COMPSs futures complete and populate
        #    the online_targets with location, speed, and event data before sending to Kafka.
        # 
        # 3. VARIABLE CONFLICTS: The inner loop used the same variable 'i' as the outer loop,
        #    causing confusion and potential bugs. Now using 'j' for clear separation.
        # 
        # 4. CLEAN ARCHITECTURE: Separates COMPSs processing (compute-intensive) from
        #    Kafka processing (I/O-intensive) for better code maintainability.
        # 
        # Process each detected object and send to Kafka or store for CSV
        #########################################################################################
        # for j, t in enumerate(online_targets):
        #     #####################################################################
        #     # Extract UTM values from track object (proper source)
        #     print(f"{CAM_ID} - Debug: Processing target {j}: {t}")
        #     print(f"{CAM_ID} - Debug: t.location: {getattr(t, 'location', 'NO LOCATION ATTR')}")
        #     print(f"{CAM_ID} - Debug: t.median_speed: {getattr(t, 'median_speed', 'NO SPEED ATTR')}")
        #     print(f"{CAM_ID} - Debug: t.event: {getattr(t, 'event', 'NO EVENT ATTR')}")
            
        #     utm_x_m = float(t.location[0])
        #     utm_y_m = float(t.location[1])
        #     speed_kmh = float(getattr(t, "median_speed", 0.0))
        #     polygon_type = getattr(getattr(t, "event", None), "polyType", None)
            
        #     print(f"{CAM_ID} - Debug: Extracted - utm_x_m: {utm_x_m}, utm_y_m: {utm_y_m}, speed_kmh: {speed_kmh}, polygon_type: {polygon_type}")
        #     #########################################################################
        #     # Only send to Kafka if UTM values are valid (not 0 and not None)
        #     utm_valid = utm_x_m != 0.0 and utm_y_m != 0.0 and utm_x_m is not None and utm_y_m is not None
        #     if use_kafka and kafka_producer and utm_valid:
        #         # Build Kafka message data
        #         data = {
        #             "cam_id": str(CAM_ID),
        #             "frame_id": int(frameId),
        #             "ts": int(ts_ms),  # Use converted timestamp
        #             "track_id": int(t.track_id),
        #             "coord_box1": float(t.tlwh[0]),
        #             "coord_box2": float(t.tlwh[1]),
        #             "coord_box3": float(t.tlwh[2]),
        #             "coord_box4": float(t.tlwh[3]),
        #             "box_score": float(t.score),
        #             "class_box": int(getattr(t, 'cl', 0)),
        #             "utm": {
        #                 "utm_x_m": utm_x_m,
        #                 "utm_y_m": utm_y_m,
        #                 "speed_kmh": speed_kmh,
        #                 "polygon_type": polygon_type
        #             }
        #         }
                
        #         # Send to Kafka
        #         success = send_tracking_data_to_kafka(kafka_producer, kafka_topic, data, CAM_ID)
        #         if not success:
        #             print(f"{CAM_ID} - Failed to send tracking data to Kafka")
        #         else:
        #             print(f"{CAM_ID} - Successfully sent tracking data to Kafka (UTM: {utm_x_m}, {utm_y_m})")
        #     elif use_kafka and kafka_producer and not utm_valid:
        #         print(f"{CAM_ID} - Skipping Kafka send - invalid UTM values (utm_x_m: {utm_x_m}, utm_y_m: {utm_y_m}, track_id: {t.track_id})")
        #     else:
        #         # CSV mode
        #         results.append(
        #             f"{CAM_ID},{frameId},{ts},{t.track_id},{t.tlwh[0]:.2f},{t.tlwh[1]:.2f},{t.tlwh[2]:.2f},{t.tlwh[3]:.2f},{t.score:.2f},{getattr(t, 'cl', 0)}\n"
        #         )

        
        # AUTOMATIC FLUSH FOR LOW-LATENCY DELIVERY
        # Optional immediate flush after sending data for ultra-low latency scenarios
        # Periodic flush (frame- or time-based, or hour change)
        if use_kafka and kafka_producer:
            # Periodic flush management
            if kafka_flush_interval > 0 and frame_idx % kafka_flush_interval == 0:
                kafka_producer.flush()
                print(f"{CAM_ID} - Kafka producer flushed (frame {frame_idx})")
            elif kafka_auto_flush and (time.time() - last_flush_time > FLUSH_EVERY_SECS):
                kafka_producer.flush()
                last_flush_time = time.time()
                print(f"{CAM_ID} - Kafka producer auto-flushed")
            
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
###############################################################################################
##########################################################################################3#####
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
            for name, timer in timers.items():

                print(f'{CAM_ID} - Avg. {name.capitalize()} Time: {timer.average_time}')                

                timer.clear()

            timers['total'].tic()

        timers['total'].toc() 
        
        if (print_time and frame_idx % 30 == 0):
            print(f"{CAM_ID} - Average FPS: {fps_est:.2f}, Frame {frame_idx}")
            
        # We check again and save results with speed
        if (frame_idx % 300 == 0 and new_hour != current_hour):
              

            timers['saving_results'].tic()

            

            

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
            timers['saving_results'].toc()
            timers['total'].toc() 


            # if not use_kafka:
            #     save_results_to_csv(results, output_dir, CAM_ID, frame_idx)
        else: 
            print(f"{CAM_ID} - Acabando {frame_idx} - {frameId} - {tm.time()}")
            timers['total'].toc() 
            continue  # Continue normal processing
            
        print(f"{CAM_ID} - Finishing iter {frame_idx} ")
        
        # We end loop if not new frames are going to arrive
        # if frameId >= NUM_ITERS and NEVEREND == False: 
        #     break

    # CLEANUP AND FINAL DATA HANDLING
    print(f'{CAM_ID} - Camera edge while loop has ended')
    print(f"{CAM_ID} - \n\n\t SmartCity skipped a total of {frameId - frame_idx} frames.")
#####################################################################################################
    # Final data handling based on output mode
#####################################################################################################
    if use_kafka and kafka_producer:
        # KAFKA MODE: Flush remaining messages and close producer
        kafka_producer.flush()  # Ensure all pending messages are sent
        kafka_producer.close()  # Clean shutdown of producer
        print(f"{CAM_ID} - Kafka producer flushed and closed")
    elif save_results and all_results != []:
        # CSV MODE: Save accumulated results to file
        utils.save_results(all_results, exp_dir, CAM_ID)
        
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
    ############################################################################
    # Get Kafka configuration from environment variables (Helm chart)
    # kafka_env_config = get_kafka_config_from_env()
    kafka_config = load_kafka_config(opt)
#######################################################################################
    # Convert edge_ips to a list if needed
    # if (len(opt.edge_ips) > 1):
    #     edge_ips = opt.edge_ips.split(" ")
    # else:
    #     edge_ips = opt.edge_ips
        
    print(f"- - - -  RUN UDP of: {opt.edge_ips} - - - - ")
    # Run one thread per edge_ip
    with ThreadPoolExecutor(max_workers=len(opt.edge_ips)) as executor:
        futures = [
            executor.submit(run_udp, 
                            edge_ip=edge_ip,
                            kafka_config=kafka_config,
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
                            alerts=opt.alerts
                           )
            for edge_ip in opt.edge_ips
        ]
        for future in as_completed(futures):
            try:

                future.result()

            except Exception as e:

                print(f"Error en una tarea: {e}")

        

        # reid_weights=opt.reid_weights,

