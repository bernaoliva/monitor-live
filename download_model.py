# -*- coding: utf-8 -*-
"""
Baixa o modelo treinado do GCS para a pasta local `model/`.
Execute depois que o job no Vertex AI terminar.

Uso:
  python download_model.py --bucket_name NOME_DO_BUCKET
"""

import argparse
import os
from google.cloud import storage


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--bucket_name", required=True)
    p.add_argument("--gcs_prefix",  default="model_output",
                   help="Pasta no bucket onde o modelo foi salvo")
    p.add_argument("--local_dir",   default="model",
                   help="Pasta local onde salvar o modelo")
    return p.parse_args()


def main():
    args = parse_args()

    os.makedirs(args.local_dir, exist_ok=True)
    client  = storage.Client()
    bucket  = client.bucket(args.bucket_name)
    blobs   = list(bucket.list_blobs(prefix=args.gcs_prefix))

    if not blobs:
        print(f"Nenhum arquivo encontrado em gs://{args.bucket_name}/{args.gcs_prefix}")
        print("Verifique se o job terminou no Vertex AI.")
        return

    print(f"Baixando {len(blobs)} arquivo(s) de gs://{args.bucket_name}/{args.gcs_prefix}...")

    for blob in blobs:
        rel  = blob.name[len(args.gcs_prefix):].lstrip("/")
        if not rel:
            continue
        dest = os.path.join(args.local_dir, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        blob.download_to_filename(dest)
        print(f"  {blob.name} → {dest}")

    print(f"\nModelo salvo em: {args.local_dir}/")

    # Arquivos podem estar em local_dir/ ou local_dir/model/
    model_subdir = os.path.join(args.local_dir, "model")
    check_dir = model_subdir if os.path.isdir(model_subdir) else args.local_dir

    print(f"\nVerificando arquivos em: {check_dir}")
    for fname, required in [
        ("config.json",           True),
        ("model.safetensors",     False),
        ("pytorch_model.bin",     False),
        ("tokenizer_config.json", True),
        ("vocab.txt",             True),
        ("metrics.json",          True),
        ("model_info.json",       True),
    ]:
        path = os.path.join(check_dir, fname)
        if os.path.exists(path):
            size = os.path.getsize(path) // 1024
            print(f"  [OK] {fname} ({size} KB)")
        elif not required:
            pass  # formato alternativo, normal nao ter
        else:
            print(f"  [FALTANDO] {fname}")

    has_model = (
        os.path.exists(os.path.join(check_dir, "model.safetensors")) or
        os.path.exists(os.path.join(check_dir, "pytorch_model.bin"))
    )
    print()
    if has_model:
        print(f"Modelo pronto! Use o caminho: {check_dir}")
    else:
        print("ATENCAO: arquivo do modelo nao encontrado.")


if __name__ == "__main__":
    main()
