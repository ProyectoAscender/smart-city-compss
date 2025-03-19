import cv2
import os
from os.path import join
from src.timer import Timer
from src.visualize import plot_tracking
from trackers.multi_tracker_zoo import create_tracker
from src.viewTransform import ViewTransformer
from src import utils
import numpy as np
import shutil
import time as tm
import socket
import signal
import sys

import comm_udp as comm_udp



# Hardcoded values
DEFAULT_FPS = 30
VIDEO_OUT_NAME = "video_tracking_output.mp4"
LOG_OUT_NAME = "out.txt"
ALERTS_OUT_NAME = "alarm.txt"
PMAT_DEST_PATH = "./pmat.txt"


# Global flag for exiting the program gracefully
FINISH_PROGRAM = False

def signal_handler(sig, frame):
    global FINISH_PROGRAM
    print("\n[Signal Handler] Ctrl+C clicked! Closing execution...")
    FINISH_PROGRAM = True

signal.signal(signal.SIGINT, signal_handler)



def run_udp(
        edge_ips=None,
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
        save_results = True,
        save_plot = False,
        view_plot = False,
        get_speed = True,
        alerts = True
        ):

    global FINISH_PROGRAM
    
    print("\n\n\n[udp_handler] Starting UDP-based tracking...")
    
    # Convert edge_ips to a list if needed
    if isinstance(edge_ips, str):
        edge_ips = edge_ips.split(" ")
        
    
    # Maybe this should be inside the for loop? one tracker per edge device????
    # Create as many track instances as there are video sources
    # TO - DO : si cada run se paraleliza para cada vídeo, aqui no paralelizamos nada, pero podriamos tener mas de un tracker para solo una camara -> approach paddle padlle
    tracker_list = []
    # print(f'- Creating tracker for {opt.source} - ')
    tracker = create_tracker(tracking_method, tracking_config, reid_weights)
    tracker_list.append(tracker, )
    
    
    # For each Edge Device, do handshake, connect UDP
    # This could be parallel, so that each edge device is processed at once
    for edge_device in edge_ips:
        if FINISH_PROGRAM:
            break
        
        print(f"[udp_handler] Handling edge_ip: {edge_device}")
        
        # parse "host:port"
        host, port_str = edge_device.split(":")
        port = int(port_str)
        
        # Create a UDP socket with configuration params
        udpSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udpSock.settimeout(5.0)  # timeout for individual attempts
        max_retries=150
        retry_delay=1
        
        # handshake to get camera info
        try:
            info = comm_udp.handshake_and_get_info(udpSock, host, port, max_retries, retry_delay)
            print(f"[udp_handler] Camera info: {info}")
        except socket.timeout:
            print("[udp_handler] Handshake timeout!")
            continue

        # GET EDGE INFO:
        CAM_ID = info["cam_id"]
        GSTREAMER = int(info["gstreamer"])
        NUM_ITERS = int(info["frames_to_process"])
        CAM_HEIGHT = int(info["cam_height"])
        CAM_WIDTH  = int(info["cam_width"])
        DATA_PATH = info["data_path"].replace("'", "")
        DATA_PATH = os.path.join(*(DATA_PATH.split(os.path.sep)[3:-1]))
        # videoPath = os.path.join( 'data', DATA_PATH, "videos/20230721_092248_cam01h264.mp4")
        CITY = DATA_PATH.split(os.path.sep)[0]
        AREA = DATA_PATH.split(os.path.sep)[1]
        DATA_PATH = os.path.join( 'data', DATA_PATH)
    
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

        # Optinal saving or visualizing video stuff. Initialization.
        if save_plot or view_plot:

            gst_str = (
                    "udpsrc port=5001 multicast-group=239.255.12.42 auto-multicast=true ! "
                    "application/x-rtp,media=video,clock-rate=90000,encoding-name=H264 ! "
                    "rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! appsink"
                )
            
            
            cap = cv2.VideoCapture(gst_str, cv2.CAP_GSTREAMER)
            if not cap.isOpened():
                print("Failed to open GStreamer pipeline for receiving processed frames")
                exit(1)
        
            vid_fps = cap.get(cv2.CAP_PROP_FPS)
            FPS = vid_fps if int(vid_fps) > 0 else DEFAULT_FPS
            
            # Prepare video output
            out_path = join(exp_dir, VIDEO_OUT_NAME)
            print(out_path)
            video_format = 'MP4V'
            fourcc = cv2.VideoWriter_fourcc(*video_format)
            print(f'Saving video. Path: {out_path} | fps: {FPS} | resolution: {CAM_WIDTH}x{CAM_HEIGHT}')
            vid_writer = cv2.VideoWriter(out_path, fourcc, FPS, (CAM_WIDTH, CAM_HEIGHT))



        ## LOOP ITERATING FRAMES:
        frame_idx = 0
        timer_track = Timer()
        timer_reception = Timer()
        timer_wait_recv = Timer()
        timer_speed = Timer()
        timer_video = Timer()
        timer_alerts = Timer()
        
        hex_data = ""
        skiped_frames = 0

        # Prepare storage for bounding-box results
        results = []
        alertInfo = []
        
        # We loop indefinitely or until some condition
        while frame_idx < NUM_ITERS:                            
            frame_idx += 1
            
            # Loop to get the last message
            udpSock.setblocking(False)
            timer_wait_recv.tic()
            while True:
                if FINISH_PROGRAM:
                    break   
                try:
                    hex_data, address = udpSock.recvfrom(16000)  # bigger buffer if needed
                    
                except BlockingIOError as b:
                    if(hex_data==""):   # hex_data is set to "" at the end of the processing loop
                        # print("[main.py] No bounding box data, continuing...")
                        continue

                    timer_wait_recv.toc()
                    break
            
            udpSock.setblocking(True)
            if FINISH_PROGRAM:
                break
            
            timer_reception.tic()
        
            # Decode the message as per our template            
            frameData = list(comm_udp.decode_hex_bboxes(hex_data))      
            
            frameId = frameData[0][2]
            ts = frameData[0][3]

            det = []
            # Checking because message can have 0 detections, only one row with frame info data
            if (len(frameData[0]) > 4):
                # Detections to numpy array [x,y,w,h,score,classId]
                det = np.asarray([box[-6:-1] for box in frameData])  # by now,without classId
            
            timer_reception.toc()

            print(f"Processing Frame {frameId} with time stamp: {ts}")

            timer_track.tic()

            ## TRACKING
            # Frames con detecciones
            if det != []:
                # Update tracker
                online_targets = tracker_list[0].update(det, img_info, test_size)

            # Frames sin detecciones. Actualizamos el tracker
            else:
                tracker_list[0].frame_id += 1  # Avanzamos el frame_id manualmente
                for track in tracker_list[0].tracked_stracks:
                    track.frames_since_update += 1  # Incrementamos contador de no actualización
                online_targets = []            
                print('Actualizando tracker sin nuevas detecciones ')
            
            
             
            # Collect and write results if online targets is not empty
            online_tlwhs = []
            online_ids = []
            online_scores = []
            online_speeds = []
            for i, t in enumerate(online_targets):
                tlwh = t.tlwh
                tid = t.track_id
                if tlwh[2] * tlwh[3] > min_box_area: 
                    online_tlwhs.append(tlwh)
                    online_ids.append(tid)
                    online_scores.append(t.score)
                    results.append(
                        f"{frameId},{ts},{tid},{tlwh[0]:.2f},{tlwh[1]:.2f},{tlwh[2]:.2f},{tlwh[3]:.2f},{t.score:.2f},-1,-1,-1\n"
                    )

            timer_track.toc()
            
            timer_speed.tic()
            if (get_speed):
                for t in online_targets:
                    # Update tracklet latest 2 locations
                    mapPoints = view_transformer.transform_points(points = t.to_bc()[0:2])#.astype(int)
                    if t.location is not None: 
                        print(f'Track id {t.track_id} en if {mapPoints}')
                        t.prev_location = t.location
                        t.location = mapPoints
                        # Calculate speed
                        distance = np.square(np.sum((np.power(abs(t.location - t.prev_location),2))))
                        time = 1 / (FPS if "FPS" in vars() else DEFAULT_FPS)
                        speed = (distance / time) * 3.6
                        t.speeds = np.append(t.speeds, speed)
                        online_speeds.append(f"#{t.track_id} {t.speeds[-1].astype(int)} km/h /n") # 
                        # print(online_speeds)
                    else:
                        print(f'Track id {t.track_id} en else {mapPoints}')
                        t.location = mapPoints
            timer_speed.toc()
                    # online_speeds.append()
            
            
            # Add alert to list
            timer_alerts.tic()
            if (alerts and frame_idx % 100):    
                alert_category , severity  = 'hazardOnRoad', 'critical'
                description =  '"Vehicle between stop and railway with red light"'
                alertFlag = True
                if  online_targets != [] :
                    alertInfo.append(
                        f"{frameId},{ts},{alert_category}, {severity} {description},{CAM_ID},{online_targets[0].track_id},{online_targets[0].location[0][0]:.6f},{online_targets[0].location[0][1]:.6f}\n"
                                    )
            timer_alerts.toc()

            # Save frame into video with box plotting
            timer_video.tic()
            if save_plot:
                ret, frame = cap.read()
                if not ret:
                    break
                online_im = plot_tracking(
                    frame, online_tlwhs, online_ids, frame_id=frameId, fps=1. / timer_track.average_time
                )
                # Save video
                vid_writer.write(online_im)

            # View frame with plot
            if view_plot:
                if not save_plot:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    online_im = plot_tracking(
                        frame, online_tlwhs, online_ids, frame_id=frameId, fps=1. / timer_track.average_time
                    )
                # Show video
                cv2.imshow("Tracking", online_im)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                
                
            timer_video.toc()


            if frame_idx % 90 == 0:
                print(f'Processing frame {frame_idx}')
                print(f'\t- Avg. Reception Time: {timer_reception.average_time}')
                print(f'\t- Avg. Waiting Time: {timer_wait_recv.average_time}')                
                print(f'\t- Avg. Tracking Time: {timer_track.average_time}')
                print(f'\t- Avg. Speed Time: {timer_speed.average_time}')
                print(f'\t- Avg. Video Time: {timer_video.average_time}')
                print(f'\t- Avg. Alerts Time: {timer_alerts.average_time}')
                timer_track.clear()
                timer_speed.clear()
                timer_video.clear()
                timer_reception.clear()
                timer_wait_recv.clear()
                timer_alerts.clear()

            if frameId != frame_idx and frameId - frame_idx != skiped_frames:
                skiped_frames = frameId - frame_idx
                print(f"\tSmartCity skipped one frame!! Total skipped frames: {frameId - frame_idx}")
                # break

            hex_data = ""
        # WHILE ENDED

        print(f"\n\n\tSmartCity skipped a total of {frameId - frame_idx} frames.")

        if save_results:
            res_file = join(exp_dir, LOG_OUT_NAME)
            print(f"Savedir: {res_file}")
            with open(res_file, 'w') as f:
                f.writelines(results)
            print(f"save results to {res_file}")
            
        if alerts:
            alarm_file = join(exp_dir, ALERTS_OUT_NAME)
            print(f"Savedir: {alarm_file}")
            with open(alarm_file, 'w') as f:
                f.writelines(alertInfo)
            print(f"save results to {alarm_file}")

        if save_plot: 
            print(f"Releasing video...")
            cap.release()
            vid_writer.release()
            cv2.destroyAllWindows()

        udpSock.close()
        print(f"[main.py] Done receiving from {edge_device}.\n")



def main_udp(opt):
    global FINISH_PROGRAM
    
    # Prepare experiment folder
    if not os.path.exists(opt.exp_dir):
        os.makedirs(opt.exp_dir)
    exp_vid_dir = join(opt.exp_dir, opt.expn)
    if os.path.exists(exp_vid_dir):
        shutil.rmtree(exp_vid_dir)
    os.makedirs(exp_vid_dir)
    opt.exp_dir = exp_vid_dir


    
    
    # Each endpoint => "host:port"
    # We'll pass them to run(...) as zmq_endpoints
    run_udp(edge_ips=opt.edge_ips,
        track_thresh=opt.track_thresh,
        track_buffer=opt.track_buffer,
        match_thresh=opt.match_thresh,
        min_box_area=opt.min_box_area,
        reid_weights=opt.reid_weights,
        tracking_method=opt.tracking_method,
        tracking_config=opt.tracking_config,
        exp_dir=opt.exp_dir,
        expn=opt.expn,
        save_results=opt.save_results,
        save_plot=opt.save_plot,
        view_plot=opt.view_plot,
        get_speed=opt.get_speed,
        alerts=opt.alerts
        )
