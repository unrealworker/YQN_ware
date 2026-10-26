"""Check exported forklift turn rates and sampling using the runtime's linear key interpolation."""
import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRIVING = {'运送托盘', '返回地堆', '前往补给月台', '补给运回地堆'}


def audit(data):
    rows = []
    for track in data['tracks'][:5]:
        rates = []
        heading_steps = []
        speeds = []
        speed_errors = []
        previous = None
        acceleration = yaw_acceleration = 0.
        for a, b in zip(track['keys'], track['keys'][1:]):
            dt = b[0] - a[0]
            if a[7] not in DRIVING or not a[5] or not b[5] or dt <= 0:
                previous = None
                continue
            distance = math.dist(a[1], b[1]) / 100
            if distance < 1e-6:
                previous = None
                continue
            signed_angle = math.remainder(b[2] - a[2], 360)
            angle = abs(signed_angle)
            speed, yaw_rate, midpoint = distance / dt, signed_angle / dt, (a[0] + b[0]) / 2
            if previous:
                elapsed = midpoint - previous[0]
                acceleration = max(acceleration, abs(speed - previous[1]) / elapsed)
                yaw_acceleration = max(yaw_acceleration, abs(yaw_rate - previous[2]) / elapsed)
            previous = (midpoint, speed, yaw_rate)
            rates.append((abs(yaw_rate), a[0], b[0]))
            heading_steps.append(angle)
            speeds.append(distance / dt)
            expected_speed = 3.2 if a[7] in {'返回地堆', '前往补给月台'} else 2.6
            speed_errors.append(abs(speed - expected_speed))
        worst = max(rates, default=(0, 0, 0))
        rows.append(dict(id=track['id'], driving_intervals=len(rates),
                         maximum_yaw_rate_deg_s=worst[0], worst_interval_s=list(worst[1:]),
                         maximum_heading_step_deg=max(heading_steps, default=0),
                         maximum_heading_step_at_60hz_deg=worst[0]/60.,
                         maximum_speed_m_s=max(speeds, default=0),
                         maximum_cruise_speed_error_m_s=max(speed_errors, default=0),
                         maximum_linear_acceleration_m_s2=acceleration,
                         maximum_yaw_acceleration_deg_s2=yaw_acceleration))
    passed = len(rows) == 5 and all(row['driving_intervals'] > 0
        and row['maximum_heading_step_at_60hz_deg'] <= 6.01
        and row['maximum_cruise_speed_error_m_s'] <= .005 for row in rows)
    return dict(success=passed, forklifts=rows,
                scope='Actual exported moving forklift keys; shortest-angle linear interpolation as in Simulation::Sample')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=ROOT / 'Content/GHSTwinUI/data/order-replay.json')
    parser.add_argument('--report', type=Path, default=ROOT / 'Saved/OrderReplay/turning_validation.json')
    args = parser.parse_args()
    result = audit(json.loads(args.data.read_text(encoding='utf8')))
    result['timeline_sha256'] = hashlib.sha256(args.data.read_bytes()).hexdigest()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result['success'] else 1)
