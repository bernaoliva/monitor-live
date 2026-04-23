# -*- coding: utf-8 -*-
"""
Fase 6b — Calibração: temperature scaling + threshold tuning.

Pós-treino obrigatório em produção. Dois ajustes:

1. Temperature Scaling (Guo et al. 2017): 1 parâmetro que corrige
   over/underconfidence do softmax. Ajustado no val set via NLL.

2. Threshold tuning: em vez de 0.5 (quase sempre errado), escolhe o
   threshold que maximiza F1 (ou F-beta configurável) no val set.

Aplicado no serving/app.py via 2 parâmetros em model_info.json:
  - temperature: float, divide os logits antes de softmax
  - threshold:   float, corte pra is_technical=True

Uso:
  python training/calibrate.py \\
      --model-dir ./model_v2 \\
      --val training/corpus/val.parquet \\
      --out ./model_v2/calibration.json
"""

import argparse
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from sklearn.metrics import fbeta_score, precision_recall_curve
from transformers import AutoTokenizer, AutoModelForSequenceClassification


def fit_temperature(logits: np.ndarray, labels: np.ndarray,
                    lr: float = 0.01, max_iter: int = 200) -> float:
    """Ajusta T ∈ (0, inf) minimizando NLL(softmax(logits/T), labels)."""
    T = torch.ones(1, requires_grad=True)
    optimizer = torch.optim.LBFGS([T], lr=lr, max_iter=max_iter)
    logits_t = torch.tensor(logits, dtype=torch.float32)
    labels_t = torch.tensor(labels, dtype=torch.long)

    def closure():
        optimizer.zero_grad()
        loss = F.cross_entropy(logits_t / T.clamp(min=0.05), labels_t)
        loss.backward()
        return loss

    optimizer.step(closure)
    return float(T.detach().clamp(min=0.05).item())


def choose_threshold(probs: np.ndarray, labels: np.ndarray,
                     beta: float = 1.0) -> tuple[float, float]:
    """Sweep em [0.05, 0.95] e retorna (threshold, F_beta) que maximiza F-beta."""
    thresholds = np.linspace(0.05, 0.95, 91)
    best_t, best_f = 0.5, 0.0
    for t in thresholds:
        preds = (probs >= t).astype(int)
        f = fbeta_score(labels, preds, beta=beta, zero_division=0)
        if f > best_f:
            best_f, best_t = f, t
    return float(best_t), float(best_f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--val",       default="training/corpus/val.parquet")
    ap.add_argument("--gold",      default="training/corpus/test_gold.parquet",
                    help="opcional — para avaliação final com ground truth humano")
    ap.add_argument("--out",       default=None)
    ap.add_argument("--beta",      type=float, default=1.0,
                    help="β do F-beta (0.5=favorece precision, 2=favorece recall)")
    ap.add_argument("--batch-size", type=int, default=128)
    ap.add_argument("--max-len",   type=int, default=96)
    args = ap.parse_args()

    out_path = Path(args.out) if args.out else Path(args.model_dir) / "calibration.json"
    device = "cuda" if torch.cuda.is_available() else "cpu"

    # === Carrega modelo ===
    print(f"Carregando modelo de {args.model_dir}...")
    tokenizer = AutoTokenizer.from_pretrained(args.model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(args.model_dir).to(device).eval()

    # === Infer no val ===
    import pandas as pd
    val = pd.read_parquet(args.val)
    print(f"Val: {len(val):,} ({val['label'].sum():,} positivos)")
    texts = val["text"].tolist()
    labels = val["label"].astype(int).to_numpy()

    all_logits = []
    with torch.no_grad():
        for i in range(0, len(texts), args.batch_size):
            chunk = texts[i:i+args.batch_size]
            enc = tokenizer(chunk, truncation=True, padding=True,
                            max_length=args.max_len, return_tensors="pt").to(device)
            out = model(**enc)
            all_logits.append(out.logits.cpu().numpy())
    logits = np.concatenate(all_logits, axis=0)

    # === 1. Temperature scaling ===
    print("\n=== Temperature Scaling ===")
    T_before = 1.0
    T_fitted = fit_temperature(logits, labels)
    print(f"  T_before: 1.0")
    print(f"  T_fitted: {T_fitted:.4f}")
    if T_fitted > 1.2:
        print(f"  → modelo estava OVERCONFIDENT (T>1 suaviza)")
    elif T_fitted < 0.8:
        print(f"  → modelo estava UNDERCONFIDENT (T<1 aguça)")
    else:
        print(f"  → calibração já razoável")

    # === 2. Threshold tuning ===
    print(f"\n=== Threshold Tuning (F-{args.beta}) ===")
    probs_T = F.softmax(torch.tensor(logits) / T_fitted, dim=-1)[:, 1].numpy()
    best_t, best_f = choose_threshold(probs_T, labels, beta=args.beta)
    print(f"  best threshold: {best_t:.3f}  (F-{args.beta} = {best_f:.4f})")

    # === 3. Curva PR pra referência ===
    pr, rc, _ = precision_recall_curve(labels, probs_T)
    idx_90r = np.argmin(np.abs(rc - 0.90))
    idx_95r = np.argmin(np.abs(rc - 0.95))
    print(f"\n  precision@recall=0.90: {pr[idx_90r]:.4f}")
    print(f"  precision@recall=0.95: {pr[idx_95r]:.4f}")

    # === 4. Se tem gold set, reporta métricas finais ===
    gold_metrics = None
    gold_path = Path(args.gold)
    if gold_path.exists():
        print(f"\n=== Avaliação no gold set ({gold_path}) ===")
        gold = pd.read_parquet(gold_path)
        # usa HUMAN_is_technical se preenchido, senão label v2
        if "HUMAN_is_technical" in gold.columns and gold["HUMAN_is_technical"].notna().any():
            y_true = gold["HUMAN_is_technical"].astype(int).to_numpy()
            print(f"  usando HUMAN_is_technical como ground truth")
        else:
            y_true = gold["label"].astype(int).to_numpy()
            print(f"  ⚠️  HUMAN_is_technical vazio — usando label v2 (menos confiável)")
        gold_texts = gold["text"].tolist()
        gold_logits = []
        with torch.no_grad():
            for i in range(0, len(gold_texts), args.batch_size):
                chunk = gold_texts[i:i+args.batch_size]
                enc = tokenizer(chunk, truncation=True, padding=True,
                                max_length=args.max_len, return_tensors="pt").to(device)
                gold_logits.append(model(**enc).logits.cpu().numpy())
        gold_logits = np.concatenate(gold_logits, axis=0)
        gold_probs = F.softmax(torch.tensor(gold_logits) / T_fitted, dim=-1)[:, 1].numpy()
        gold_preds = (gold_probs >= best_t).astype(int)
        from sklearn.metrics import f1_score, precision_score, recall_score
        gold_metrics = {
            "f1":        float(f1_score(y_true, gold_preds, zero_division=0)),
            "precision": float(precision_score(y_true, gold_preds, zero_division=0)),
            "recall":    float(recall_score(y_true, gold_preds, zero_division=0)),
        }
        for k, v in gold_metrics.items():
            print(f"  {k}: {v:.4f}")

    # === Salva ===
    calibration = {
        "temperature":           T_fitted,
        "threshold":             best_t,
        "f_beta_used":           args.beta,
        "f_beta_score":          best_f,
        "precision_at_recall_90": float(pr[idx_90r]),
        "precision_at_recall_95": float(pr[idx_95r]),
        "gold_metrics":          gold_metrics,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(calibration, indent=2), encoding="utf-8")
    print(f"\nSalvo: {out_path}")


if __name__ == "__main__":
    main()
