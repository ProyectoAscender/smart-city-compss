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


from trackers.multi_tracker_zoo import create_tracker
import argparse	

import time
import zmq
import uuid

from datetime import datetime

import ntpath 

from glob import glob
from os.path import join
# from tqdm import tqdm
#############
import time
global seen, windows, dt

import os, shutil
###############

import numpy as np
import cv2

from src import comm
from src import utils
from src.visualize import plot_tracking
from src.timer import Timer

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
    parser.add_argument('--save_plot', type=bool, default=True, help="plot tracking")
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

def run(source=None,
        model=None,
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
        save_plot = True,
        edge_ips = [] # <- sobra?
):


    # source = str(source)
    is_file = Path(opt.source).suffix[1:] in (['mp4', 'avi'])

    start_time = time.time()
    initTime = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

    # Create as many track instances as there are video sources
    # TO - DO : si cada run se paraleliza para cada vídeo, aqui no paralelizamos nada, pero podriamos tener mas de un tracker para solo una camara -> approach paddle padlle
    tracker_list = []
    print(f'- Creating tracker for {opt.source} - ')
    tracker = create_tracker(tracking_method, tracking_config, reid_weights)
    tracker_list.append(tracker, )
    
    ## BINDING UDP:
    # Let camera edge start
    print('UDP handshaking')
    comm.camera_edge_handshake(opt.source)

    ## SET SOCKET, GET EDGE INFO
    print('UDP Setting socket')
    serverSocket, edgeInfo = comm.set_socket(opt.source)


    ## EDGE INFO:
    edgeInfo = (str(edgeInfo)).split('|')
    CAM_ID, GSTREAMER, NUM_ITERS, CAM_HEIGHT, CAM_WIDTH, DATA_PATH = edgeInfo[1:]
    GSTREAMER = int(GSTREAMER)
    NUM_ITERS = int(NUM_ITERS)
    CAM_HEIGHT = 720
    CAM_WIDTH = 1280
    if (GSTREAMER == 0): print(DATA_PATH) 
    # Initializing list to store tracker data
    results = []
    # alternative: results = [None] * NUM_ITERS
    #[ 0: Height, 1: width]
    img_info = [CAM_HEIGHT, CAM_WIDTH]
    # Original version of bytetrack re-scales boxes to original img_info values:
    #   test_size = (args.tsize, args.tsize) 
    #   tsize are values from original yolo model resolution
    test_size = (img_info[0], img_info[1]) # We don't want to re-scale yet

    if save_plot:
        a = (DATA_PATH.replace("'", "") if GSTREAMER == 0 else CAM_ID)
        print(f'{a}')
        cap = cv2.VideoCapture(a) # TO - DO: else con gstreamer
        vid_fps = cap.get(cv2.CAP_PROP_FPS)
        FPS = vid_fps if int(vid_fps) > 0 else DEFAULT_FPS
        # Prepare video output
        out_path = join(exp_dir, VIDEO_OUT_NAME)
        video_format = 'MP4V'
        fourcc = cv2.VideoWriter_fourcc(*video_format)
        print(f'Saving video. Path: {out_path} | fps: {FPS} | resolution: {CAM_WIDTH}x{CAM_HEIGHT}')
        vid_writer = cv2.VideoWriter(out_path, fourcc, FPS, (CAM_WIDTH, CAM_HEIGHT))


    ## LOOP ITERATING FRAMES:
    frame_idx = 1
    timer = Timer()
    print(f'--------------NUM_ITERS:   {NUM_ITERS}')
    while frame_idx < 2000:

        timer.tic()
        timestamp = frame_idx / tracker_list[0].args.frame_rate
        print(f'Reading data of frame {frame_idx} - timestamp: {timestamp}')

        # Reading udp data
        comm.setAck_socket(serverSocket, opt.source)
        frameData = list(comm.read_udp(serverSocket)) # iterator to npArray
        # [box[-6:] for box in frameData]

        # Detections to numpy array [x,y,w,h,score,classId]
        det = np.asarray([box[-6:-1] for box in frameData])  # by now,without classId

        if det is not None:

            # Update tracker
            online_targets = tracker_list[0].update(det, img_info, test_size)

            # Collect and write results
            online_tlwhs = []
            online_ids = []
            online_scores = []
            for t in online_targets:
                tlwh = t.tlwh
                tid = t.track_id
                if tlwh[2] * tlwh[3] > min_box_area: 
                    online_tlwhs.append(tlwh)
                    online_ids.append(tid)
                    online_scores.append(t.score)
                    results.append(
                        f"{frame_idx},{tid},{tlwh[0]:.2f},{tlwh[1]:.2f},{tlwh[2]:.2f},{tlwh[3]:.2f},{t.score:.2f},-1,-1,-1\n"
                    )

            timer.toc()

            if save_plot:
                ret, frame = cap.read()
                if not ret:
                    break
                online_im = plot_tracking(
                    frame, online_tlwhs, online_ids, frame_id=frame_idx, fps=1. / timer.average_time
                )
                vid_writer.write(online_im)

        else:
            timer.toc()

            if save_plot:
                ret, frame = cap.read()
                online_im = frame
                print('Using original frame...')

        print(f'Ending iter of frame {frame_idx} - Timestamp {timestamp}')
        if frame_idx % 10 == 0:
            print(f'Processing frame {frame_idx} - Avg. Time: {timer.average_time}')

        frame_idx += 1

    if save_results:
        res_file = join(exp_dir, LOG_OUT_NAME)
        with open(res_file, 'w') as f:
            f.writelines(results)
        print(f"save results to {res_file}")

    if save_plot: 
        print(f"Releasing video...")
        vid_writer.release()




    print(results)

  
    
        # # LOOP NUMBER CAMERA INPUTS
        # for cam_idx, socket_ip in enumerate(socket_ips):
        #     print('Receiving boxes ')
        #     cam_ids[cam_idx], timestamps[cam_idx], list_boxes, reception_dummies[cam_idx], det[cam_idx], init_point, frames[cam_idx] = \
        #                         receive_boxes(socket_ip, reception_dummies[cam_idx])
            
            
            
            # trackers_list[index], cur_index[index], info_for_deduplicator[index] = execute_tracking(list_boxes,
            #                                                                                         trackers_list[index],
            #                                                                                         cur_index[index],
            #                                                                                         init_point)



    # end_time = time.time()
    # print("Exec Inner Time: " + str(end_time - start_time))
    # print("Exec Inner Time per Iteration: " + str((end_time - start_time) / NUM_ITERS))
    # print("Exiting Application...")
    # #finish()




# #------ PADDLE PADDLE APPROACH
#       for cls_id in range(self.num_classes):
#             cls_idx = (pred_dets[:, 0:1] == cls_id).squeeze(-1)
#             pred_dets_dict[cls_id] = pred_dets[cls_idx]
#             if pred_embs is not None:
#                 pred_embs_dict[cls_id] = pred_embs[cls_idx]
#             else:
#                 pred_embs_dict[cls_id] = None

#         for cls_id in range(self.num_classes):
#             """ Step 1: Get detections by class"""
#             pred_dets_cls = pred_dets_dict[cls_id]
#             pred_embs_cls = pred_embs_dict[cls_id]
#             remain_inds = (pred_dets_cls[:, 1:2] > self.conf_thres).squeeze(-1)
#             if remain_inds.sum() > 0:
#                 pred_dets_cls = pred_dets_cls[remain_inds]
#                 if pred_embs_cls is None:
#                     # in original ByteTrack
#                     detections = [
#                         STrack(
#                             STrack.tlbr_to_tlwh(tlbrs[2:6]),
#                             tlbrs[1],
#                             cls_id,
#                             30,
#                             temp_feat=None) for tlbrs in pred_dets_cls
#                     ] 
# #---------




def main(opt):

    # creating experiment folder
    if not os.path.exists(opt.exp_dir):
        os.makedirs(opt.exp_dir)
    exp_vid_dir = join(opt.exp_dir, opt.expn)
    if os.path.exists(exp_vid_dir):
        shutil.rmtree(exp_vid_dir)
    os.makedirs(exp_vid_dir)
    opt.exp_dir = exp_vid_dir

    # # TO-DO: parallelize Loop for every camera at list edge_ips
    print(f'------------------- {list(opt.edge_ips.split(" "))}')
    
    for edge_ip in list(opt.edge_ips.split(" ")):

        opt.source = edge_ip
        run(**vars(opt))

    # # Print results
    # t = tuple(x.t / seen * 1E3 for x in dt)  # speeds per image
    # LOGGER.info(f'Speed: %.1fms pre-process, %.1fms inference, %.1fms NMS, %.1fms {opt.tracking_method} update per image at shape {(1, 3, *opt.imgsz)}' % t)


if __name__ == "__main__":
    opt = parse_opt()
    main(opt)
    
    
    # args = make_parser().parse_args()
    # exp = get_exp(args.exp_file, args.name)
    # exp.merge(args.opts)
    
    # main()

