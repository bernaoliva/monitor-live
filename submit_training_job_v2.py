# -*- coding: utf-8 -*-
"""
Submete job v2 do classificador (mmBERT-base) para Vertex AI A100.

Uploadeia train.parquet, val.parquet, test_gold.parquet para GCS,
sobe o trainer/train_v2.py, e roda na A100 80GB.

Uso:
  python submit_training_job_v2.py
  python submit_training_job_v2.py --epochs 5 --no-focal
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

from google.cloud import aiplatform, storage


PROJECT  = "youtube-monitor-474920"
REGION   = "us-central1"
BUCKET   = "monitor-lives-bucket"
JOB_PREFIX = "trainer-mmbert-v2"

CONTAINER_GPU = "us-docker.pkg.dev/vertex-ai/training/pytorch-gpu.2-2.py310:latest"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--epochs",       type=int, default=4)
    p.add_argument("--batch-size",   type=int, default=128)
    p.add_argument("--lr",           type=float, default=3e-5)
    p.add_argument("--pos-weight",   type=float, default=5.0)
    p.add_argument("--no-focal",     action="store_true")
    p.add_argument("--no-oversample", action="store_true")
    p.add_argument("--oversample-ratio", type=float, default=0.5)
    p.add_argument("--focal-gamma", type=float, default=2.0)
    p.add_argument("--distill-alpha", type=float, default=0.5)
    p.add_argument("--rdrop-alpha",   type=float, default=1.0)
    p.add_argument("--max-len",       type=int, default=96)
    return p.parse_args()


def upload(bucket, local, remote):
    blob = bucket.blob(remote)
    blob.upload_from_filename(local)
    uri = f"gs://{BUCKET}/{remote}"
    print(f"  upload: {local} -> {uri}")
    return uri


def main():
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    job_name = f"{JOB_PREFIX}-{timestamp}"

    aiplatform.init(project=PROJECT, location=REGION,
                    staging_bucket=f"gs://{BUCKET}")

    # Verifica arquivos locais
    required = [
        "training/corpus/train.parquet",
        "training/corpus/val.parquet",
        "training/corpus/test_gold.parquet",
        "trainer/train_v2.py",
    ]
    for f in required:
        if not Path(f).exists():
            print(f"ERRO: {f} nao existe")
            sys.exit(1)

    # Upload
    print("=" * 70)
    print("Uploading data + script to GCS...")
    print("=" * 70)
    client = storage.Client(project=PROJECT)
    bucket = client.bucket(BUCKET)
    base = f"training/{timestamp}"
    train_uri = upload(bucket, "training/corpus/train.parquet",
                       f"{base}/train.parquet")
    val_uri   = upload(bucket, "training/corpus/val.parquet",
                       f"{base}/val.parquet")
    upload(bucket, "training/corpus/test_gold.parquet",
           f"{base}/test_gold.parquet")
    upload(bucket, "training/corpus/test_gold_review.csv",
           f"{base}/test_gold_review.csv")

    output_dir = f"gs://{BUCKET}/{base}/model_output"

    # Args do trainer
    job_args = [
        f"--train={train_uri}",
        f"--val={val_uri}",
        f"--output-dir={output_dir}",
        f"--epochs={args.epochs}",
        f"--batch-size={args.batch_size}",
        f"--learning-rate={args.lr}",
        f"--pos-weight={args.pos_weight}",
        f"--max-len={args.max_len}",
        f"--distill-alpha={args.distill_alpha}",
        f"--rdrop-alpha={args.rdrop_alpha}",
        f"--focal-gamma={args.focal_gamma}",
        f"--oversample-ratio={args.oversample_ratio}",
    ]
    if args.no_focal:
        # Default e --focal-loss True; usa flag inversa nao trivial -> deixa default
        pass
    if args.no_oversample:
        pass

    # Job
    print("\n" + "=" * 70)
    print(f"Submitting Custom Training Job: {job_name}")
    print(f"Image: {CONTAINER_GPU}")
    print(f"Args: {job_args}")
    print("=" * 70)

    job = aiplatform.CustomTrainingJob(
        display_name=job_name,
        script_path="trainer/train_v2.py",
        container_uri=CONTAINER_GPU,
        requirements=[
            "transformers>=4.45.0",
            "accelerate>=1.0.0",
            "scikit-learn>=1.4.2",
            "pandas>=2.2.0",
            "pyarrow>=15.0.0",
            "google-cloud-storage>=2.16.0",
        ],
    )

    print("Iniciando job (vai bloquear ate o resource ser criado, depois roda async)...")
    try:
        job.submit(
            args=job_args,
            replica_count=1,
            machine_type="a2-ultragpu-1g",
            accelerator_type="NVIDIA_A100_80GB",
            accelerator_count=1,
            base_output_dir=f"gs://{BUCKET}/{base}",
        )
    except AttributeError:
        # versao antiga sem .submit, usa .run com sync=False
        job.run(
            args=job_args,
            replica_count=1,
            machine_type="a2-ultragpu-1g",
            accelerator_type="NVIDIA_A100_80GB",
            accelerator_count=1,
            base_output_dir=f"gs://{BUCKET}/{base}",
            sync=False,
        )

    print(f"\n[OK] Job submetido: {job_name}")
    print(f"  Outputs: {output_dir}")
    print(f"  Console: https://console.cloud.google.com/vertex-ai/training/custom-jobs?project={PROJECT}")
    try:
        rn = job.resource_name
        print(f"  Resource: {rn}")
    except Exception:
        print(f"  (resource ainda nao disponivel - ja deve estar criando, veja no console)")


if __name__ == "__main__":
    main()
