import argparse
from datetime import datetime
from pathlib import Path
import os
import sys
import shutil


OPENCV_VIDEOIO_DEBUG=1


# IDK what this does
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
srcROOT = ROOT + '/src/' 
sys.path.append(ROOT)
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # add ROOT to PATH

if str(ROOT + '/trackers' + '/bytetrack') not in sys.path:
    sys.path.append(str(ROOT + '/trackers' + '/bytetrack'))  # add strong_sort ROOT to PATH
relROOT = Path(os.path.relpath(srcROOT, ROOT))  # relative
WEIGHTS = relROOT / '/weights'



# from udp_handler import run_udp, main_udp
from udp_handler import main_udp
from zmq_handler import main_zmq



def parse_opt():
    parser = argparse.ArgumentParser("ByteTrack argument parser!")
    parser.add_argument("--mode", type=str, choices=["udp", "csv","zmq"], required=True, help="Select communication mode")
    parser.add_argument("--only_results", type=bool, default=False, help="save tracking results into txt")
    parser.add_argument("--save_results", type=bool, default=True, help="save tracking results into txt")
    parser.add_argument('--save_plot', type=bool, default=False, help="plot tracking")
    parser.add_argument('--view_plot', type=bool, default=False, help="plot view trough x11")
    parser.add_argument('--alerts', type=bool, default=False, help="Generate alerts with MQTT")
    parser.add_argument('--semantics', type=bool, default=False, help="Analytics with semantics")
    parser.add_argument("--print_time", type=bool, default=True, help="Print time statistics in terminal")
    parser.add_argument('--get_speed', type=bool, default=False, help="Measure speed")
    parser.add_argument("--expn", "--experiment-name", type=str, default= datetime.now().strftime("%Y%m%d"))
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
    parser.add_argument("--edge_ips", nargs='+', type=str,default=['1111'],help='array with ip:port of camera edges ')
    opt = parser.parse_args()
    opt.tracking_config = relROOT / '../trackers' / opt.tracking_method / 'configs' / (opt.tracking_method + '.yaml')
    print(f'Arguments are: \n {opt}')
    return opt






if __name__ == "__main__":
    opt = parse_opt()

    if opt.mode == "udp":
        print('Entering into mode udp..')
        main_udp(opt)

    elif opt.mode == "zmq":
        main_zmq(opt)

