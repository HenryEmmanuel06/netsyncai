"""Measure remote-command round-trip latency (REST → WSS → agent → REST).

Usage:
  python scripts/eval_latency.py --token <JWT> --device <id> \
      --api http://localhost:8000 --runs 20
"""

import argparse
import statistics
import time

import httpx


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--token", required=True)
    p.add_argument("--device", required=True)
    p.add_argument("--api", default="http://localhost:8000")
    p.add_argument("--runs", type=int, default=10)
    args = p.parse_args()

    headers = {"Authorization": f"Bearer {args.token}"}
    latencies = []
    with httpx.Client(base_url=args.api, headers=headers, timeout=60) as c:
        c.get("/health")
        for _ in range(args.runs):
            t0 = time.perf_counter()
            r = c.get(f"/api/v1/devices/{args.device}/browse", params={"path": ""})
            dt = (time.perf_counter() - t0) * 1000
            r.raise_for_status()
            latencies.append(dt)

    print(f"runs: {len(latencies)}")
    print(f"mean: {statistics.mean(latencies):.1f} ms")
    print(f"p50:  {statistics.median(latencies):.1f} ms")
    print(f"min:  {min(latencies):.1f} ms   max: {max(latencies):.1f} ms")


if __name__ == "__main__":
    main()
