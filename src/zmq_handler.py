import cv2
import zmq
import os
from os.path import join
from src.timer import Timer
from src.visualize import plot_tracking
from trackers.multi_tracker_zoo import create_tracker
from src.viewTransform import ViewTransformer
import numpy as np
import shutil
import time as tm

import comm_zmq as comm_zmq



# Hardcoded values
DEFAULT_FPS = 30
VIDEO_OUT_NAME = "video_tracking_output.mp4"
LOG_OUT_NAME = "out.txt"



def run_zmq(
        zmq_endpoints=None,
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
        speed = True,
        edge_ips = [] # <- sobra?
):

    print("\n\n\n[zmq_handler] Starting ZMQ-based tracking...")
    
    # CHECK HOW TO HANDLE THIS FOR MANY EDGE DEVICES.
    # Create as many track instances as there are video sources
    # TO - DO : si cada run se paraleliza para cada vídeo, aqui no paralelizamos nada, pero podriamos tener mas de un tracker para solo una camara -> approach paddle padlle
    tracker_list = []
    # print(f'- Creating tracker for {opt.source} - ')
    tracker = create_tracker(tracking_method, tracking_config, reid_weights)
    tracker_list.append(tracker, )
    
    
    
    # Prepare storage for bounding-box results
    results = []

    # We'll store references to ZeroMQ SUB sockets here if multiple cameras
    sub_sockets = []
    sub_contexts = []
    
    # For each endpoint, do handshake, connect SUB
    for endpoint in zmq_endpoints:
        print(f"[zmq_handler] Handling endpoint: {endpoint}")
        # parse "host:port"
        host, port_str = endpoint.split(":")
        port = int(port_str)

        # handshake to get camera info
        info = comm_zmq.handshake_and_get_info(f"{host}:{port}")
        print(f"[zmq_handler] Camera info: {info}")

        # GET EDGE INFO:
        CAM_ID = int(info["cam_id"])
        GSTREAMER = int(info["gstreamer"])
        NUM_ITERS = int(info["frames_to_process"])
        CAM_HEIGHT = int(info["cam_height"])
        CAM_WIDTH  = int(info["cam_width"])
        DATA_PATH = info["data_path"].replace("'", "")
        DATA_PATH = os.path.join(*(DATA_PATH.split(os.path.sep)[3:-1]))
        videoPath = os.path.join( 'data', DATA_PATH, "videos/20230721_092248_cam01h264.mp4")
        CITY = DATA_PATH.split(os.path.sep)[0]
        AREA = DATA_PATH.split(os.path.sep)[1]
        DATA_PATH = os.path.join( 'data', DATA_PATH)

        # connect SUB on port+1
        pub_port = port + 1
        sub_addr = f"tcp://{host}:{pub_port}"
        print(f"[zmq_handler] Subscribing to bounding boxes at {sub_addr}")

        ctx = zmq.Context()
        sub_socket = ctx.socket(zmq.SUB)
        sub_socket.connect(sub_addr)
        sub_socket.setsockopt_string(zmq.SUBSCRIBE, info["cam_id"])  # filter by camera ID
        # If you want to subscribe to all cameras, do SUBSCRIBE, ""

        sub_sockets.append(sub_socket)
        sub_contexts.append(ctx)
        
    
    # Load Pmat (this works assuming 1 edge camera)
    # PMAT_PATH = utils.find_files_by_strings(os.path.join(DATA_PATH, 'pmat'), CAM_ID, "ACTIVE")[0]
        
    # Load pmat
    # view_transformer = ViewTransformer(pmatPath = PMAT_PATH)
    # os.system('cp ' + PMAT_PATH + ' ./pmat.txt')
    view_transformer = ViewTransformer(pmatPath = 'pmat.txt')
    
    img_info = [CAM_HEIGHT, CAM_WIDTH]
    test_size = (img_info[0], img_info[1]) # We don't want to re-scale yet

    
    
    
    
    
    # Optinal saving video stuff
    if save_plot:
        # Get path to get frames, removing edge source video b2drop root 
        print(f'{videoPath}')
        cap = cv2.VideoCapture('./20230721_092248_cam01h264.mp4') # TO - DO: else con gstreamer
        vid_fps = cap.get(cv2.CAP_PROP_FPS)
        FPS = vid_fps if int(vid_fps) > 0 else DEFAULT_FPS
        # Prepare video output
        out_path = join(exp_dir, VIDEO_OUT_NAME)
        video_format = 'MP4V'
        fourcc = cv2.VideoWriter_fourcc(*video_format)
        print(f'Saving video. Path: {out_path} | fps: {FPS} | resolution: {CAM_WIDTH}x{CAM_HEIGHT}')
        vid_writer = cv2.VideoWriter(out_path, fourcc, FPS, (CAM_WIDTH, CAM_HEIGHT))


    # 5) Start receiving bounding boxes from each SUB socket
    # We'll do a round-robin poll or a simple approach reading from any socket
    poller = zmq.Poller()
    for s in sub_sockets:
        poller.register(s, zmq.POLLIN)

    print("[zmq_handler] Ready to receive bounding boxes...")



    ## LOOP ITERATING FRAMES:
    frame_idx = 0
    timer_track = Timer()
    first_no_socks = 0
    max_await = 5

    
    # We loop indefinitely or until some condition
    while frame_idx < NUM_ITERS:
        frame_idx += 1
        
        # poll all sub sockets
        socks = dict(poller.poll(timeout=2000))  # 2s poll
        if not socks:
            if(first_no_socks ==  0):
                first_no_socks = frame_idx
            if frame_idx - first_no_socks <= max_await:
                print("[zmq_handler] No data in 2s, continuing...")
                continue
            else:
                print("[zmq_handler] Waited for too long, dropping connection...")
                break

        for i, sub_socket in enumerate(sub_sockets):
            if sub_socket in socks and socks[sub_socket] == zmq.POLLIN:
                # 2-part message: [topic=camera_id, data=hex_string]
                parts = sub_socket.recv_multipart()
                if len(parts) != 2:
                    continue

                camera_id = parts[0].decode('utf-8', errors='ignore')
                hex_data  = parts[1]

                
                timer_track.tic()

                
                frameData = list(comm_zmq.decode_hex_bboxes(hex_data))
                
                # Detections to numpy array [x,y,w,h,score,classId]
                det = np.asarray([box[-6:-1] for box in frameData])  # by now,without classId
                
                frameId = frameData[0][2]
                ts = frameData[0][3]

                
                print(f"Processing Frame: {frameId} with timestamp: {ts}")
                
                if frameId != frame_idx:
                    print(f"{frameId - frame_idx} frames are missing!! Camera-edge is not waiting for smartcity!")
                    # break


                ## TRACKING
        
                if det is not None:

                    # Update tracker
                    online_targets = tracker_list[0].update(det, img_info, test_size)

                    # Collect and write results
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

                    if (speed):
                        for t in online_targets:
                            # Update tracklet latest 2 locations
                            mapPoints = view_transformer.transform_points(points = t.to_bc()[0:2])#.astype(int)
                            if t.location is not None: 
                                t.prev_location = t.location
                                t.location = mapPoints
                                # Calculate speed
                                distance = np.square(np.sum((np.power(abs(t.location - t.prev_location),2))))
                                time = 1 / (FPS if "FPS" in vars() else DEFAULT_FPS)
                                speed = (distance / time) * 3.6
                                t.speeds = np.append(t.speeds, speed)
                                online_speeds.append(f"#{t.track_id} {t.speeds[-1].astype(int)} km/h /n") # 
                                print(online_speeds)
                            else:
                                t.location = mapPoints




                            # online_speeds.append()

                
                
                if save_plot:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    online_im = plot_tracking(
                        frame, online_tlwhs, online_ids, frame_id=frameId, fps=1. / timer_track.average_time
                    )
                    vid_writer.write(online_im)

            else:
                timer_track.toc()
            
            
                if save_plot:
                    ret, frame = cap.read()
                    online_im = frame
                    print('Using original frame...')

            
            if frame_idx % 10 == 0:
                print(f'Processing frame {frame_idx} - Avg. Time: {timer_track.average_time}')
                timer_track.clear()



    if save_results:
        res_file = join(exp_dir, LOG_OUT_NAME)
        print(f"Savedir: {res_file}")
        with open(res_file, 'w') as f:
            f.writelines(results)
        print(f"save results to {res_file}")

    if save_plot: 
        print(f"Releasing video...")
        vid_writer.release()








def main_zmq(opt):
    # Prepare experiment folder
    if not os.path.exists(opt.exp_dir):
        os.makedirs(opt.exp_dir)
    exp_vid_dir = join(opt.exp_dir, opt.expn)
    if os.path.exists(exp_vid_dir):
        shutil.rmtree(exp_vid_dir)
    os.makedirs(exp_vid_dir)
    opt.exp_dir = exp_vid_dir

    # Convert old "edge_ips" argument into a list of ZeroMQ endpoints

    if isinstance(opt.edge_ips, list):
        endpoints = opt.edge_ips
    else:
        endpoints = str(opt.edge_ips).split(" ")

    print(endpoints)
    
    
    # Each endpoint => "host:port"
    # We'll pass them to run(...) as zmq_endpoints
    run_zmq(zmq_endpoints=endpoints,
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
        speed=opt.speed)
