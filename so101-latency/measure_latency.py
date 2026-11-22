"""Measure single-joint SO-101 teleoperation without cameras."""
import argparse
import csv
import math
import statistics
import time
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path

JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex")
FIELDS = (
    "loop_ms", "leader_ms", "write_start_ms", "write_done_ms", "follower_ms",
    "leader_deg", "requested_deg", "sent_deg", "follower_deg", "limited",
)


def crossing(rows, field, clock, baseline, direction, threshold, earliest=-math.inf):
    for previous, current in zip(rows, rows[1:]):
        a = direction * (previous[field] - baseline)
        b = direction * (current[field] - baseline)
        if a < threshold <= b:
            fraction = (threshold - a) / (b - a)
            stamp = previous[clock] + fraction * (current[clock] - previous[clock])
            if stamp >= earliest:
                return stamp
    return None


def summarize(rows, baseline, threshold):
    if len(rows) < 2:
        print("Too few complete samples.")
        return
    periods = [b["loop_ms"] - a["loop_ms"] for a, b in zip(rows, rows[1:])]
    writes = [r["write_done_ms"] - r["write_start_ms"] for r in rows]
    reads = [r["leader_ms"] - r["loop_ms"] for r in rows]
    feedback_reads = [r["follower_ms"] - r["write_done_ms"] for r in rows]
    rate = 1000 / statistics.mean(periods)
    p95 = sorted(periods)[math.ceil(0.95 * len(periods)) - 1]
    print(f"Loop: {rate:.1f} Hz mean | median {statistics.median(periods):.2f} ms"
          f" | p95 {p95:.2f} ms | max {max(periods):.2f} ms")
    print(f"Median host calls: leader read {statistics.median(reads):.2f} ms"
          f" | goal write {statistics.median(writes):.2f} ms"
          f" | follower read {statistics.median(feedback_reads):.2f} ms")
    print(f"Limited commands: {sum(r['limited'] for r in rows)}/{len(rows)}")
    events = []
    for direction in (1, -1):
        leader = crossing(rows, "requested_deg", "leader_ms", baseline, direction, threshold)
        if leader is not None:
            events.append((leader, direction))
    if not events:
        print(f"No measurable leader crossing. Start still, then move once by >{threshold:g} deg.")
        return
    leader, direction = min(events)
    goal = crossing(rows, "sent_deg", "write_done_ms", baseline, direction, threshold, leader)
    actual = crossing(rows, "follower_deg", "follower_ms", baseline, direction, threshold, goal) if goal is not None else None
    if actual is None:
        print("No complete threshold crossing in the command and follower feedback.")
        return
    print(f"First {threshold:g} deg crossing (estimate):"
          f" leader -> sent {goal - leader:.1f} ms"
          f" | sent -> follower {actual - goal:.1f} ms"
          f" | leader -> follower {actual - leader:.1f} ms")


def measure(args, key):
    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
    from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig

    leader = SO101Leader(SO101LeaderConfig(port=args.leader_port, id="so101_leader", use_degrees=True))
    follower = SO101Follower(SO101FollowerConfig(port=args.follower_port, id="so101_follower", use_degrees=True))
    if not leader.calibration or not follower.calibration:
        raise RuntimeError("Saved calibration missing. Run lerobot-calibrate with the existing arm IDs.")
    print("Clear the workspace and support the follower in a resting pose before connecting.")
    print(f"Leader {args.leader_port}; follower {args.follower_port}; only {args.joint} will track.")
    if input("Verify the two physical ports, then type START: ").strip() != "START":
        return

    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / datetime.now().strftime("latency-%Y%m%d-%H%M%S-%f.csv")
    rows = []
    baseline = None
    try:
        with ExitStack() as stack:
            for arm in (leader, follower):
                stack.callback(lambda device=arm: device.disconnect() if device.is_connected else None)
                arm.connect(calibrate=False)
                if not arm.is_calibrated:
                    raise RuntimeError("Motor calibration differs from the saved file. Check ports and calibration.")
            input("Keep both arms still. Press Enter to start sampling: ")
            initial_leader = leader.get_action()[key]
            hold = follower.get_observation()
            baseline = hold[key]
            print("Hold the leader still for one second, then move the selected joint once by "
                  f"{min(8.0, args.travel * 0.8):g} deg and hold until the run ends.", flush=True)
            start = time.perf_counter()

            def stamp():
                return (time.perf_counter() - start) * 1000

            period = 1 / args.hz
            previous_sample = start
            last_sent = baseline
            while time.perf_counter() - start < args.seconds:
                tick = time.perf_counter()
                loop_ms = (tick - start) * 1000
                leader_position = leader.get_action()[key]
                leader_ms = stamp()
                requested = baseline + leader_position - initial_leader
                bounded = max(baseline - args.travel, min(baseline + args.travel, requested))
                step = args.speed * min(period, tick - previous_sample)
                target = max(last_sent - step, min(last_sent + step, bounded))
                previous_sample = tick
                write_start = stamp()
                sent = follower.send_action({**hold, key: target})[key]
                write_done = stamp()
                observed = follower.get_observation()[key]
                feedback_stamp = stamp()
                rows.append(dict(zip(FIELDS, (
                    loop_ms, leader_ms, write_start, write_done, feedback_stamp,
                    leader_position, requested, sent, observed, abs(sent - requested) > 0.05,
                ))))
                last_sent = sent
                time.sleep(max(0, tick + period - time.perf_counter()))
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if rows:
            with path.open("x", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            print(f"CSV: {path}")
            summarize(rows, baseline, args.threshold)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--leader-port", required=True, type=Path)
    parser.add_argument("--follower-port", required=True, type=Path)
    parser.add_argument("--joint", choices=JOINTS, default="shoulder_pan")
    parser.add_argument("--hz", type=float, default=30)
    parser.add_argument("--seconds", type=float, default=8)
    parser.add_argument("--travel", type=float, default=12, help="Maximum displacement from start, deg")
    parser.add_argument("--speed", type=float, default=60, help="Maximum target slope, deg/s")
    parser.add_argument("--threshold", type=float, default=2, help="Crossing threshold, deg")
    parser.add_argument("--output", type=Path, default=Path("results"))
    args = parser.parse_args()
    if not (0 < args.hz <= 60 and 2 <= args.seconds <= 60 and
            0 < args.threshold < min(8, 0.8 * args.travel) and
            0 < args.travel <= 15 and 0 < args.speed <= 90):
        parser.error("Use 0 < hz <= 60, 2–60 seconds, travel <= 15 deg, speed <= 90 deg/s, "
                     "and a threshold below the instructed test motion.")
    if not all(port.is_char_device() for port in (args.leader_port, args.follower_port)):
        parser.error("Both ports must be present. Check USB attachment and port assignments.")
    if args.leader_port.samefile(args.follower_port):
        parser.error("The arms must use different serial ports.")
    args.leader_port, args.follower_port = str(args.leader_port), str(args.follower_port)
    try:
        measure(args, f"{args.joint}.pos")
    except (RuntimeError, OSError) as exc:
        parser.exit(1, f"Measurement stopped: {exc}\n")


if __name__ == "__main__":
    main()
