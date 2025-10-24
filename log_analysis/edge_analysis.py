from collections import defaultdict
import re
import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.dates as mdates

from datetime import datetime

TZ = "Europe/Madrid" 


# Hardcoded input and output settings
INPUT_FILE = "data_logs/edge_2025-08-28_080504.log"


def get_output_dir():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(script_dir, "plots_camera_edge")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir

def timestamp_to_datetime(timestamp):
    try:
        # Adjust division factor based on your timestamp format
        dt = datetime.fromtimestamp(timestamp / 1000000)  # Microseconds from C++ code
        return dt
    except (ValueError, OSError, OverflowError):
        return None
    
    
def parse_file(filepath):
    """
    Parse lines from the file. We keep:
      - VC Frame:  6; CE frame: 6 with timestamp: 1115039 | printed at: 1755862651733259
        
        
    Skips any line that contains invalid UTF-8 characters or unrealistic values.
    """
    counter_data = []
    counter_line = "VC Frame:  "
    # Match: VC Frame: <num>; CE frame: <num> with timestamp: <num> | printed at: <num>
    counter_pattern = re.compile(
        r"""(?mx)                                   # m: multiline, x: verbose
        ^\s*VC\s*Frame\s*:\s*(?P<vc_frame>-?\d+)    # VC Frame
        \s*;\s*CE\s*frame\s*:\s*(?P<ce_frame>-?\d+) # CE frame
        \s*with\s*timestamp\s*:\s*(?P<ts_frame>-?\d+) # first timestamp
        \s*\|\s*printed\s*at\s*:\s*(?P<printed_at>-?\d+) # printed-at timestamp
        \s*$"""
    )
    
    debugggg = False
    aaaa = 0
    with open(filepath, 'rb') as f:  # read as bytes
        for line_num, raw_line in enumerate(f, 1):
            try:
                line = raw_line.decode('utf-8')  # try to decode this line
            except UnicodeDecodeError:
                print(f"Line {line_num} was corrupter. Skipping....")
                continue  # skip entire line if it can't be decoded

            
            if line.startswith(counter_line):
                m = counter_pattern.match(line)
                if m:
                    try:
                        
                        vc_frame = np.int64(m.group('vc_frame'))
                        ce_frame = np.int64(m.group('ce_frame'))
                        ts_frame = np.int64(m.group('ts_frame'))
                        printed_at = np.int64(m.group('printed_at'))

                        # With this:
                        dt = timestamp_to_datetime(ts_frame)
                        
                        
                        # Only because of gstreamer break_
                        if ce_frame >= 2398081:
                            break   
                        
                        
                               
                        # Build wall-clock datetime from printed_at (µs since epoch)
                        dt = pd.to_datetime(printed_at, unit='us', utc=True)
                        if TZ:
                            dt = dt.tz_convert(TZ)

                        counter_data.append({
                            'VideoCapture_frame': vc_frame,
                            'CameraEdge_frame' : ce_frame,
                            'device_ts'        : ts_frame,     # renamed for clarity
                            'printed_at_us'    : printed_at,   # wall-clock in microseconds
                            'datetime'         : dt            # wall-clock datetime (x-axis)
                        })
                    except ValueError:
                        continue
                    
            # if line.startswith("VC Frame:  21605; CE frame: 21605 with timestamp:"):
            #     debugggg = True
                
            # if debugggg:
            #     print(line)
            #     aaaa += 1
                
            # if aaaa == 500:
            #     return pd.DataFrame(counter_data)
                    
            else:
                # print(line)
                continue
    return pd.DataFrame(counter_data)



def plot_timestamps(df, output_dir):
    plt.figure(figsize=(12, 6))
    x = df['datetime']                       # from printed_at
    y = df['device_ts']                      # device counter / acquisition timestamp
    plt.scatter(x, y, label='device_ts vs wall-clock', alpha=0.6, s=10)

    ax = plt.gca()
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.AutoDateFormatter(ax.xaxis.get_major_locator()))
    plt.xticks(rotation=45)

    plt.xlabel('Wall-clock time')
    plt.ylabel('Device timestamp')
    plt.title('Device timestamp over wall-clock time')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'timestamps_scatter.png'))
    plt.close()

    
def plot_fps(df, output_dir):
    plt.figure(figsize=(12, 6))

    # diffs from wall-clock µs → seconds
    dt_us = df['printed_at_us'].diff().dropna()
    dt_s  = dt_us / 1_000_000.0

    # robust filtering (loose outlier clip)
    mean = dt_s.mean()
    std  = dt_s.std()
    laxi = 10
    filtered = dt_s[(dt_s >= mean - laxi*std) & (dt_s <= mean + laxi*std)]

    approx_fps = 1.0 / filtered.mean()
    print(f"\n\nApprox FPS (wall-clock): {approx_fps:.3f} fps\n\n")

    x = np.arange(len(filtered))
    plt.scatter(x, filtered, label='Inter-frame interval (s)', alpha=0.6, s=10)
    plt.xlabel('Sample Index')
    plt.ylabel('Seconds')
    plt.ticklabel_format(useOffset=False, style='plain')
    plt.title('Inter-frame time from wall-clock (printed_at)')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'timestamp_differences.png'))
    plt.close()

    
    

    
    
    
    
def plot_counters(df, output_dir):
    plt.figure(figsize=(12, 6))
    x = df['datetime']
    plt.scatter(x, df['VideoCapture_frame'], label='Video Capture Frame', alpha=0.6, s=10)
    plt.scatter(x, df['CameraEdge_frame'],  label='Camera Edge Frame',  alpha=0.6, s=10)

    ax = plt.gca()
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.AutoDateFormatter(ax.xaxis.get_major_locator()))
    plt.xticks(rotation=45)

    plt.xlabel('Wall-clock time')
    plt.ylabel('Frame ID')
    plt.title('Frame counters over wall-clock time')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'counters_scatter.png'))
    plt.close()

        
    
    
    
    stats = sorted(list(df.columns.values))
    num_stats = len(stats)
    
    # create one figure with N rows, 1 column
    fig, axes = plt.subplots(num_stats, 1, figsize=(12, 4*num_stats), sharex=True)
    
    # if only one stat, axes is not a list
    if num_stats == 1:
        axes = [axes]
        
    x = df['datetime'].values if 'datetime' in df.columns else df['timestamp'].to_numpy(dtype=int)    
    
    
    for ax, stat in zip(axes, stats):        
        
        y = df[stat].to_numpy(dtype=float)
        

        ax.scatter(x, y, label=stat, alpha=0.6, s=10)


        ax.set_ylabel(stat)
        ax.grid(True)
        ax.legend(loc="best")
        
        
    if 'datetime' in df.columns:
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        plt.gca().xaxis.set_major_locator(mdates.SecondLocator(interval=3600))
        plt.xticks(rotation=45)
    else:
        plt.ticklabel_format(useOffset=False, style='plain')
        
    axes[-1].set_xlabel("time")
    fig.suptitle("Scatter plots of Frame Counter on VideoCapture vs CameraEdge vs Timestamps", y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    
    if 'datetime' in df.columns:
        plt.setp(axes[-1].xaxis.get_majorticklabels(), rotation=45) 

    outfile = os.path.join(output_dir, "stats_scatter.png")
    
    fig.savefig(outfile)
    plt.close(fig)


        



def main():
    output_dir = get_output_dir()
    counters_df = parse_file(INPUT_FILE)
    

    # Counter overview
    print("\n\n")
    print(counters_df.head())  # preview
    print(counters_df.tail())
    
    print("\n\n")
    with pd.option_context('display.float_format', '{:.2f}'.format):
        print(counters_df.describe())
    
    
    plot_timestamps(counters_df, output_dir)

    
    plot_counters(counters_df, output_dir)

    
    plot_fps(counters_df, output_dir)
    



if __name__ == '__main__':
    main()
