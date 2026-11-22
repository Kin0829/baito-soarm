"""Analyze a multi-joint SO-101 follow-latency CSV written by measure_latency.py.

Usage: python analyze_latency.py results/latency-XXXX.csv [--max-lag 500] [--min-motion 3]
"""
import argparse
import csv
import math
from pathlib import Path

import numpy as np

JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")
TIME_FIELDS = ("loop_ms", "leader_ms", "write_start_ms", "write_done_ms", "follower_ms")
JOINT_FIELDS = ("leader", "requested", "sent", "follower", "limited")


def columns(joint):
    return [f"{joint}.{field}" for field in JOINT_FIELDS]


def load(path):
    with open(path, newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        header = reader.fieldnames or []
    if not rows or "loop_ms" not in header:
        raise ValueError(f"{path} is not a multi-joint latency CSV")
    joints = [j for j in JOINTS if f"{j}.requested" in header]
    data = {k: np.array([float(r[k]) for r in rows]) for k in header}
    return data, joints


def sample_times(data):
    """Best estimate of when each signal was sampled or commanded, in ms.

    A sync_read returns positions captured somewhere inside the read call, so the midpoint of
    the call is used. A goal takes effect when the write call has returned.
    """
    leader = (data["loop_ms"] + data["leader_ms"]) / 2
    sent = data["write_done_ms"]
    follower = (data["write_done_ms"] + data["follower_ms"]) / 2
    return leader, sent, follower


def best_lag(t_a, a, t_b, b, max_lag, step=1.0):
    """Shift (ms) that best aligns b(t + lag) with a(t), ignoring a constant offset.

    Returns (lag_ms, residual_rms) or (None, None) when there is too little overlap.
    """
    start = max(t_a[0], t_b[0])
    stop = min(t_a[-1], t_b[-1] - max_lag)
    if stop - start < 500:
        return None, None
    grid = np.arange(start, stop, 2.0)
    ref = np.interp(grid, t_a, a)
    best = (None, math.inf)
    for lag in np.arange(0, max_lag + step, step):
        diff = ref - np.interp(grid + lag, t_b, b)
        cost = float(np.var(diff))
        if cost < best[1]:
            best = (float(lag), cost)
    return best[0], math.sqrt(best[1])


def analyze(data, joints, max_lag=500.0, min_motion=3.0):
    leader_t, sent_t, follower_t = sample_times(data)
    periods = np.diff(data["loop_ms"])
    print(f"Samples: {len(periods) + 1} over {data['loop_ms'][-1] / 1000:.1f} s")
    print(f"Loop: {1000 / periods.mean():.1f} Hz mean | median {np.median(periods):.2f} ms"
          f" | p95 {np.percentile(periods, 95):.2f} ms | max {periods.max():.2f} ms")
    print(f"Median bus calls: leader read {np.median(data['leader_ms'] - data['loop_ms']):.2f} ms"
          f" | goal write {np.median(data['write_done_ms'] - data['write_start_ms']):.2f} ms"
          f" | follower read {np.median(data['follower_ms'] - data['write_done_ms']):.2f} ms")
    print("All joints share one sync_read/sync_write per frame, so their timestamps are identical;"
          " differences between joints come from the servos.\n")

    header = (f"{'joint':<14}{'range':>8}{'peak v':>9}{'limited':>9}"
              f"{'L->sent':>9}{'sent->F':>9}{'L->F':>8}{'err rms':>9}{'err max':>9}")
    print(header)
    print(f"{'':<14}{'deg':>8}{'deg/s':>9}{'frames':>9}{'ms':>9}{'ms':>9}{'ms':>8}{'deg':>9}{'deg':>9}")
    print("-" * len(header))
    results = {}
    for joint in joints:
        req = data[f"{joint}.requested"]
        sent = data[f"{joint}.sent"]
        fol = data[f"{joint}.follower"]
        limited = int(data[f"{joint}.limited"].sum()) if f"{joint}.limited" in data else 0
        span = float(req.max() - req.min())
        velocity = np.abs(np.diff(req) / np.maximum(np.diff(leader_t), 1e-3) * 1000)
        peak = float(np.percentile(velocity, 95)) if len(velocity) else 0.0
        error = np.interp(follower_t, leader_t, req) - fol
        err_rms = float(np.sqrt(np.mean((error - error.mean()) ** 2)))
        err_max = float(np.abs(error).max())
        name = joint + (" (%)" if joint == "gripper" else "")
        if span < min_motion:
            print(f"{name:<14}{span:>8.1f}{peak:>9.0f}{limited:>9}   moved too little to time")
            results[joint] = None
            continue
        lag_ls, _ = best_lag(leader_t, req, sent_t, sent, max_lag)
        lag_sf, _ = best_lag(sent_t, sent, follower_t, fol, max_lag)
        lag_lf, _ = best_lag(leader_t, req, follower_t, fol, max_lag)

        def fmt(lag, width):
            if lag is None:
                return f"{'n/a':>{width}}"
            mark = "!" if lag >= max_lag else ""
            return f"{lag:>{width - len(mark)}.0f}{mark}"

        print(f"{name:<14}{span:>8.1f}{peak:>9.0f}{limited:>9}"
              f"{fmt(lag_ls, 9)}{fmt(lag_sf, 9)}{fmt(lag_lf, 8)}{err_rms:>9.2f}{err_max:>9.2f}")
        results[joint] = dict(span=span, peak_speed=peak, limited=limited, leader_to_sent=lag_ls,
                              sent_to_follower=lag_sf, leader_to_follower=lag_lf,
                              error_rms=err_rms, error_max=err_max)
    clipped = [j for j, r in results.items() if r and r["limited"] > 0.1 * len(data["loop_ms"])]
    if clipped:
        print(f"\nWARNING: {', '.join(clipped)} were limited in >10% of frames. Their L->sent, L->F and err"
              " compare against a clipped command and are not latency; use sent->F, or rerun with a"
              " larger --travel / --speed.")
    print("\nL = leader. Lags are the time shift that best overlays the two whole curves"
          " (offset removed).")
    print("L->sent > 0 means the software limits slowed the command: see 'limited'.")
    print(f"'!' = hit the {max_lag:g} ms search limit (unreliable). err = requested - follower"
          " at the same moment; rms excludes the constant offset.")
    print("Gripper values are 0-100 % of its range, not degrees.")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--max-lag", type=float, default=500, help="Largest lag to search, ms")
    parser.add_argument("--min-motion", type=float, default=3, help="Skip joints moving less, deg")
    args = parser.parse_args()
    data, joints = load(args.csv)
    analyze(data, joints, args.max_lag, args.min_motion)


if __name__ == "__main__":
    main()
