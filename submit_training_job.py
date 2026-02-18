# -*- coding: utf-8 -*-
"""
Submete o job de fine-tune do DistilBERT para o Vertex AI Training.

Pré-requisitos:
  pip install google-cloud-aiplatform google-cloud-storage
  python setup_gcp.py --project_id ... --bucket_name ...

Uso (com GPU — recomendado, ~30-60min, ~$0.35):
  python submit_training_job.py \
      --project_id SEU_PROJECT_ID \
      --bucket_name NOME_DO_BUCKET \
      --use_gpu

Uso (sem GPU — mais lento, ~2-4h, ~$0.30):
  python submit_training_job.py \
      --project_id SEU_PROJECT_ID \
      --bucket_name NOME_DO_BUCKET
"""

import argparse
import os
import sys

from google.cloud import aiplatform, storage


# ─────────────────────────────────────────────────────────────────────────────
# CONTAINERS PRÉ-CONSTRUÍDOS DO VERTEX AI
# ─────────────────────────────────────────────────────────────────────────────
CONTAINER_GPU = "us-docker.pkg.dev/vertex-ai/training/pytorch-gpu.2-2.py310:latest"
CONTAINER_CPU = "us-docker.pkg.dev/vertex-ai/training/pytorch-cpu.2-2:latest"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--project_id",   required=True)
    p.add_argument("--bucket_name",  required=True)
    p.add_argument("--region",       default="us-central1")
    p.add_argument("--epochs",       type=int, default=6)
    p.add_argument("--batch_size",   type=int, default=32)
    p.add_argument("--use_gpu",      action="store_true",
                   help="Usar GPU T4 (mais rapido, custo similar ao CPU)")
    return p.parse_args()


def upload_file(local_path: str, bucket_name: str, gcs_path: str):
    client = storage.Client()
    blob = client.bucket(bucket_name).blob(gcs_path)
    blob.upload_from_filename(local_path)
    print(f"  Upload: {local_path} → gs://{bucket_name}/{gcs_path}")


def main():
    args = parse_args()

    print("=" * 60)
    print("  Vertex AI — Submissao de Job de Treino")
    print("=" * 60)
    print(f"  Project : {args.project_id}")
    print(f"  Bucket  : gs://{args.bucket_name}")
    print(f"  Regiao  : {args.region}")
    print(f"  Modo    : {'GPU (T4)' if args.use_gpu else 'CPU'}")
    print(f"  Epochs  : {args.epochs}")
    print("=" * 60)

    # ── 1. Upload dos dados e do script ──────────────────────────────────────
    print("\n[1/3] Enviando arquivos para GCS...")

    if not os.path.exists("training_data.csv"):
        print("ERRO: training_data.csv nao encontrado.")
        print("Execute primeiro: python generate_training_data.py")
        sys.exit(1)

    if not os.path.exists("trainer/train.py"):
        print("ERRO: trainer/train.py nao encontrado.")
        sys.exit(1)

    upload_file("training_data.csv",  args.bucket_name, "data/training_data.csv")
    upload_file("trainer/train.py",   args.bucket_name, "trainer/train.py")

    # ── 2. Inicializar Vertex AI ──────────────────────────────────────────────
    print("\n[2/3] Inicializando Vertex AI...")
    aiplatform.init(
        project=args.project_id,
        location=args.region,
        staging_bucket=f"gs://{args.bucket_name}",
    )

    # ── 3. Criar e submeter o job ─────────────────────────────────────────────
    print("\n[3/3] Submetendo CustomTrainingJob...")

    container_uri = CONTAINER_GPU if args.use_gpu else CONTAINER_CPU

    job = aiplatform.CustomTrainingJob(
        display_name="classificador-comentarios-tecnicos",
        script_path="trainer/train.py",
        container_uri=container_uri,
        requirements=[
            "accelerate>=0.21.0",
            "transformers==4.40.0",
            "scikit-learn==1.4.2",
            "pandas==2.2.2",
            "numpy==1.26.4",
            "google-cloud-storage==2.16.0",
        ],
    )

    job_args = [
        f"--data_gcs_path=gs://{args.bucket_name}/data/training_data.csv",
        f"--epochs={args.epochs}",
        f"--batch_size={args.batch_size}",
        "--learning_rate=2e-5",
        "--max_len=64",
    ]

    # Configurações de máquina
    if args.use_gpu:
        machine_type       = "n1-standard-4"   # 4 vCPUs, 15GB RAM
        accelerator_type   = "NVIDIA_TESLA_T4"
        accelerator_count  = 1
        est_time  = "30-60 min"
        est_cost  = "~$0.35"
    else:
        machine_type       = "n1-standard-8"   # 8 vCPUs, 30GB RAM
        accelerator_type   = None
        accelerator_count  = 0
        est_time  = "2-4 horas"
        est_cost  = "~$0.60"

    print(f"\n  Maquina    : {machine_type}")
    print(f"  Acelerador : {accelerator_type or 'nenhum (CPU)'}")
    print(f"  Tempo est. : {est_time}")
    print(f"  Custo est. : {est_cost}")
    print(f"\n  Iniciando... (sync=False — o job roda em segundo plano)")

    run_kwargs = dict(
        args=job_args,
        replica_count=1,
        machine_type=machine_type,
        base_output_dir=f"gs://{args.bucket_name}/model_output",
        sync=False,  # não bloqueia o terminal
    )
    if args.use_gpu:
        run_kwargs["accelerator_type"]  = accelerator_type
        run_kwargs["accelerator_count"] = accelerator_count

    job.run(**run_kwargs)

    # ── Resultado ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Job submetido com sucesso!")
    print("=" * 60)
    print(f"\n  Acompanhe o progresso em:")
    print(f"  https://console.cloud.google.com/vertex-ai/training/custom-jobs"
          f"?project={args.project_id}")
    print(f"\n  Modelo sera salvo em:")
    print(f"  gs://{args.bucket_name}/model_output/")
    print(f"\n  Quando terminar, execute:")
    print(f"  python download_model.py --bucket_name {args.bucket_name}")
    print()


if __name__ == "__main__":
    main()
