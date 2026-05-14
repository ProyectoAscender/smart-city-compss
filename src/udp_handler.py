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
from src import csv_mode, utils, event, processing
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import comm_udp as comm_udp

from pycompss.api.api import compss_wait_on

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


# Global for det
EMPTY_DET = np.empty((0, 6), dtype=np.float32)



def signal_handler(sig, frame):
    global FINISH_PROGRAM
    print("\n[Signal Handler] Ctrl+C clicked! Closing execution...")
    FINISH_PROGRAM = True

signal.signal(signal.SIGINT, signal_handler)

def run_udp(
        mode='udp',
        edge_ip=None,
        track_thresh = None,
        track_buffer = None,
        match_thresh = None,
        min_box_area = 0,
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
        print_time = True
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
    

    print(f"Handling edge_ip: {edge_ip}")
    csv_realtime = False

    # Si el modo es 'csv', obtener info de variables de entorno y saltar UDP
    if (mode == 'csv'):
        csv_config = csv_mode.load_csv_mode_config(DEFAULT_FPS)
        selected_hours, source_csv_scan_path = csv_mode.select_csv_hours(csv_config["SOURCE_DATA_PATH"])
        csv_mode.sync_csv_inputs(csv_config, selected_hours)
        CAM_ID = csv_config['CAM_ID']
        MULTICAST = csv_config['MULTICAST']
        NEVEREND = csv_config['NEVEREND']
        NUM_ITERS = csv_config['NUM_ITERS']
        CAM_HEIGHT = csv_config['CAM_HEIGHT']
        CAM_WIDTH  = csv_config['CAM_WIDTH']
        DATA_PATH = csv_config['DATA_PATH']
        CITY = csv_config['CITY']
        AREA = csv_config['AREA']
        ROI_PATH = csv_config['ROI_PATH']
        PMAT_PATH = csv_config['PMAT_PATH']
        FPS = csv_config['FPS']
        csv_realtime = csv_config['CSV_REALTIME']
        if (not os.path.exists(PMAT_DEST_PATH)) or (os.stat(PMAT_PATH).st_mtime - os.stat(PMAT_DEST_PATH).st_mtime > 1) :
            shutil.copy2 (PMAT_PATH, PMAT_DEST_PATH)
        view_transformer = ViewTransformer(pmatPath = "./pmat.txt")
        img_info = [CAM_HEIGHT, CAM_WIDTH]
        test_size = (img_info[0], img_info[1])
    else:
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
        CITY = DATA_PATH.split(os.path.sep)[0]
        AREA = DATA_PATH.split(os.path.sep)[1]
        DATA_PATH = os.path.join( 'data', DATA_PATH)
        ROI_PATH = DATA_PATH + '/roi/' + AREA.lower() + '_' + CAM_ID + '.json'
        PMAT_PATH = utils.find_files_by_strings(os.path.join(DATA_PATH, 'pmat'), CAM_ID, "ACTIVE")[0]
        if (not os.path.exists(PMAT_DEST_PATH)) or (os.stat(PMAT_PATH).st_mtime - os.stat(PMAT_DEST_PATH).st_mtime > 1) :
            shutil.copy2 (PMAT_PATH, PMAT_DEST_PATH)
        view_transformer = ViewTransformer(pmatPath = "./pmat.txt")
        img_info = [CAM_HEIGHT, CAM_WIDTH]
        test_size = (img_info[0], img_info[1]) # We don't want to re-scale yet

    # Optinal saving or visualizing video. Both ways requires get processed frames from camera-edge.
    if view_plot or save_plot:
        
        # Gstreamer input from camera edge. ONLY processed frames are sent and received trough here.
        gst_str = (
            "udpsrc port=5002 multicast-group=239.255.12.41 auto-multicast=true ! "
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

    current_hour = int(datetime.now().strftime("%H"))
    # Prepare video save output
    if save_plot:

        # now_minus_1m = datetime.now() - timedelta(minutes=1)
        folder_path = os.path.join(exp_dir,
                               datetime.now().strftime("%Y%m%d"), 
                               datetime.now().strftime("%H%M"),
                               CAM_ID)
         
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
            
    # Abrir fichero de tracklets si modo csv
    _csv_groups = None
    if mode == 'csv':
        selected_hours, selected_csv_paths, _csv_groups, csv_scan_path = csv_mode.prepare_csv_groups(DATA_PATH, selected_hours)
        print(f'{CAM_ID} - CSV mode: hours selected {selected_hours}')
        print(f'{CAM_ID} - CSV mode: reading {len(selected_csv_paths)} CSV files from {csv_scan_path}')

    # If semantics enabled, load polygons:
    if(get_semantic):
        print(f'{CAM_ID} - Loading Polygons')
        polys = utils.getPolysRoi(ROI_PATH)
    else:
        polys = []

    frame_idx = 0
    frameId = 0
    ts = 0
    ts_reception = datetime.now()
    csv_frame_interval = (1.0 / FPS) if mode == 'csv' and csv_realtime and FPS > 0 else 0.0
    csv_next_read_ts = None
    # Time inicialization
    timers = {name: Timer() for name in ['track', 'frame_reception', 'udp_decoding','udp_wait_reception', 'processing', 'speed', 'video', 'semantics', 'total', 'saving_results']}
            
    # Variable inicialization:
    skiped_frames = 0
    
    
    # Prepare storage for bounding-box results
    results = []
    all_results = []
    if (alerts): alertInfo = []
    
    print('Iterating frames')
    ######################### LOOP ITERATING FRAMES ########################
    # We loop indefinitely or until some condition
    # while frame_idx < NUM_ITERS:
    # Loop changed because Smart City can be faster than camera-edge
    while not FINISH_PROGRAM and (mode == 'csv' or frameId <= NUM_ITERS or NEVEREND == True):
        timers['total'].tic()
        hex_data = ""
        new_hour = int(datetime.now().strftime("%H"))  
        frame_idx += 1
        

        ######### DATA RECEPTION #########
        ###### CSV 
        timers['udp_wait_reception'].tic()
        if mode == 'csv':
            if csv_realtime and csv_next_read_ts is not None:
                sleep_time = csv_next_read_ts - tm.time()
                if sleep_time > 0:
                    tm.sleep(sleep_time)
            if csv_realtime:
                csv_next_read_ts = tm.time() + csv_frame_interval
            # Leer todas las filas que comparten el mismo frameId
            group = next(_csv_groups, None)
            if group is None:
                FINISH_PROGRAM = True
                timers['udp_wait_reception'].toc()
                break 
            else:
                _fid_str, rows = group
                rows = list(rows)
                frameId = int(_fid_str)
                ts = float(rows[0][2])
                ts_reception = datetime.now()
                det = np.array([[float(r[5]), float(r[6]), float(r[7]), float(r[8]), float(r[9]), int(r[10])] for r in rows])
            timers['udp_wait_reception'].toc()
        else:
            # Lógica UDP original
            udpSock.setblocking(False)
            while True:
                if FINISH_PROGRAM:
                    break   
                try: 
                    hex_data, address = udpSock.recvfrom(16000)
                    ts_reception = datetime.now()
                except BlockingIOError as b:
                    if(hex_data==""):
                        continue
                    timers['udp_wait_reception'].toc()
                    break
            udpSock.setblocking(True)
            if FINISH_PROGRAM:
                break
        
        timers['frame_reception'].tic()
        ######### FRAME RECEPTION FOR PLOT #########
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


        if mode != 'csv':
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
        
        
        ## TRACKING
        
        timers['track'].tic()
        
        ### BUG REPORT  -   Tracker, according to the log analysis, seems to be the sole responsible for loosing 
        ###                 Real Time processing over time. 
        ###                 ByteTrack/StrongSORT-like trackers expect update every frame to age/prune tracks 
        ###                 (track_buffer, timeouts, merges, duplicate removal, etc.). Skipping it lets 
        ###                 tracked_stracks/lost_stracks quietly balloon, making each subsequent update slower and 
        ###                 the downstream processing loop heavier.
        
        
        ###                 Possibly issues caused by:
        # # Frames con detecciones
        # if det != []:
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
            
            line = (f"\n{CAM_ID},{frameId},{ts},{ts_reception},{t.track_id},"
                    f"{t.tlwh[0]:.2f},{t.tlwh[1]:.2f},{t.tlwh[2]:.2f},{t.tlwh[3]:.2f},"
                    f"{t.score:.2f},{t.cl}")
            frame_results.append(line)
            results.append(line)  # results global, si lo quieres
            # online_flags(t.event.alertFlag)
            

        timers['track'].toc()
        
        

        
        # After results append, if "only_results" we dont need to process anything else of this frame
        if (only_results): 
            timers['saving_results'].tic()
            
            print(f"\t -> Running on ONLY_RESULTS mode - only_results={only_results}")
            # We've checked every 300 frames if hour has changed.
            if (frame_idx % 300 == 0 and new_hour != current_hour):
                utils.save_results(results, exp_dir, CAM_ID)
                current_hour = new_hour
                results = []
                print(f"{CAM_ID} - Saving every 300 frames")
                
                timers['saving_results'].toc()
            else: 
                print(f"{CAM_ID} - Acabando {frame_idx} - {frameId}")
                
                timers['saving_results'].toc()
                
                continue
            
        
        
        
        timers['processing'].tic()
        futures = []
        for t in online_targets:
            tModified , alertInfo_thread, online_speeds_thread,  t_speed_thread, t_semantics_thread = processing.process_tracklets(t, view_transformer, timers, get_semantic, 
                                                            get_speed , alerts , polys, ts, frameId) 
            futures.append((tModified , alertInfo_thread, online_speeds_thread,  t_speed_thread, t_semantics_thread))
            
        for i, future in enumerate(futures):
            try:
                # print('XX compss_wait_on...')
                online_targets[i] = compss_wait_on(future[0])
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

            except Exception as e:
                print(f"{CAM_ID} - Error receiving compss data: {e}")
                sys.exit(1)
        timers['processing'].toc()




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

        
        if (print_time and frame_idx % 30 == 0):
            print(f'{CAM_ID} - Info every 30 frames - frameidx: {frame_idx}')
            timers['total'].toc()
            
            
            for name, timer in timers.items():
                print(f'{CAM_ID} - Avg. {name.capitalize()} Time: {timer.average_time}')                
                timer.clear()
                
                
            timers['total'].tic()
        
        
        
        
        
        
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

        
        else: 
            print(f"{CAM_ID} - Acabando {frame_idx} - {frameId} - {tm.time()}")
            
            timers['total'].toc() 
            
            
            continue
        
        print(f"{CAM_ID} - Finishing iter {frame_idx} ")
        
        # We end loop if not new frames are going to arrive
        # if frameId >= NUM_ITERS and NEVEREND == False: 
        #     break

        
        
        
        
        
        
        
        
        
    # WHILE ENDED

    print(f'{CAM_ID} - Camera edge while loop has ended')
    print(f"{CAM_ID} - \n\n\t SmartCity skipped a total of {frameId - frame_idx} frames.")

    if save_results and all_results != []:
        utils.save_results(all_results, exp_dir, CAM_ID)
        
    if alerts:
        alarm_file = join(exp_dir, ALERTS_OUT_NAME)
        print(f"{CAM_ID} - Savedir: {alarm_file}")
        with open(alarm_file, 'w') as f:
            f.writelines(alertInfo)
        print(f"{CAM_ID} - save alarms to {alarm_file}")

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
    
    if mode != 'csv':
        print(f"{CAM_ID} - About to close udp")
        udpSock.close()
        print(f"{CAM_ID} - Done receiving from {edge_ip}.\n")

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
    
    incompatible_only_results = (
        (opt.only_results and not opt.save_results) or
        (opt.only_results and (opt.save_plot or opt.view_plot or opt.get_speed or opt.get_semantic or opt.alerts))
    )
    incompatible_csv_mode = (
        opt.mode == 'csv' and (opt.save_plot or opt.view_plot)
    )

    if incompatible_only_results:
        print("Error: argumentos incompatibles con --only_results.")
        sys.exit(1)
    if incompatible_csv_mode:
        print("Error: --save_plot y --view_plot no son compatibles con --mode=csv.")
        sys.exit(1)
    
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
            mode=opt.mode,
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
