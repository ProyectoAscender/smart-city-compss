from collections import defaultdict
import re
import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

from datetime import datetime

# from analysisss import integrate_analysis



# Hardcoded input and output settings
# INPUT_FILE = "data_logs/smartcity_2025-08-18_151705.log"
INPUT_FILE = "data_logs/smartcity_2025-08-28_080443.log"


def get_output_dir():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(script_dir, "plots_smartcity")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir

def parse_file(filepath):
    """
    Parse lines from the file. We keep:
      - lines like "0001 - Acabando 185 - 449 - 1755862631.3679588" 
      to track difference between processed and recieved counter
      
      - lines like:
            0001 - Info every 30 frames - frameidx: 180
            0001 - Avg. Track Time: 0.010753059387207031
            0001 - Avg. Reception Time: 0.0010788917541503906
            0001 - Avg. Wait_recv Time: 0.00011448065439860026
            0001 - Avg. Processing Time: 0.015289974212646485
            0001 - Avg. Speed Time: 0.0003709547509451281
            0001 - Avg. Video Time: 0.0678168773651123
            0001 - Avg. Semantics Time: 0.0005739855663970816
            0001 - Avg. Total Time: 0.09528356393178304
        to track the average across 18h run, and see how the behave
        
      - lines like:
             - Saving to src/../runs/exp/20250818/0001/151803/tracklets.txt
            - Saved results to src/../runs/exp/20250818/0001/151803/tracklets.txt
            0001 - Saving every 300 frames
            0001 - New video file started: src/../runs/exp/20250818/0001/151803/video_tracking_output.mp4, vid_writer
            0001 - Finishing iter 300 
        to try to understand why the videos keep moving faster
        
        
    Skips any line that contains invalid UTF-8 characters or unrealistic values.
    """
    counter_data = []
    counter_line = "0001 - Acabando"
    # Match: 0001 - Acabando <num> - <num> (allowing flexible spaces)
    counter_pattern = re.compile(r"^0001\s*-\s*Acabando\s+(-?\d+)\s*-\s*(-?\d+)\s*-\s*(-?\d+(?:\.\d+)?)\s*$")
    
    
    stats_data = defaultdict(list)
    stats_line = "0001 - Avg."
    # Match: 0001 - Acabando <num> - <num> (allowing flexible spaces)
    stats_pattern = re.compile(r"""(?mx)                     # m: multiline (^/$ work per line), x: verbose
                                ^\s*0001\s*-\s*              # start of line, optional indent, '0001 -'
                                (?P<label>[^:]+?)            # capture the label up to the colon (e.g. 'Track Time')
                                \s*:\s*                      # the colon separator
                                (?P<value>                   # capture the number
                                    -?(?:\d+\.\d*|\.\d+|\d+) # int or float
                                    (?:[eE][+-]?\d+)?        # optional scientific exponent
                                )
                                \s*$                         # allow trailing spaces, then end of line
                                """)
    index_stats_data = []
    index_stat_line = "0001 - Info every"
    index_stat_pattern = re.compile(r"^0001\s*-\s*Info\s+every\s+30\s+frames\s*-\s*frameidx\s*:\s*(?P<index>-?\d+)\s*$")

    

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
                        frameIdx = int(m.group(1))
                        frameId  = int(m.group(2))
                        ts_smartcity = np.float64(m.group(3))

                        # Skip corrupted or unrealistic values
                        if frameIdx < 0 or frameId < 0:
                            continue
                        if frameId > 1e7:
                            continue
                        
                        
                        # Only because of gstreamer break_
                        if frameId >= 2398081:
                            break                        
                        
                        counter_data.append({
                            'frameIdx': frameIdx,
                            'frameId': frameId,
                            'ts_smartcity' : ts_smartcity
                        })
                    except ValueError:
                        continue
                
                    
            elif line.startswith(index_stat_line):
                m = index_stat_pattern.match(line)
                if m:
                    try:
                        value = int(m.group('index'))
                        index_stats_data.append(value)
                        
                    except ValueError:
                        continue
            
            
            elif line.startswith(stats_line):
                m = stats_pattern.match(line)
                if m:
                    try:
                        label = m.group('label')
                        value = np.float64(m.group('value'))
                        
                        # keep a dict with all the keys we are taking
                        stats_data[label].append(value)
                    
                    except ValueError:
                        continue
                    
                    
            else:
                # print(line)
                continue
    return pd.DataFrame(counter_data), pd.DataFrame(stats_data), index_stats_data


def plot_counters(df, output_dir):
    """
    Plot line plots of frameIdx and frameId values for each camera (0003 and 0004).
    """
    # Convert epoch seconds -> timezone-aware datetimes (Europe/Madrid)
    ts = pd.to_datetime(df["ts_smartcity"], unit="s", utc=True).dt.tz_convert("Europe/Madrid")

    plt.figure(figsize=(12, 6))
    plt.scatter(ts, df['frameId'], label='frameId (asociado al envio de camera edge)', alpha=0.6, s=10)
    plt.scatter(ts, df['frameIdx'], label='frameIdx(bucle smart city)', alpha=0.6, s=10)
    ax = plt.gca()
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M:%S'))
    plt.xticks(rotation=45)

    plt.xlabel('time (Europe/Madrid)')
    plt.ylabel('frame counters')
    plt.ticklabel_format(axis='y', useOffset=False, style='plain')
    plt.title('Scatter of frameId vs frameIdx over time')
    plt.legend()
    plt.grid(True, linestyle=':')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'counters_scatter.png'), dpi=150)
    plt.close()


def plot_diff_counters(df, output_dir):
    """
    Plot the difference between frameId and frameIdx for each camera.
    """    
    # Convert epoch seconds -> timezone-aware datetimes (Europe/Madrid)
    ts = pd.to_datetime(df["ts_smartcity"], unit="s", utc=True).dt.tz_convert("Europe/Madrid")
    
    diff = df["frameId"] - df["frameIdx"]
    
    plt.figure(figsize=(12, 6))
    plt.scatter(ts, diff, label='frameId - frameIdx', alpha=0.6, s=10)
    ax = plt.gca()
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M:%S'))
    plt.xticks(rotation=45)
    plt.xlabel('time (processed frames in Smartcity)')
    plt.ylabel('frame counter difference')
    plt.title(f'Difference between frameId and frameIdx')
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f'counter_diff.png'))
    # plt.savefig(os.path.join(output_dir, f'counter_diff.svg'), format='svg', dpi=600)
    plt.close()
        
def analyze_diff_growth(df, output_dir):
    """
    Analyze and visualize the growth pattern of (frameId - frameIdx)
    showing the original diff, its slope, acceleration,
    and log-transformed version. X-axis = ts_smartcity as readable time.
    """

    # Time axis: convert epoch seconds -> timezone-aware datetimes (Europe/Madrid)
    ts = pd.to_datetime(df["ts_smartcity"], unit="s", utc=True).dt.tz_convert("Europe/Madrid")

    # Quantity of interest and its derivatives (per-sample derivatives)
    diff = df['frameId'] - df['frameIdx']
    y = diff.to_numpy()
    slope = np.gradient(y)          # rate of change per sample
    acceleration = np.gradient(slope)  # change of slope per sample

    # Log transform (use log1p to safely handle zeros)
    log_diff = np.log1p(y)

    # Plot
    fig, axs = plt.subplots(4, 1, figsize=(14, 12), sharex=True)

    axs[0].scatter(ts, y, s=5, alpha=0.5)
    axs[0].set_ylabel("diff (frameId - frameIdx)")
    axs[0].set_title("Raw diff growth")

    axs[1].plot(ts, slope)
    axs[1].set_ylabel("1st deriv. (per sample)")
    axs[1].set_title("Rate of change (slope)")

    axs[2].plot(ts, acceleration)
    axs[2].set_ylabel("2nd deriv. (per sample)")
    axs[2].set_title("Acceleration")

    axs[3].plot(ts, log_diff)
    axs[3].set_ylabel("log(1 + diff)")
    axs[3].set_title("Log-transformed diff (linear ⇒ exponential growth)")
    axs[3].set_xlabel("time (Europe/Madrid)")

    # Date formatting on shared x-axis
    ax = axs[-1]
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M:%S'))
    plt.xticks(rotation=45)

    for ax in axs:
        ax.grid(True, linestyle=':')

    plt.tight_layout()
    out_file = os.path.join(output_dir, "diff_growth_analysis.png")
    plt.savefig(out_file, dpi=150)
    plt.close()


def plot_stats(df, output_dir, index_stats_data, counters_df, tz="Europe/Madrid"):
    """
    Plot all stats over time using ts_smartcity derived from frameIdx.

    Parameters
    ----------
    df : pd.DataFrame
        Stats table (all numeric columns to be plotted).
    output_dir : str
        Where to save the figure.
    index_stats_data : array-like / pd.Series
        For each row in `df`, the frameIdx at which the stats were captured.
    counters_df : pd.DataFrame
        Must contain at least ['frameIdx', 'ts_smartcity'] to map frameIdx -> epoch seconds.
    tz : str
        Timezone for x-axis display (default: 'Europe/Madrid').
    """

    # ----- Keep alignment masks while filtering outliers -----
    mask = np.ones(len(df), dtype=bool)
    if "Avg. Frame_reception Time" in df.columns:
        mask &= ~(df["Avg. Frame_reception Time"] > 1e-5)
    if "Avg. Udp_wait_reception Time" in df.columns:
        mask &= ~(df["Avg. Udp_wait_reception Time"] > 50)

    df = df.loc[mask].reset_index(drop=True)
    index_stats_data = np.asarray(index_stats_data)[mask]

    # ----- Build mapping frameIdx -> ts_smartcity (epoch seconds) -----
    ts_map = (counters_df
              .drop_duplicates("frameIdx")
              .set_index("frameIdx")["ts_smartcity"])

    ts_epoch = pd.Series(index_stats_data).map(ts_map).to_numpy(dtype=float)

    # Drop rows with missing timestamps
    good = np.isfinite(ts_epoch)
    df = df.iloc[good].reset_index(drop=True)
    ts_epoch = ts_epoch[good]

    # Display x-axis as timezone-aware datetimes
    ts_dt = pd.to_datetime(ts_epoch, unit="s", utc=True).tz_convert(tz)

    # Use seconds since first timestamp for numerically stable fitting
    t0 = float(ts_epoch.min())
    t_sec = ts_epoch - t0  # seconds since start

    # ----- Choose stat columns (numeric only, stable order) -----
    stats = [c for c in df.columns if np.issubdtype(df[c].dtype, np.number)]
    stats.sort()
    num_stats = len(stats)

    fig, axes = plt.subplots(num_stats, 1, figsize=(12, 3.6 * num_stats), sharex=True)
    if num_stats == 1:
        axes = [axes]

    for ax, stat in zip(axes, stats):
        # y-values with NaN/Inf guard
        y = df[stat].to_numpy(dtype=float)
        m = np.isfinite(t_sec) & np.isfinite(y)
        tx = t_sec[m]
        ty = y[m]
        tplot = ts_dt[m]

        # Scatter
        ax.scatter(tplot, ty, label=stat, alpha=0.6, s=10)

        # Linear fit vs time (slope is "units per second")
        if tx.size >= 2:
            slope, intercept = np.polyfit(tx, ty, 1)
            y_fit = slope * tx + intercept
            ax.plot(tplot, y_fit, linewidth=1, color="red",
                    label=f"fit (slope={slope:.10g} per s)")
            ax.text(
                0.02, 0.95, f"fit slope = {slope:.10g} per s",
                transform=ax.transAxes, ha="left", va="top",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.7)
            )

        # Cosmetics
        ax.set_ylabel(stat)
        ax.grid(True)
        ax.legend(loc="best")
        ax.ticklabel_format(useOffset=False, style='plain', axis='y')

    # Shared x-axis: readable datetimes
    axes[-1].set_xlabel(f"time ({tz})")
    axes[-1].xaxis.set_major_locator(mdates.AutoDateLocator())
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M:%S'))
    plt.xticks(rotation=45)

    fig.suptitle("Scatter plots of stats over time", y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.95])

    outfile = os.path.join(output_dir, "stats_scatter.png")
    fig.savefig(outfile, dpi=150)
    plt.close(fig)
    
    
def explain_diff_with_stats(counters_df, stats_df, output_dir, stats_index_col, default_block=30):
    """
    Align stats printed every N processed frames (e.g., 30) to the counter stream and
    test whether timing stats explain the growth of drops (frameId - frameIdx).

    Parameters
    ----------
    counters_df : DataFrame with ['frameIdx','frameId'] in time order.
    stats_df    : DataFrame with timing stats columns (e.g., 'Avg. Track Time', ...).
    output_dir  : directory for outputs.
    stats_index_col : 1D array-like of ints giving the frameIdx where each stats row was printed
                      (e.g., [30, 60, 90, ...]). Must be the same length as stats_df (or longer;
                      it will be trimmed to match).
    default_block : expected spacing between stats frameIdx (usually 30).

    Outputs
    -------
    - plots/diff_predicted_vs_actual.png
    - plots/diff_explain_regression.csv
    Returns
    -------
    pandas.DataFrame with regression summary for all stats.
    """

    frameIdx_c = counters_df['frameIdx'].to_numpy()
    diff = (counters_df['frameId'] - counters_df['frameIdx']).to_numpy()
    n_c = len(counters_df)

    # --- map stats frameIdx to counter indices ---
    s_idx = np.asarray(stats_index_col, dtype=int)
    
    # trim/align if lengths differ
    n_s = min(len(s_idx), len(stats_df))
    if n_s < 3:
        raise ValueError("Need at least 3 stats points for a meaningful regression.")
    s_idx = s_idx[:n_s]
    s_df = stats_df.iloc[:n_s].reset_index(drop=True)

    # determine block size from the data (should be ~30), but dynamic
    est_block = int(round(np.median(np.diff(s_idx))))
    block = est_block if est_block > 0 else int(default_block)

    # map each stats frameIdx to the closest index in counters
    c_pos = np.searchsorted(frameIdx_c, s_idx, side='left')
    c_pos = np.clip(c_pos, 0, n_c - 1)

    # --- compute block-wise increase in cumulative drops at each stats point ---
    # use only those stats points that have a full preceding block
    mask = c_pos >= block
    c_pos = c_pos[mask]
    s_df = s_df.loc[mask].reset_index(drop=True)

    # Δdiff over the block preceding each stats print
    ddiff_block = diff[c_pos] - diff[c_pos - block]
    y = ddiff_block.astype(float)

    # --- regress y on each timing stat & rank ---
    results = []
    for col in s_df.columns:
        # guard: skip non-numeric columns if any
        x = pd.to_numeric(s_df[col], errors='coerce').to_numpy()
        valid = np.isfinite(x) & np.isfinite(y)
        if valid.sum() < 3:
            continue

        X = np.vstack([x[valid], np.ones(valid.sum())]).T
        a, b = np.linalg.lstsq(X, y[valid], rcond=None)[0]  # y_block ≈ a*x + b
        y_hat = a * x + b
        ss_res = float(np.nansum((y - y_hat) ** 2))
        ss_tot = float(np.nansum((y - np.nanmean(y)) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
        corr = float(np.corrcoef(x[valid], y[valid])[0, 1])

        # Interpret in per-frame terms
        slope_per_frame = a / block          # ≈ sending FPS if x ≈ processing time per frame
        intercept_per_frame = b / block      # ≈ -1 expected by the simple rate model

        results.append({
            'stat': col,
            'block_size_used': block,
            'slope_block': a,
            'intercept_block': b,
            'slope_per_frame~FPS': slope_per_frame,
            'intercept_per_frame~should_be_-1': intercept_per_frame,
            'R2': r2,
            'corr': corr
        })

    res_df = pd.DataFrame(results).sort_values('R2', ascending=False)
    res_csv = os.path.join(output_dir, 'diff_explain_regression.csv')
    res_df.to_csv(res_csv, index=False)

    # --- best stat fit on block increments ---
    best = res_df.iloc[0]
    best_col = best['stat']
    x = pd.to_numeric(s_df[best_col], errors='coerce').to_numpy()
    a, b = best['slope_block'], best['intercept_block']
    y_fit = a * x + b


    # --- reconstruct predicted cumulative diff over the whole run ---
    # Convert the block prediction to a per-frame increment and paint it piecewise-constant
    per_frame_inc_at_blocks = (y_fit / block)  # predicted Δdiff per processed frame at each block
    per_frame_inc_full = np.zeros(n_c, dtype=float)

    # define block boundaries centered on each stats print (use preceding block)
    starts = c_pos - block
    ends = c_pos

    # fill each block with its predicted per-frame increment
    for inc, s, e in zip(per_frame_inc_at_blocks, starts, ends):
        s = max(0, int(s))
        e = max(s + 1, int(e))
        per_frame_inc_full[s:e] = inc

    # extend the last rate to the remainder of the run, if any
    if ends.size > 0 and ends[-1] < n_c:
        per_frame_inc_full[ends[-1]:] = per_frame_inc_at_blocks[-1]

    # build the predicted cumulative diff (align baseline for comparability)
    pred_diff = np.cumsum(per_frame_inc_full)
    pred_diff -= pred_diff[starts[0]] if len(starts) else pred_diff[0]
    pred_diff += diff[max(0, starts[0])] if len(starts) else diff[0]

    plt.figure(figsize=(12, 6))
    plt.plot(diff, label='Actual diff (frameId - frameIdx)')
    plt.plot(pred_diff, label=f'Predicted diff from {best_col}')
    plt.xlabel('processed frames (frameIdx order)')
    plt.ylabel('cumulative drops')
    plt.title('Observed vs predicted cumulative drops')
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'diff_predicted_vs_actual.png'))
    plt.close()

    # concise textual summary for the console
    print("\n=== Diff explanation summary (block-based) ===")
    print(res_df.to_string(index=False))
    print(f"\nBest stat: {best_col}")
    print(f"  Block size used: {int(best['block_size_used'])}")
    print(f"  Estimated camera FPS (slope/block) ≈ {best['slope_per_frame~FPS']:.2f}")
    print(f"  Intercept per frame (should be ≈ -1) ≈ {best['intercept_per_frame~should_be_-1']:.2f}")
    print(f"  R² ≈ {best['R2']:.3f}  |  corr ≈ {best['corr']:.3f}")

    return res_df



def sanity_check_diff_vs_stats_simple(counters_df, stats_df, output_dir, top_k_plots=1):
    """
    Secondary check (no block logic) for explaining frame drops using timing stats.

    Method:
      - diff = frameId - frameIdx (cumulative drops)
      - y = Δdiff per processed frame
      - Each stat column is linearly interpolated to the counters' length
      - Regress y ~ a*stat + b, compute R² + Pearson/Spearman corr
      - Rank stats and plot best fit + predicted cumulative diff

    Saves:
      - plots/simple_best_stat_scatter.png
      - plots/simple_pred_vs_actual_diff.png
      - plots/simple_stats_summary.csv

    Returns:
      pandas.DataFrame with summary ranked by R².
    """

    # --- build cumulative diff and its increment per processed frame ---
    cdf = counters_df.sort_values('frameIdx').reset_index(drop=True)
    diff = (cdf['frameId'] - cdf['frameIdx']).astype(float).to_numpy()
    d_diff = np.diff(diff, prepend=diff[0])  # per-frame increase (>=0 in steady runs)

    n = len(diff)
    if n < 5 or len(stats_df) < 3:
        raise ValueError("Not enough samples to run the sanity check.")

    # common index for interpolation (0..n-1)
    t_full = np.arange(n)
    t_stat = np.linspace(0, n - 1, len(stats_df))

    # helper: evaluate a simple OLS and metrics
    def _fit_and_score(x_full, y_full):
        # OLS y ≈ a*x + b (no regularization, no block logic)
        X = np.vstack([x_full, np.ones_like(x_full)]).T
        a, b = np.linalg.lstsq(X, y_full, rcond=None)[0]
        y_hat = a * x_full + b
        ss_res = float(np.sum((y_full - y_hat) ** 2))
        ss_tot = float(np.sum((y_full - np.mean(y_full)) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
        # correlations
        pear = float(np.corrcoef(x_full, y_full)[0, 1])
        # Spearman via ranks (robust to monotone nonlinearity)
        xr = pd.Series(x_full).rank(method='average').to_numpy()
        yr = pd.Series(y_full).rank(method='average').to_numpy()
        spear = float(np.corrcoef(xr, yr)[0, 1])
        return a, b, r2, pear, spear, y_hat

    rows = []
    fits = {}  # keep best-fit arrays for plotting

    # iterate numeric stat columns only
    for col in stats_df.columns:
        x_stat = pd.to_numeric(stats_df[col], errors='coerce').to_numpy()
        if not np.isfinite(x_stat).any():
            continue
        # interpolate the stat to per-frame timebase
        x_full = np.interp(t_full, t_stat, x_stat)
        # robust guard: drop any non-finite after interp
        valid = np.isfinite(x_full) & np.isfinite(d_diff)
        if valid.sum() < 10:
            continue
        a, b, r2, pear, spear, y_hat = _fit_and_score(x_full[valid], d_diff[valid])
        rows.append({
            'stat': col,
            'slope_est_FPS': a,                # if stat is time/frame, slope ≈ camera FPS
            'intercept_expect_-1': b,          # theory suggests ≈ -1
            'R2': r2,
            'pearson': pear,
            'spearman': spear
        })
        fits[col] = (x_full, d_diff, y_hat, valid)

    if not rows:
        raise ValueError("No usable numeric stats found for the sanity check.")

    summary = pd.DataFrame(rows).sort_values('R2', ascending=False)
    os.makedirs(output_dir, exist_ok=True)
    summary.to_csv(os.path.join(output_dir, 'simple_stats_summary.csv'), index=False)

    # --- best stat scatter with fit ---
    best = summary.iloc[0]['stat']


    # Console summary
    print("\n=== Simple sanity check (no blocks) ===")
    print(summary.to_string(index=False))
    print(f"\nBest stat: {best}")
    print(f"  slope ≈ {summary.iloc[0]['slope_est_FPS']:.2f}  (≈ sending FPS if stat ≈ time/frame)")
    print(f"  intercept ≈ {summary.iloc[0]['intercept_expect_-1']:.2f}  (should be ≈ -1 by theory)")
    print(f"  R²={summary.iloc[0]['R2']:.3f}  |  Pearson={summary.iloc[0]['pearson']:.3f}  |  Spearman={summary.iloc[0]['spearman']:.3f}")

    return summary




def main():
    output_dir = get_output_dir()
    counters_df, stats_df, index_stats_data = parse_file(INPUT_FILE)
    

    # Counter overview
    print("\n\n")
    print(counters_df.head())  # preview
    print(counters_df.tail())
    print("\n\n")
    with pd.option_context('display.float_format', '{:.2f}'.format):
        print(counters_df.describe())
        
    
    # stats overview
    with pd.option_context('display.float_format', '{:.10f}'.format):
        print("\n\n")
        print(stats_df.head())  # preview
        print(stats_df.tail())
        print("\n\n")
        print(stats_df.describe())
    
    # Counter Analysis
    plot_counters(counters_df, output_dir)
    plot_diff_counters(counters_df, output_dir) 
    analyze_diff_growth(counters_df, output_dir)
    
    
    # stats Analysis
    plot_stats(stats_df, output_dir, index_stats_data, counters_df, tz="Europe/Madrid")
    
    
    # Explainatory analysis
    explain_diff_with_stats(counters_df, stats_df, output_dir, index_stats_data, default_block=30)
    sanity_check_diff_vs_stats_simple(counters_df, stats_df, output_dir)
    
    # analysis_results = integrate_analysis(counters_df, stats_df, output_dir)



if __name__ == '__main__':
    main()
