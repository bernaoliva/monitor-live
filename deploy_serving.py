# -*- coding: utf-8 -*-
"""
Build e deploy do serviço de inferência no Cloud Run.
Usa Cloud Build (não precisa de Docker local).

Uso:
  python deploy_serving.py \
      --project_id SEU_PROJECT_ID \
      --bucket_name SEU_BUCKET
"""

import argparse
import os
import subprocess
import sys


def find_gcloud() -> str:
    """Localiza o executável gcloud no Windows ou Unix."""
    import shutil
    # Tenta no PATH primeiro
    g = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if g:
        return g
    # Caminhos comuns no Windows
    # Try all known user profiles in case Python runs as a different user
    home = os.path.expanduser("~")
    users_dir = os.path.dirname(home)  # e.g. C:\Users
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"),
        os.path.join(home, "AppData", "Local", "Google", "Cloud SDK", "google-cloud-sdk", "bin", "gcloud.cmd"),
        r"C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
        r"C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
    ]
    # Also scan other user profiles (handles case where Python runs as different user)
    if os.path.isdir(users_dir):
        for user in os.listdir(users_dir):
            p = os.path.join(users_dir, user, "AppData", "Local", "Google", "Cloud SDK", "google-cloud-sdk", "bin", "gcloud.cmd")
            candidates.append(p)
    for c in candidates:
        if os.path.exists(c):
            return c
    raise FileNotFoundError(
        "gcloud CLI não encontrado. Instale em: https://cloud.google.com/sdk/docs/install"
    )


GCLOUD = find_gcloud()


def run(cmd: str, check=True) -> subprocess.CompletedProcess:
    # Substitui "gcloud " pelo caminho completo
    cmd_full = cmd.replace("gcloud ", f'"{GCLOUD}" ', 1)
    print(f"\n$ {cmd_full}")
    result = subprocess.run(cmd_full, shell=True, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
    if check and result.returncode != 0:
        print(f"\nERRO ao executar: {cmd_full}")
        sys.exit(1)
    return result


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--project_id",    required=True)
    p.add_argument("--bucket_name",   required=True)
    p.add_argument("--region",        default="us-central1")
    p.add_argument("--service_name",  default="classificador-tecnico")
    p.add_argument("--memory",        default="2Gi",
                   help="Memoria do container (2Gi para CPU, 8Gi para GPU)")
    p.add_argument("--cpu",           default="2",
                   help="CPUs do container")
    p.add_argument("--max_instances", default="5",
                   help="Maximo de instancias para autoscaling")
    return p.parse_args()


def main():
    args = parse_args()

    IMAGE = (
        f"{args.region}-docker.pkg.dev/"
        f"{args.project_id}/monitor-serving/inference:latest"
    )

    print("=" * 60)
    print("  Deploy — Classificador de Comentarios Tecnicos")
    print("=" * 60)
    print(f"  Project : {args.project_id}")
    print(f"  Regiao  : {args.region}")
    print(f"  Imagem  : {IMAGE}")
    print(f"  Servico : {args.service_name}")
    print("=" * 60)

    # ── 1. Criar repositório no Artifact Registry ─────────────────────────────
    print("\n[1/4] Criando repositorio no Artifact Registry...")
    run(
        f"gcloud artifacts repositories create monitor-serving "
        f"--repository-format=docker "
        f"--location={args.region} "
        f"--project={args.project_id}",
        check=False  # ignora se já existe
    )

    # ── 2. Build da imagem com Cloud Build ───────────────────────────────────
    print("\n[2/4] Construindo imagem com Cloud Build...")
    print("  (isso pode levar 5-10 minutos na primeira vez)")
    run(
        f"gcloud builds submit . "
        f"--config=cloudbuild.yaml "
        f"--substitutions=_IMAGE={IMAGE} "
        f"--project={args.project_id} "
        f"--timeout=20m"
    )

    # ── 3. Deploy no Cloud Run ────────────────────────────────────────────────
    print("\n[3/4] Fazendo deploy no Cloud Run...")
    run(
        f"gcloud run deploy {args.service_name} "
        f"--image={IMAGE} "
        f"--region={args.region} "
        f"--platform=managed "
        f"--allow-unauthenticated "
        f"--memory={args.memory} "
        f"--cpu={args.cpu} "
        f"--concurrency=80 "
        f"--max-instances={args.max_instances} "
        f"--min-instances=0 "
        f"--port=8080 "
        f"--timeout=60 "
        f"--project={args.project_id}"
    )

    # ── 4. Pegar URL do serviço ───────────────────────────────────────────────
    print("\n[4/4] Obtendo URL do servico...")
    result = run(
        f"gcloud run services describe {args.service_name} "
        f"--region={args.region} "
        f"--project={args.project_id} "
        f"--format='value(status.url)'"
    )
    url = result.stdout.strip()

    print("\n" + "=" * 60)
    print("  Deploy concluido!")
    print("=" * 60)
    print(f"\n  URL do servico: {url}")
    print(f"\n  Teste rapido:")
    print(f'  curl -X POST {url}/classify \\')
    print(f'    -H "Content-Type: application/json" \\')
    print(f'    -d \'{{"text": "sem audio aqui"}}\'')
    print(f"\n  Adicione no monitor.py:")
    print(f"  SERVING_URL = \"{url}\"")
    print()


if __name__ == "__main__":
    main()
