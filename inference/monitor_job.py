# -*- coding: utf-8 -*-
"""Monitora um Vertex AI Custom Job rodando."""
import argparse
import time
from datetime import datetime

from google.cloud import aiplatform


PROJECT  = "youtube-monitor-474920"
REGION   = "us-central1"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-id", required=True, help="Job ID numérico")
    ap.add_argument("--poll", type=int, default=60, help="poll interval em segundos")
    args = ap.parse_args()

    aiplatform.init(project=PROJECT, location=REGION)
    job = aiplatform.CustomJob.get(args.job_id)

    while True:
        # Refresh
        job._sync_gca_resource()
        state = job.state.name
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] State: {state}")

        if state in ("JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED",
                     "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"):
            print(f"\nFinal state: {state}")
            if state != "JOB_STATE_SUCCEEDED":
                print("Logs:")
                print(f"  https://console.cloud.google.com/logs/query?project={PROJECT}")
            break

        time.sleep(args.poll)


if __name__ == "__main__":
    main()
