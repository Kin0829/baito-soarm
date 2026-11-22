"""Measure SO-101 leader -> follower tracking latency on several joints at once, without cameras."""
import argparse
import csv
import os
import time
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path

from analyze_latency import JOINTS, TIME_FIELDS, analyze, columns, load


def measure(args):
    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
    from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig

    follower_options = {"position_p_coefficient": args.p_coefficient}
    if args.i_coefficient is not None:
        follower_options["position_i_coefficient"] = args.i_coefficient
    if args.d_coefficient is not None:
        follower_options["position_d_coefficient"] = args.d_coefficient
    leader = SO101Leader(SO101LeaderConfig(port=args.leader_port, id="so101_leader", use_degrees=True))
    follower = SO101Follower(SO101FollowerConfig(
        port=args.follower_port, id="so101_follower", use_degrees=True, **follower_options))
    if not leader.calibration or not follower.calibration:
        raise RuntimeError("Saved calibration missing. Run lerobot-calibrate with the existing arm IDs.")
    print("Clear the workspace and support the follower in a resting pose before connecting.")
    print(f"Leader {args.leader_port}; follower {args.follower_port}")
    print(f"Tracking: {', '.join(args.joints)} | no speed or travel limit, like lerobot-teleoperate"
          f" | follower P = {follower.config.position_p_coefficient}, I = {follower.config.position_i_coefficient},"
          f" D = {follower.config.position_d_coefficient}")
    if input("Verify the two physical ports, then type START: ").strip() != "START":
        return

    keys = [f"{joint}.pos" for joint in args.joints]
    fields = list(TIME_FIELDS) + [c for joint in args.joints for c in columns(joint) if not c.endswith(".limited")]
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / datetime.now().strftime(
        f"latency-%Y%m%d-%H%M%S-%f-{args.hz:g}hz-p{follower.config.position_p_coefficient}"
        f"-i{follower.config.position_i_coefficient}-d{follower.config.position_d_coefficient}.csv")
    rows = []
    try:
        with ExitStack() as stack:
            for arm in (leader, follower):
                stack.callback(lambda device=arm: device.disconnect() if device.is_connected else None)
                arm.connect(calibrate=False)
                if not arm.is_calibrated:
                    raise RuntimeError("Motor calibration differs from the saved file. Check ports and calibration.")
            input("Keep both arms still. Press Enter to start sampling: ")
            initial_leader = leader.get_action()
            hold = follower.get_observation()
            baseline = {key: hold[key] for key in keys}
            print(f"Hold still for one second, then move the leader through a natural motion for"
                  f" {args.seconds:g} s. Ctrl+C stops early.", flush=True)
            start = time.perf_counter()

            def stamp():
                return (time.perf_counter() - start) * 1000

            period = 1 / args.hz
            while time.perf_counter() - start < args.seconds:
                tick = time.perf_counter()
                loop_ms = (tick - start) * 1000
                leader_action = leader.get_action()
                leader_ms = stamp()
                requested = {key: baseline[key] + leader_action[key] - initial_leader[key] for key in keys}
                write_start = stamp()
                sent = follower.send_action({**hold, **requested})
                write_done = stamp()
                observed = follower.get_observation()
                follower_ms = stamp()
                row = [loop_ms, leader_ms, write_start, write_done, follower_ms]
                for key in keys:
                    row += [leader_action[key], requested[key], sent[key], observed[key]]
                rows.append(row)
                time.sleep(max(0, tick + period - time.perf_counter()))
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if rows:
            with path.open("x", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(fields)
                writer.writerows(rows)
            print(f"CSV: {path}\n")
            if len(rows) > 2:
                analyze(*load(path))


def check_ports(leader, follower):
    """Return an error message, or None when both ports exist and differ."""
    if os.name == "nt":
        from serial.tools import list_ports

        present = {p.device.upper() for p in list_ports.comports()}
        if not all(port.upper() in present for port in (leader, follower)):
            return (f"Both ports must be present. Found: {', '.join(sorted(present)) or 'none'}."
                    " Detach them from WSL first (usbipd detach --busid ...).")
        if leader.upper() == follower.upper():
            return "The arms must use different serial ports."
        return None
    paths = Path(leader), Path(follower)
    if not all(path.is_char_device() for path in paths):
        return "Both ports must be present. Check USB attachment and port assignments."
    if paths[0].samefile(paths[1]):
        return "The arms must use different serial ports."
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--leader-port", required=True, type=Path)
    parser.add_argument("--follower-port", required=True, type=Path)
    parser.add_argument("--joints", nargs="+", choices=JOINTS, default=list(JOINTS),
                        help="Joints that follow the leader (default: all six); the rest hold still")
    parser.add_argument("--hz", type=float, default=30)
    parser.add_argument("--seconds", type=float, default=15)
    parser.add_argument("--p-coefficient", type=int, default=32,
                        help="Follower position P gain written at connect (default 32; LeRobot uses 16)")
    parser.add_argument("--i-coefficient", type=int,
                        help="Follower position I gain written at connect (LeRobot default 0)")
    parser.add_argument("--d-coefficient", type=int,
                        help="Follower position D gain written at connect (LeRobot default 32)")
    parser.add_argument("--output", type=Path, default=Path("results"))
    args = parser.parse_args()
    args.joints = list(dict.fromkeys(args.joints))
    if not (0 < args.hz <= 60 and 3 <= args.seconds <= 120):
        parser.error("Use 0 < hz <= 60 and 3-120 seconds.")
    if not 1 <= args.p_coefficient <= 32:
        parser.error("Use a P coefficient from 1 to 32.")
    if args.i_coefficient is not None and not 0 <= args.i_coefficient <= 16:
        parser.error("Use an I coefficient from 0 to 16.")
    if args.d_coefficient is not None and not 0 <= args.d_coefficient <= 96:
        parser.error("Use a D coefficient from 0 to 96.")
    problem = check_ports(str(args.leader_port), str(args.follower_port))
    if problem:
        parser.error(problem)
    args.leader_port, args.follower_port = str(args.leader_port), str(args.follower_port)
    try:
        measure(args)
    except KeyboardInterrupt:
        print("\nCancelled.")
    except (RuntimeError, OSError) as exc:
        parser.exit(1, f"Measurement stopped: {exc}\n")


if __name__ == "__main__":
    main()
