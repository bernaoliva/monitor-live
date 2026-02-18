# -*- coding: utf-8 -*-
"""
Configuração inicial do Google Cloud para o projeto.
Execute UMA VEZ antes de submeter o treino.

Pré-requisitos:
  pip install google-cloud-storage google-cloud-aiplatform

Uso:
  python setup_gcp.py --project_id SEU_PROJECT_ID --bucket_name NOME_DO_BUCKET
"""

import argparse
import subprocess
import sys


def run(cmd: str, check=True):
    print(f"\n$ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr and result.returncode != 0:
        print(result.stderr.strip())
    if check and result.returncode != 0:
        print(f"\nErro ao executar: {cmd}")
        sys.exit(1)
    return result


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--project_id",   required=True, help="ID do projeto GCP")
    p.add_argument("--bucket_name",  required=True, help="Nome do bucket GCS (único globalmente)")
    p.add_argument("--region",       default="us-central1",
                   help="Região GCP (default: us-central1 — mais barata)")
    return p.parse_args()


def main():
    args = parse_args()

    print("=" * 60)
    print("  Configuracao do Google Cloud — Monitor de Lives")
    print("=" * 60)
    print(f"  Project ID : {args.project_id}")
    print(f"  Bucket     : gs://{args.bucket_name}")
    print(f"  Regiao     : {args.region}")
    print("=" * 60)

    # ── 1. Autenticar ────────────────────────────────────────────────────────
    print("\n[1/5] Verificando autenticacao gcloud...")
    result = run("gcloud auth list --filter=status:ACTIVE --format='value(account)'", check=False)
    if not result.stdout.strip():
        print("Nao autenticado. Abrindo navegador para login...")
        run("gcloud auth login")
        run("gcloud auth application-default login")
    else:
        print(f"Autenticado como: {result.stdout.strip()}")

    # ── 2. Definir projeto ───────────────────────────────────────────────────
    print(f"\n[2/5] Definindo projeto: {args.project_id}")
    run(f"gcloud config set project {args.project_id}")

    # ── 3. Habilitar APIs necessárias ────────────────────────────────────────
    print("\n[3/5] Habilitando APIs...")
    apis = [
        "aiplatform.googleapis.com",      # Vertex AI
        "storage.googleapis.com",          # Cloud Storage
        "cloudbuild.googleapis.com",       # Cloud Build
        "run.googleapis.com",              # Cloud Run (para servir depois)
        "artifactregistry.googleapis.com", # Container Registry
    ]
    for api in apis:
        run(f"gcloud services enable {api} --project={args.project_id}", check=False)
    print("APIs habilitadas.")

    # ── 4. Criar bucket GCS ──────────────────────────────────────────────────
    print(f"\n[4/5] Criando bucket: gs://{args.bucket_name}")
    result = run(
        f"gsutil ls gs://{args.bucket_name}",
        check=False
    )
    if result.returncode == 0:
        print("Bucket ja existe. Pulando criacao.")
    else:
        run(
            f"gsutil mb -p {args.project_id} "
            f"-l {args.region} "
            f"-b on "
            f"gs://{args.bucket_name}"
        )
        print(f"Bucket criado: gs://{args.bucket_name}")

    # ── 5. Criar pastas no bucket ────────────────────────────────────────────
    print("\n[5/5] Criando estrutura de pastas no bucket...")
    folders = ["data/", "model_output/", "serving/"]
    for folder in folders:
        run(
            f'echo "" | gsutil cp - gs://{args.bucket_name}/{folder}.keep',
            check=False
        )
    print("Estrutura criada.")

    # ── Resumo ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Configuracao concluida!")
    print("=" * 60)
    print(f"\n  Bucket GCS : gs://{args.bucket_name}")
    print(f"  Dados      : gs://{args.bucket_name}/data/")
    print(f"  Modelo     : gs://{args.bucket_name}/model_output/")
    print(f"\n  Proximo passo:")
    print(f"  python submit_training_job.py \\")
    print(f"    --project_id {args.project_id} \\")
    print(f"    --bucket_name {args.bucket_name} \\")
    print(f"    --use_gpu")
    print()


if __name__ == "__main__":
    main()
