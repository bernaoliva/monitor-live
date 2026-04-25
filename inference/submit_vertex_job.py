# -*- coding: utf-8 -*-
"""Submete o pipeline de labeling como Vertex AI Custom Job com container custom."""
import argparse
import os
from datetime import datetime
from pathlib import Path

from google.cloud import aiplatform, storage


PROJECT  = "youtube-monitor-474920"
REGION   = "us-central1"
BUCKET   = "monitor-lives-bucket"
IMAGE    = f"us-central1-docker.pkg.dev/{PROJECT}/vllm-images/labeling:latest"
JOB_PREFIX = "labeling-vllm"


def upload(bucket_name: str, local_path: str, remote_path: str) -> str:
    client = storage.Client(project=PROJECT)
    blob = client.bucket(bucket_name).blob(remote_path)
    blob.upload_from_filename(local_path)
    uri = f"gs://{bucket_name}/{remote_path}"
    print(f"  uploaded: {local_path} -> {uri}")
    return uri


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["gemma-4-26b-a4b", "qwen-3-30b-a3b"])
    ap.add_argument("--winner", default=None, help="Pular teste e usar esse modelo direto")
    args = ap.parse_args()

    aiplatform.init(project=PROJECT, location=REGION,
                    staging_bucket=f"gs://{BUCKET}/staging")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    job_name = f"{JOB_PREFIX}-{timestamp}"

    # 1. Upload inputs
    print("=" * 70)
    print("Uploading inputs to GCS...")
    print("=" * 70)
    pending_uri  = upload(BUCKET, "inference/data/pending.parquet",
                          f"labeling/{timestamp}/pending.parquet")
    test_uri     = upload(BUCKET, "inference/data/test_cases.parquet",
                          f"labeling/{timestamp}/test_cases.parquet")
    existing_uri = upload(BUCKET, "training/corpus/labeled_existing_with_text.parquet",
                          f"labeling/{timestamp}/labeled_existing.parquet")

    output_uri        = f"gs://{BUCKET}/labeling/{timestamp}/labeled_pending.parquet"
    test_results_uri  = f"gs://{BUCKET}/labeling/{timestamp}/test_results.json"

    # 2. Args pro container
    container_args = [
        f"--gcs-pending={pending_uri}",
        f"--gcs-test={test_uri}",
        f"--gcs-existing={existing_uri}",
        f"--gcs-output={output_uri}",
        f"--gcs-test-results={test_results_uri}",
    ]
    if args.winner:
        container_args.append(f"--winner={args.winner}")
    else:
        container_args += ["--models"] + args.models

    # 3. Submeter Custom Job com container custom
    print("\n" + "=" * 70)
    print(f"Submitting Custom Job: {job_name}")
    print(f"Image: {IMAGE}")
    print("=" * 70)

    worker_pool_specs = [{
        "machine_spec": {
            "machine_type": "a2-ultragpu-1g",
            "accelerator_type": "NVIDIA_A100_80GB",
            "accelerator_count": 1,
        },
        "replica_count": 1,
        "disk_spec": {
            "boot_disk_type": "pd-ssd",
            "boot_disk_size_gb": 300,
        },
        "container_spec": {
            "image_uri": IMAGE,
            "args": container_args,
        },
    }]

    job = aiplatform.CustomJob(
        display_name=job_name,
        worker_pool_specs=worker_pool_specs,
        staging_bucket=f"gs://{BUCKET}/staging",
    )

    job.run(sync=False, timeout=14400)  # 4h max

    job_id = job.name.split('/')[-1]
    print(f"\n✓ Job submetido: {job_name}")
    print(f"  Job ID: {job_id}")
    print(f"  Console: https://console.cloud.google.com/vertex-ai/locations/{REGION}/training/{job_id}?project={PROJECT}")
    print(f"\nOutputs esperados em:")
    print(f"  Test results: {test_results_uri}")
    print(f"  Labeled:      {output_uri}")


if __name__ == "__main__":
    main()
