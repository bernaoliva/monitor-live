# -*- coding: utf-8 -*-
"""
Merge dataset sintetico + comentarios reais rotulados para retreino.

Combina:
  1. training_data_backup_sintetico.csv (1850 exemplos sinteticos)
  2. real_comments_labeled.csv (comentarios reais rotulados pelo Claude)

Saida: ../training_data.csv (raiz do projeto, formato esperado pelo train.py)

Uso:
  cd training
  python merge_training_data.py
  python merge_training_data.py --upload  # tambem faz upload para GCS
"""

import argparse
import csv
import os
import random
import re
import sys
import unicodedata

random.seed(42)

SYNTHETIC_FILE = "training_data_backup_sintetico.csv"
LABELED_FILE = "real_comments_labeled.csv"
OUTPUT_FILE = os.path.join("..", "training_data.csv")

GCS_BUCKET = "SEU_BUCKET_GCS"
GCS_PATH = "data/training_data.csv"


def normalize_text(text):
    """Normaliza texto para deduplicacao."""
    t = text.strip().lower()
    t = unicodedata.normalize("NFC", t)
    t = re.sub(r"\s+", " ", t)
    return t


def load_synthetic(path):
    """Carrega dataset sintetico (text, label)."""
    rows = []
    if not os.path.exists(path):
        print(f"AVISO: {path} nao encontrado — pulando sinteticos.")
        return rows
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = (row.get("text") or "").strip()
            label = row.get("label", "0")
            if text:
                rows.append((text, int(label)))
    return rows


def load_labeled(path):
    """Carrega dados rotulados pelo Claude (text, label, ...)."""
    rows = []
    if not os.path.exists(path):
        print(f"ERRO: {path} nao encontrado.")
        print("Execute relabel_with_claude.py primeiro.")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = (row.get("text") or "").strip()
            label = row.get("label", "0")
            if text and len(text) >= 3:
                rows.append((text, int(label)))
    return rows


def deduplicate(rows):
    """Remove duplicatas por texto normalizado (mantendo a primeira ocorrencia)."""
    seen = set()
    unique = []
    for text, label in rows:
        key = (normalize_text(text), label)
        if key not in seen:
            seen.add(key)
            unique.append((text, label))
    return unique


def upload_to_gcs(local_path, bucket_name, gcs_path):
    """Upload do CSV para Google Cloud Storage."""
    try:
        from google.cloud import storage
        client = storage.Client()
        blob = client.bucket(bucket_name).blob(gcs_path)
        blob.upload_from_filename(local_path)
        print(f"Upload: {local_path} -> gs://{bucket_name}/{gcs_path}")
        return True
    except ImportError:
        print("AVISO: google-cloud-storage nao instalado. Pulando upload.")
        return False
    except Exception as e:
        print(f"ERRO ao fazer upload: {e}")
        return False


def balance_dataset(rows, target_pos_ratio=0.30):
    """Undersample negativos para atingir ratio alvo de positivos (sem augmentation)."""
    positives = [(t, l) for t, l in rows if l == 1]
    negatives = [(t, l) for t, l in rows if l == 0]

    current_ratio = len(positives) / len(rows) if rows else 0
    if current_ratio >= target_pos_ratio:
        return rows  # ja balanceado

    # Apenas undersample dos negativos — sem augmentation
    target_neg = int(len(positives) / target_pos_ratio - len(positives))
    target_neg = min(target_neg, len(negatives))
    random.shuffle(negatives)
    negatives_kept = negatives[:target_neg]

    result = positives + negatives_kept
    random.shuffle(result)
    return result


def parse_args():
    p = argparse.ArgumentParser(description="Merge sinteticos + reais para retreino")
    p.add_argument("--synthetic", default=SYNTHETIC_FILE,
                   help=f"CSV sintetico (default: {SYNTHETIC_FILE})")
    p.add_argument("--labeled", default=LABELED_FILE,
                   help=f"CSV rotulado (default: {LABELED_FILE})")
    p.add_argument("--output", default=OUTPUT_FILE,
                   help=f"CSV de saida (default: {OUTPUT_FILE})")
    p.add_argument("--upload", action="store_true",
                   help="Upload para GCS apos merge")
    p.add_argument("--bucket", default=GCS_BUCKET,
                   help=f"Bucket GCS (default: {GCS_BUCKET})")
    p.add_argument("--balance", action="store_true",
                   help="Balancear dataset para ~30%% positivos (undersample neg + augment pos)")
    return p.parse_args()


def main():
    args = parse_args()

    # 1. Carrega fontes
    print(f"Carregando sinteticos: {args.synthetic}")
    synthetic = load_synthetic(args.synthetic)
    print(f"  {len(synthetic)} exemplos sinteticos")

    print(f"Carregando rotulados: {args.labeled}")
    labeled = load_labeled(args.labeled)
    print(f"  {len(labeled)} exemplos reais rotulados")

    # 2. Merge
    all_rows = synthetic + labeled
    print(f"\nTotal antes de dedup: {len(all_rows)}")

    # 3. Deduplica
    unique = deduplicate(all_rows)
    print(f"Apos deduplicacao: {len(unique)}")

    # 4. Balancear (opcional)
    if args.balance:
        before_total = len(unique)
        unique = balance_dataset(unique, target_pos_ratio=0.30)
        print(f"Apos balanceamento: {len(unique)} (era {before_total})")
    else:
        random.shuffle(unique)

    # 5. Estatisticas
    pos = sum(1 for _, l in unique if l == 1)
    neg = sum(1 for _, l in unique if l == 0)
    total = len(unique)

    print(f"\nDataset final:")
    print(f"  Total: {total}")
    print(f"  Positivos (1): {pos} ({pos/total*100:.1f}%)")
    print(f"  Negativos (0): {neg} ({neg/total*100:.1f}%)")

    # 6. Salva CSV
    output_path = args.output
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["text", "label"])
        for text, label in unique:
            writer.writerow([text, label])

    abs_path = os.path.abspath(output_path)
    print(f"\nSalvo em: {abs_path}")

    # 7. Upload para GCS (opcional)
    if args.upload:
        print(f"\nFazendo upload para GCS...")
        upload_to_gcs(abs_path, args.bucket, GCS_PATH)

    # 8. Proximos passos
    print(f"\nProximos passos:")
    print(f"  1. python submit_training_job.py \\")
    print(f"       --project_id SEU_PROJECT_ID \\")
    print(f"       --bucket_name {args.bucket} \\")
    print(f"       --use_gpu --epochs 6")
    print(f"  2. python download_model.py --bucket_name {args.bucket}")
    print(f"  3. python deploy_serving.py")


if __name__ == "__main__":
    main()
