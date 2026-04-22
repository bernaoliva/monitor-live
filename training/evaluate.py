# -*- coding: utf-8 -*-
"""
Fase 6: avalia modelo novo (BERTimbau v2) vs atual (v1) no test_gold.

Compara em métricas críticas:
  - F1, Precision, Recall, ROC-AUC
  - Precision@Recall=0.90 (métrica-alvo)
  - Breakdown por canal e por categoria
  - Latência p50/p99 single-text em CPU

Gates de aceitação:
  - F1 novo >= F1 atual + 0.05
  - Precision@Recall=0.90 >= 0.85
  - Latência p99 single-text <= 100ms em CPU

Uso:
  python training/evaluate.py \\
      --gold training/corpus/test_gold.parquet \\
      --model-v2 ./model_v2 \\
      --model-v1-url https://classificador-tecnico-559450313387.us-central1.run.app
"""

import argparse
import json
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests
import torch
from sklearn.metrics import (
    accuracy_score, f1_score, precision_score, recall_score,
    roc_auc_score, precision_recall_curve, confusion_matrix,
)
from transformers import BertTokenizerFast, BertForSequenceClassification


def predict_v2(model_dir: str, texts: list[str], device: str = "cuda",
               batch_size: int = 64, max_len: int = 96) -> tuple[list[int], list[float], list[float]]:
    """Roda BERTimbau local. Retorna (preds, probs_pos, latencies_ms)."""
    tokenizer = BertTokenizerFast.from_pretrained(model_dir)
    model = BertForSequenceClassification.from_pretrained(model_dir).to(device).eval()

    preds, probs_pos, latencies = [], [], []
    for i in range(0, len(texts), batch_size):
        chunk = texts[i:i+batch_size]
        enc = tokenizer(chunk, truncation=True, padding=True, max_length=max_len,
                        return_tensors="pt").to(device)
        t0 = time.perf_counter()
        with torch.no_grad():
            out = model(**enc)
        dt_ms = (time.perf_counter() - t0) * 1000 / max(len(chunk), 1)
        latencies.extend([dt_ms] * len(chunk))

        probs = torch.softmax(out.logits, dim=-1).cpu().numpy()
        chunk_preds = probs.argmax(-1).tolist()
        preds.extend(chunk_preds)
        probs_pos.extend(probs[:, 1].tolist())
    return preds, probs_pos, latencies


def predict_v1(url: str, texts: list[str], batch_size: int = 64) -> tuple[list[int], list[float]]:
    """Roda o serving atual (Cloud Run) via /classify/batch."""
    preds, probs_pos = [], []
    session = requests.Session()
    for i in range(0, len(texts), batch_size):
        chunk = texts[i:i+batch_size]
        r = session.post(f"{url}/classify/batch", json={"texts": chunk}, timeout=30)
        r.raise_for_status()
        for item in r.json():
            preds.append(1 if item.get("is_technical") else 0)
            probs_pos.append(item.get("prob_technical", 1.0 if item.get("is_technical") else 0.0))
    return preds, probs_pos


def metrics_block(name: str, y_true, y_pred, y_prob) -> dict:
    """Calcula bloco completo de métricas."""
    out = {
        "name":       name,
        "accuracy":   float(accuracy_score(y_true, y_pred)),
        "f1":         float(f1_score(y_true, y_pred, average="binary", zero_division=0)),
        "precision":  float(precision_score(y_true, y_pred, average="binary", zero_division=0)),
        "recall":     float(recall_score(y_true, y_pred, average="binary", zero_division=0)),
    }
    if len(set(y_true)) > 1:
        out["roc_auc"] = float(roc_auc_score(y_true, y_prob))
        pr, rc, _ = precision_recall_curve(y_true, y_prob)
        idx = np.argmin(np.abs(rc - 0.90))
        out["precision_at_recall_90"] = float(pr[idx])
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    out["confusion_matrix"] = {"TN": int(tn), "FP": int(fp), "FN": int(fn), "TP": int(tp)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default="training/corpus/test_gold.parquet")
    ap.add_argument("--model-v2", default="./model_v2",
                    help="diretório do modelo BERTimbau treinado")
    ap.add_argument("--model-v1-url",
                    default="https://classificador-tecnico-559450313387.us-central1.run.app",
                    help="URL do Cloud Run do modelo atual (v1)")
    ap.add_argument("--out", default="training/eval_results_v2.json")
    ap.add_argument("--report-md", default="training/eval_results_v2.md")
    ap.add_argument("--skip-v1", action="store_true",
                    help="pula avaliação v1 (se endpoint indisponível)")
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")

    gold = pd.read_parquet(args.gold)
    print(f"Test gold: {len(gold):,} linhas")
    print(f"  positivos (label): {gold['label'].sum():,} ({100*gold['label'].mean():.1f}%)")

    texts  = gold["text"].tolist()
    y_true = gold["label"].tolist()

    # === Modelo v2 (novo) ===
    print(f"\n=== V2: BERTimbau ({args.model_v2}) ===")
    t0 = time.time()
    v2_pred, v2_prob, v2_lat = predict_v2(args.model_v2, texts, device=device)
    print(f"  {len(texts)} predições em {time.time()-t0:.1f}s")
    print(f"  latência p50={np.percentile(v2_lat, 50):.1f}ms "
          f"p99={np.percentile(v2_lat, 99):.1f}ms (device={device})")
    v2_metrics = metrics_block("v2", y_true, v2_pred, v2_prob)
    v2_metrics["latency_p50_ms"] = float(np.percentile(v2_lat, 50))
    v2_metrics["latency_p99_ms"] = float(np.percentile(v2_lat, 99))

    # === Modelo v1 (atual) ===
    v1_metrics = None
    if not args.skip_v1:
        print(f"\n=== V1: Cloud Run ({args.model_v1_url}) ===")
        try:
            t0 = time.time()
            v1_pred, v1_prob = predict_v1(args.model_v1_url, texts)
            print(f"  {len(texts)} predições em {time.time()-t0:.1f}s")
            v1_metrics = metrics_block("v1", y_true, v1_pred, v1_prob)
        except Exception as e:
            print(f"  ERRO v1: {e}")

    # === Breakdown por canal ===
    per_channel = {}
    for ch in gold["channel"].dropna().unique():
        mask = gold["channel"] == ch
        if mask.sum() < 10:
            continue
        per_channel[ch] = metrics_block(
            f"v2-{ch}",
            [y_true[i] for i in range(len(y_true)) if mask.iloc[i]],
            [v2_pred[i] for i in range(len(v2_pred)) if mask.iloc[i]],
            [v2_prob[i] for i in range(len(v2_prob)) if mask.iloc[i]],
        )

    report = {
        "gold_size": len(gold),
        "gold_positives": int(gold["label"].sum()),
        "v2": v2_metrics,
        "v1": v1_metrics,
        "v2_per_channel": per_channel,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")

    # === Gates ===
    gates = []
    if v1_metrics:
        gate_f1 = v2_metrics["f1"] >= v1_metrics["f1"] + 0.05
        gates.append(("F1 v2 ≥ F1 v1 + 0.05",
                      gate_f1, f"v2={v2_metrics['f1']:.3f} v1={v1_metrics['f1']:.3f}"))
    if "precision_at_recall_90" in v2_metrics:
        gate_pr = v2_metrics["precision_at_recall_90"] >= 0.85
        gates.append(("Precision@Recall=0.90 ≥ 0.85",
                      gate_pr, f"{v2_metrics['precision_at_recall_90']:.3f}"))
    gate_lat = v2_metrics["latency_p99_ms"] <= 100
    gates.append(("Latência p99 ≤ 100ms (CPU p/ T4-proxy)",
                  gate_lat, f"{v2_metrics['latency_p99_ms']:.1f}ms"))

    # === Markdown report ===
    lines = [
        "# Eval v2 — BERTimbau vs DistilBERT (v1)",
        "",
        f"**Test gold**: {len(gold):,} comentários ({100*gold['label'].mean():.1f}% positivos)",
        "",
        "## Métricas",
        "",
        "| Métrica | v2 (BERTimbau) | v1 (atual) |",
        "|---------|---------------:|-----------:|",
    ]
    for k in ["accuracy", "f1", "precision", "recall", "roc_auc", "precision_at_recall_90"]:
        v2v = v2_metrics.get(k, "—")
        v1v = v1_metrics.get(k, "—") if v1_metrics else "—"
        v2s = f"{v2v:.4f}" if isinstance(v2v, float) else v2v
        v1s = f"{v1v:.4f}" if isinstance(v1v, float) else v1v
        lines.append(f"| {k} | {v2s} | {v1s} |")
    lines += ["", f"**Latência v2**: p50={v2_metrics['latency_p50_ms']:.1f}ms  p99={v2_metrics['latency_p99_ms']:.1f}ms", ""]

    lines += ["## Gates de aceitação", ""]
    for name, ok, detail in gates:
        lines.append(f"- {'✅' if ok else '❌'} **{name}** — {detail}")

    Path(args.report_md).write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport: {args.report_md}")
    print(f"JSON:   {args.out}")

    print("\n=== GATES ===")
    all_ok = True
    for name, ok, detail in gates:
        print(f"  {'✅' if ok else '❌'} {name} — {detail}")
        all_ok = all_ok and ok
    print(f"\n{'✅ LIBERADO para deploy shadow mode (Fase 7)' if all_ok else '❌ BLOQUEADO — revisar treino'}")


if __name__ == "__main__":
    main()
