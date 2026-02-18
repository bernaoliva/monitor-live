# -*- coding: utf-8 -*-
"""
Fine-tune do DistilBERT multilingual para classificar comentários técnicos.
Este script roda DENTRO do Vertex AI Training — não rode localmente.

Fluxo:
  1. Baixa training_data.csv do Google Cloud Storage
  2. Tokeniza e cria datasets PyTorch
  3. Fine-tunes DistilBERT (classificação binária)
  4. Avalia (accuracy, F1, precision, recall)
  5. Salva modelo + tokenizer no GCS (AIP_MODEL_DIR)
"""

import argparse
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import torch
from google.cloud import storage
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from torch.utils.data import Dataset
from transformers import (
    DistilBertForSequenceClassification,
    DistilBertTokenizerFast,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# ARGS
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--data_gcs_path", required=True,
                   help="Caminho GCS do CSV: gs://bucket/path/training_data.csv")
    p.add_argument("--model_name", default="distilbert-base-multilingual-cased",
                   help="Modelo base do HuggingFace Hub")
    p.add_argument("--epochs",        type=int,   default=6)
    p.add_argument("--batch_size",    type=int,   default=32)
    p.add_argument("--learning_rate", type=float, default=2e-5)
    p.add_argument("--max_len",       type=int,   default=64,
                   help="Máximo de tokens por comentário (64 é suficiente para chat)")
    p.add_argument("--warmup_ratio",  type=float, default=0.1)
    p.add_argument("--weight_decay",  type=float, default=0.01)
    p.add_argument("--val_size",      type=float, default=0.15)
    return p.parse_args()


# ─────────────────────────────────────────────────────────────────────────────
# GCS HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def gcs_download(gcs_path: str, local_path: str):
    parts = gcs_path.replace("gs://", "").split("/", 1)
    if len(parts) < 2:
        raise ValueError(f"Caminho GCS inválido (esperado gs://bucket/path): {gcs_path}")
    bucket_name, blob_name = parts[0], parts[1]
    try:
        client = storage.Client()
        client.bucket(bucket_name).blob(blob_name).download_to_filename(local_path)
        logger.info(f"Baixado: {gcs_path} → {local_path}")
    except Exception as e:
        logger.error(f"Erro ao baixar {gcs_path}: {e}")
        raise


def gcs_upload_dir(local_dir: str, gcs_dir: str):
    """Faz upload de todos os arquivos de local_dir para gcs_dir (gs://...)."""
    parts = gcs_dir.replace("gs://", "").split("/", 1)
    if len(parts) < 1 or not parts[0]:
        raise ValueError(f"Caminho GCS inválido (esperado gs://bucket/...): {gcs_dir}")
    bucket_name = parts[0]
    prefix = parts[1].rstrip("/") if len(parts) > 1 else ""

    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)

        for file_path in Path(local_dir).rglob("*"):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(local_dir)
            blob_name = f"{prefix}/{rel}" if prefix else str(rel)
            bucket.blob(blob_name).upload_from_filename(str(file_path))
            logger.info(f"Upload: gs://{bucket_name}/{blob_name}")
    except Exception as e:
        logger.error(f"Erro ao fazer upload para {gcs_dir}: {e}")
        raise


# ─────────────────────────────────────────────────────────────────────────────
# DATASET PYTORCH
# ─────────────────────────────────────────────────────────────────────────────

class CommentDataset(Dataset):
    def __init__(self, texts: list, labels: list, tokenizer, max_len: int):
        self.encodings = tokenizer(
            texts,
            truncation=True,
            padding=True,
            max_length=max_len,
            return_tensors="pt",
        )
        self.labels = labels

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        item = {k: v[idx] for k, v in self.encodings.items()}
        item["labels"] = torch.tensor(self.labels[idx], dtype=torch.long)
        return item


# ─────────────────────────────────────────────────────────────────────────────
# MÉTRICAS
# ─────────────────────────────────────────────────────────────────────────────

def compute_metrics(pred):
    labels = pred.label_ids
    preds  = pred.predictions.argmax(-1)
    return {
        "accuracy":  accuracy_score(labels, preds),
        "f1":        f1_score(labels, preds, average="binary"),
        "precision": precision_score(labels, preds, average="binary", zero_division=0),
        "recall":    recall_score(labels, preds, average="binary", zero_division=0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    # Vertex AI define AIP_MODEL_DIR apontando para gs://bucket/.../model/
    output_dir = os.environ.get("AIP_MODEL_DIR", "/tmp/model_output")
    logger.info(f"Output dir: {output_dir}")

    use_gpu = torch.cuda.is_available()
    logger.info(f"GPU disponivel: {use_gpu} | Device: {'cuda' if use_gpu else 'cpu'}")

    # ── 1. Carregar dados ─────────────────────────────────────────────────────
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        gcs_download(args.data_gcs_path, tmp.name)
        df = pd.read_csv(tmp.name)

    df = df.dropna(subset=["text", "label"])
    df["text"]  = df["text"].astype(str).str.strip()
    df["label"] = df["label"].astype(int)

    logger.info(
        f"Dataset: {len(df)} exemplos | "
        f"positivos: {df['label'].sum()} | "
        f"negativos: {(df['label']==0).sum()}"
    )

    # ── 2. Split treino / validação ───────────────────────────────────────────
    X_train, X_val, y_train, y_val = train_test_split(
        df["text"].tolist(),
        df["label"].tolist(),
        test_size=args.val_size,
        random_state=42,
        stratify=df["label"].tolist(),
    )
    logger.info(f"Treino: {len(X_train)} | Validacao: {len(X_val)}")

    # ── 3. Tokenizer & datasets ───────────────────────────────────────────────
    tokenizer     = DistilBertTokenizerFast.from_pretrained(args.model_name)
    train_dataset = CommentDataset(X_train, y_train, tokenizer, args.max_len)
    val_dataset   = CommentDataset(X_val,   y_val,   tokenizer, args.max_len)

    # ── 4. Modelo ─────────────────────────────────────────────────────────────
    model = DistilBertForSequenceClassification.from_pretrained(
        args.model_name,
        num_labels=2,
        id2label={0: "nao_tecnico", 1: "tecnico"},
        label2id={"nao_tecnico": 0, "tecnico": 1},
    )

    # ── 5. Hiperparâmetros de treino ──────────────────────────────────────────
    checkpoints_dir = "/tmp/checkpoints"
    training_args = TrainingArguments(
        output_dir=checkpoints_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=64,
        learning_rate=args.learning_rate,
        warmup_ratio=args.warmup_ratio,
        weight_decay=args.weight_decay,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        logging_steps=20,
        dataloader_num_workers=0,
        report_to="none",      # desativa wandb/tensorboard
        no_cuda=not use_gpu,
    )

    # ── 6. Treinar ────────────────────────────────────────────────────────────
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )

    logger.info("=== Iniciando treinamento ===")
    trainer.train()

    # ── 7. Avaliação final ────────────────────────────────────────────────────
    results = trainer.evaluate()
    logger.info("=== Resultados finais ===")
    for k, v in results.items():
        logger.info(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")

    # ── 8. Salvar modelo ──────────────────────────────────────────────────────
    local_final = "/tmp/final_model"
    os.makedirs(local_final, exist_ok=True)

    trainer.save_model(local_final)
    tokenizer.save_pretrained(local_final)

    # Salvar métricas e config junto
    with open(os.path.join(local_final, "metrics.json"), "w") as f:
        json.dump(results, f, indent=2)

    config_info = {
        "model_name": args.model_name,
        "max_len": args.max_len,
        "epochs": args.epochs,
        "labels": {"0": "nao_tecnico", "1": "tecnico"},
    }
    with open(os.path.join(local_final, "model_info.json"), "w") as f:
        json.dump(config_info, f, indent=2)

    # ── 9. Upload para GCS (se output_dir for gs://) ─────────────────────────
    if output_dir.startswith("gs://"):
        logger.info(f"Enviando modelo para GCS: {output_dir}")
        gcs_upload_dir(local_final, output_dir)
    else:
        os.makedirs(output_dir, exist_ok=True)
        shutil.copytree(local_final, output_dir, dirs_exist_ok=True)

    logger.info(f"=== Modelo salvo em: {output_dir} ===")


if __name__ == "__main__":
    main()
