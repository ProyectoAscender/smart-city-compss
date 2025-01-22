import os
import sys
from pathlib import Path
# Get project folder root when executing from shell like this:
# from src import utils
# FILE = Path(utils.__file__).resolve()
# ROOT = FILE.parents[0] 
# Get project folder root when executing from python command like this:
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
srcROOT = ROOT + '/src/' 
sys.path.append(ROOT)


if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # add ROOT to PATH

if str(ROOT + '/trackers' + '/bytetrack') not in sys.path:
    sys.path.append(str(ROOT + '/trackers' + '/bytetrack'))  # add strong_sort ROOT to PATH

relROOT = Path(os.path.relpath(srcROOT, ROOT))  # relative
WEIGHTS = relROOT / '/weights'

nl = '\n'

import argparse	
from collections import defaultdict, deque

import time as tm

import zmq
import uuid
from datetime import datetime
import ntpath 
from glob import glob
from os.path import join
# from tqdm import tqdm
#############
global seen, windows, dt
import os, shutil
###############

import numpy as np
import cv2

from trackers.multi_tracker_zoo import create_tracker
from src import comm
from src import utils
from src.visualize import plot_tracking
from src.timer import Timer
from src.viewTransform import ViewTransformer

from src import comm_zmq

# EDGE_INFO DEFAULT
CAM_ID = '1112'
NCAMS = 1
NUM_ITERS = 10
CAM_HEIGHT = 720
CAM_WIDTH = 1280
VIDEO_OUT_NAME = "video_tracking_output.mp4"
LOG_OUT_NAME = "out.txt"
DEFAULT_FPS = 30

# img_info["raw_img"] = img
# img, ratio = preproc(img, self.test_size, self.rgb_means, self.std)
# img_info["ratio"] = ratio

def parse_opt():
    parser = argparse.ArgumentParser("ByteTrack argument parser!")
    # Parse arguments to accept variable number of "IPs:Ports"
    parser.add_argument("--save_results", type=bool, default=True, help="save tracking results into txt")
    parser.add_argument('--save_plot', type=bool, default=False, help="plot tracking")
    parser.add_argument('--speed', type=bool, default=True, help="Measure speed")
    parser.add_argument("--expn", "--experiment-name", type=str, default= datetime.now().strftime("%m%d%Y_%H%M%S"))
    parser.add_argument('--exp_dir', default=relROOT / '..' / 'runs' / 'exp', help='experiment directory')
    # parser.add_argument("--mqtt_wait", nargs='?', const=True, type=str2bool, default=False)  # True as default
    # parser.add_argument("--with_semantics", nargs='?', const=True, type=str2bool, default=False)  # True as default
    # tracking args
    parser.add_argument('--reid-weights', type=Path, default=WEIGHTS / 'osnet_x0_25_msmt17.pt')
    parser.add_argument('--tracking_method', type=str, default='bytetrack', help='only bytetrack by now')
    parser.add_argument('--tracking_config', type=Path, default=None)
    parser.add_argument("--track_thresh", type=float, default=0.6, help="tracking confidence threshold")
    parser.add_argument("--track_buffer", type=int, default=30, help="the frames for keep lost tracks")
    parser.add_argument("--match_thresh", type=float, default=0.9, help="matching threshold for tracking")
    parser.add_argument("--min_box_area", type=float, default=100, help='filter out tiny boxes')
    parser.add_argument("edge_ips", type=str,default=['1111'], nargs='?')
    opt = parser.parse_args()
    opt.tracking_config = relROOT / '../trackers' / opt.tracking_method / 'configs' / (opt.tracking_method + '.yaml')
    print(f'Arguments are: \n {opt}')
    return opt

# # Creating struct data to feed tracker
# class frameInfo:
#     def __init__(self, confs, xyxys, cls):
#         self.conf = confs
#         self.xyxy = xyxys
#         self.cls = cls

def run(zmq_endpoints=None,
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
    
    # 1) For each endpoint, do handshake, connect SUB
    for endpoint in zmq_endpoints:
        print(f"[main.py] Handling endpoint: {endpoint}")
        # parse "host:port"
        host, port_str = endpoint.split(":")
        port = int(port_str)

        # Step 1: handshake to get camera info
        info = comm_zmq.handshake_and_get_info(f"{host}:{port}")
        print(f"[main.py] Camera info: {info}")

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

        # Step 2: connect SUB on port+1
        pub_port = port + 1
        sub_addr = f"tcp://{host}:{pub_port}"
        print(f"[main.py] Subscribing to bounding boxes at {sub_addr}")

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

    print("[main.py] Ready to receive bounding boxes...")



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
                print("[main.py] No data in 2s, continuing...")
                continue
            else:
                print("[main.py] Waited for too long, dropping connection...")
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

                
                frameData = list(comm_zmq.decode_hex_bboxes(hex_data))  # implement in comm_zmq.py
                
                # Detections to numpy array [x,y,w,h,score,classId]
                det = np.asarray([box[-6:-1] for box in frameData])  # by now,without classId
                
                frameId = frameData[0][2]
                ts = frameData[0][3]

                
                # print(f"Processing Frame: {frameId} with timestamp: {ts}")
                
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








def main(opt):
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
    run(zmq_endpoints=endpoints,
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


if __name__ == "__main__":
    opt = parse_opt()
    main(opt)

