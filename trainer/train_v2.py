# -*- coding: utf-8 -*-
"""
Fase 5: fine-tune do classificador v2.

Backbone padrão: mmBERT-base (jhu-clsp/mmBERT-base) — ModernBERT multilingual
com tokenizer Gemma 2 (256k vocab), Flash Attention 2, RoPE, unpadding.
Escolhido sobre BERTimbau pela qualidade em PT-BR ruidoso + latência em T4.

Stack de técnicas integradas (configuráveis via CLI):
  - Weighted Cross-Entropy (lida com desbalanceamento)
  - Label Smoothing (protege contra ruído de label do Gemini)
  - Knowledge Distillation (usa confidence do Gemini como soft label; KL + T)
  - R-Drop (regularização via 2 fwd passes c/ dropouts diferentes)
  - LLRD (Layer-wise LR Decay 0.9/camada)
  - SWA (Stochastic Weight Averaging nas últimas 25% épocas)
  - fp16 em A100 tensor cores

Rodagem:
  Local smoke:  python trainer/train_v2.py --smoke
  Vertex A100:  submit_training_job.py --trainer v2 --gpu_type A100
"""

import argparse
import json
import logging
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from sklearn.metrics import (
    accuracy_score, f1_score, precision_score, recall_score,
    roc_auc_score, precision_recall_curve,
)
from torch.optim.swa_utils import AveragedModel, SWALR
from torch.utils.data import Dataset, WeightedRandomSampler
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    EarlyStoppingCallback,
    Trainer,
    TrainerCallback,
    TrainingArguments,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


DEFAULT_MODEL = "EuroBERT/EuroBERT-210m"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--train", default="training/corpus/train.parquet")
    p.add_argument("--val",   default="training/corpus/val.parquet")
    p.add_argument("--output-dir", default=os.environ.get("AIP_MODEL_DIR", "./model_v2"))
    p.add_argument("--model-name", default=DEFAULT_MODEL)
    p.add_argument("--epochs",        type=int,   default=4)
    p.add_argument("--batch-size",    type=int,   default=128)
    p.add_argument("--eval-batch-size", type=int, default=256)
    p.add_argument("--learning-rate", type=float, default=3e-5,
                   help="LR do topo (com LLRD decai layer-wise)")
    p.add_argument("--max-len",       type=int,   default=96)
    p.add_argument("--warmup-ratio",  type=float, default=0.1)
    p.add_argument("--weight-decay",  type=float, default=0.01)
    p.add_argument("--pos-weight",    type=float, default=5.0,
                   help="peso da classe positiva na CE (desbalanceamento)")
    p.add_argument("--label-smoothing", type=float, default=0.05)
    p.add_argument("--llrd-decay",    type=float, default=0.9,
                   help="fator de decay do LR por camada (0=off, 1=sem decay)")
    # Class imbalance handling
    p.add_argument("--oversample", action="store_true", default=True,
                   help="WeightedRandomSampler para batches ~50/50 pos/neg")
    p.add_argument("--oversample-ratio", type=float, default=0.5,
                   help="fracao alvo de positivos por batch (0.5 = balanceado)")
    p.add_argument("--focal-loss", action="store_true", default=True,
                   help="usa Focal Loss em vez de Weighted CE (foca em hard examples)")
    p.add_argument("--focal-gamma", type=float, default=2.0,
                   help="gamma da focal loss (maior = mais foco em hard)")
    # Knowledge distillation
    p.add_argument("--distill-alpha", type=float, default=0.5,
                   help="peso do loss KL de distillation (0=off)")
    p.add_argument("--distill-temp",  type=float, default=4.0)
    p.add_argument("--soft-label-col", default="confidence_v2",
                   help="coluna do parquet com P(is_technical) do teacher")
    # R-Drop
    p.add_argument("--rdrop-alpha",   type=float, default=1.0,
                   help="peso do KL entre 2 fwd passes (0=off)")
    # SWA
    p.add_argument("--swa", action="store_true", default=True,
                   help="usa Stochastic Weight Averaging nas últimas 25% épocas")
    p.add_argument("--swa-lr",        type=float, default=5e-6)
    # Gerais
    p.add_argument("--fp16", action="store_true", default=True)
    p.add_argument("--smoke", action="store_true",
                   help="subsample 2k linhas + 1 epoch — sanity test local")
    return p.parse_args()


class CommentDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_len, soft_labels=None):
        self.encodings = tokenizer(
            list(texts),
            truncation=True,
            padding=True,
            max_length=max_len,
            return_tensors="pt",
        )
        self.labels = list(labels)
        # soft_labels: P(is_technical=1) do teacher (Gemini). None se KD desligado.
        self.soft_labels = list(soft_labels) if soft_labels is not None else None

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        item = {k: v[idx] for k, v in self.encodings.items()}
        item["labels"] = torch.tensor(self.labels[idx], dtype=torch.long)
        if self.soft_labels is not None:
            item["soft_label"] = torch.tensor(float(self.soft_labels[idx]), dtype=torch.float)
        return item


def compute_metrics(pred):
    labels = pred.label_ids
    logits = pred.predictions
    preds  = logits.argmax(-1)
    probs_pos = torch.softmax(torch.tensor(logits), dim=-1)[:, 1].numpy()

    metrics = {
        "accuracy":  accuracy_score(labels, preds),
        "f1":        f1_score(labels, preds, average="binary", zero_division=0),
        "precision": precision_score(labels, preds, average="binary", zero_division=0),
        "recall":    recall_score(labels, preds, average="binary", zero_division=0),
    }
    if len(set(labels)) > 1:
        metrics["roc_auc"] = roc_auc_score(labels, probs_pos)
        pr, rc, _ = precision_recall_curve(labels, probs_pos)
        idx = np.argmin(np.abs(rc - 0.90))
        metrics["precision_at_recall_90"] = float(pr[idx])
    return metrics


class V2Trainer(Trainer):
    """
    Trainer com:
      - Focal Loss OU Weighted CE com Label Smoothing
      - WeightedRandomSampler (oversample positivos)
      - Knowledge Distillation (se soft_label no batch)
      - R-Drop (se rdrop_alpha > 0)
      - LLRD via create_optimizer override
    """
    def __init__(self, *args,
                 pos_weight: float = 5.0,
                 label_smoothing: float = 0.05,
                 distill_alpha: float = 0.0,
                 distill_temp: float = 4.0,
                 rdrop_alpha: float = 0.0,
                 llrd_decay: float = 1.0,
                 base_lr: float = 3e-5,
                 weight_decay: float = 0.01,
                 use_focal: bool = False,
                 focal_gamma: float = 2.0,
                 sample_weights=None,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.pos_weight = pos_weight
        self.label_smoothing = label_smoothing
        self.distill_alpha = distill_alpha
        self.distill_temp  = distill_temp
        self.rdrop_alpha   = rdrop_alpha
        self.llrd_decay    = llrd_decay
        self.base_lr       = base_lr
        self.wd            = weight_decay
        self.use_focal     = use_focal
        self.focal_gamma   = focal_gamma
        self.sample_weights = sample_weights

    def get_train_dataloader(self):
        """Override pra usar WeightedRandomSampler quando sample_weights existe."""
        if self.sample_weights is None:
            return super().get_train_dataloader()
        from torch.utils.data import DataLoader
        sampler = WeightedRandomSampler(
            weights=self.sample_weights,
            num_samples=len(self.train_dataset),
            replacement=True,
        )
        return DataLoader(
            self.train_dataset,
            batch_size=self.args.per_device_train_batch_size,
            sampler=sampler,
            num_workers=self.args.dataloader_num_workers,
            pin_memory=self.args.dataloader_pin_memory,
        )

    def _focal_loss(self, logits, labels):
        """Focal Loss binaria via softmax."""
        # CE per-sample sem reducao
        weights = torch.tensor([1.0, self.pos_weight],
                               device=logits.device, dtype=logits.dtype)
        ce_per = F.cross_entropy(
            logits, labels, weight=weights,
            label_smoothing=self.label_smoothing,
            reduction='none',
        )
        # p_t = prob predita da classe correta
        probs = F.softmax(logits, dim=-1)
        p_t = probs.gather(1, labels.unsqueeze(1)).squeeze(1).clamp(1e-6, 1.0)
        # Focal modulator: (1 - p_t)^gamma
        focal_w = (1 - p_t) ** self.focal_gamma
        return (focal_w * ce_per).mean()

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels      = inputs.pop("labels")
        soft_labels = inputs.pop("soft_label", None)

        # Forward pass 1
        outputs = model(**inputs)
        logits  = outputs.logits

        # Loss principal: Focal ou Weighted CE
        if self.use_focal:
            loss_ce = self._focal_loss(logits, labels)
            terms_key = "focal"
        else:
            weights = torch.tensor([1.0, self.pos_weight],
                                   device=logits.device, dtype=logits.dtype)
            loss_ce = F.cross_entropy(
                logits, labels, weight=weights,
                label_smoothing=self.label_smoothing,
            )
            terms_key = "ce"
        total = loss_ce
        terms = {terms_key: float(loss_ce.detach())}

        # Knowledge Distillation via KL(student || teacher)
        if soft_labels is not None and self.distill_alpha > 0:
            T = self.distill_temp
            # Teacher: [1-p, p] em duas classes
            teacher = torch.stack([1 - soft_labels, soft_labels], dim=1)
            teacher = teacher.clamp(1e-6, 1 - 1e-6)
            # Distill cross-entropy: -Σ teacher * log(softmax(logits/T))
            log_student = F.log_softmax(logits / T, dim=-1)
            loss_kd = -(teacher * log_student).sum(dim=-1).mean() * (T * T)
            total = (1 - self.distill_alpha) * total + self.distill_alpha * loss_kd
            terms["kd"] = float(loss_kd.detach())

        # R-Drop: 2nd forward + KL entre as duas distribuições
        if self.rdrop_alpha > 0:
            outputs2 = model(**inputs)
            logits2  = outputs2.logits
            loss_rd = 0.5 * (
                F.kl_div(F.log_softmax(logits,  dim=-1),
                         F.softmax(logits2, dim=-1), reduction="batchmean") +
                F.kl_div(F.log_softmax(logits2, dim=-1),
                         F.softmax(logits,  dim=-1), reduction="batchmean")
            )
            total = total + self.rdrop_alpha * loss_rd
            terms["rdrop"] = float(loss_rd.detach())

        if self.state.global_step % 200 == 0:
            logger.info(f"[step {self.state.global_step}] loss={float(total):.4f} {terms}")

        return (total, outputs) if return_outputs else total

    def create_optimizer(self):
        """Override pra habilitar Layer-wise LR Decay (LLRD)."""
        if self.optimizer is not None:
            return self.optimizer
        model = self.model
        base_lr = self.base_lr
        decay   = self.llrd_decay

        # Identifica número de layers do encoder automaticamente
        n_layers = getattr(model.config, "num_hidden_layers", 12)
        logger.info(f"LLRD: {n_layers} camadas, decay={decay}, base_lr={base_lr}")

        no_decay = ["bias", "LayerNorm.weight", "layer_norm.weight"]

        groups = []
        # Classifier head — LR = base_lr (topo)
        head_params = [(n, p) for n, p in model.named_parameters()
                       if any(k in n for k in ["classifier", "score", "head"])
                       and p.requires_grad]
        if head_params:
            groups.append({
                "params": [p for n, p in head_params if not any(nd in n for nd in no_decay)],
                "lr":     base_lr,
                "weight_decay": self.wd,
            })
            groups.append({
                "params": [p for n, p in head_params if     any(nd in n for nd in no_decay)],
                "lr":     base_lr,
                "weight_decay": 0.0,
            })

        # Encoder layers — LR = base_lr * decay^(n_layers - i)
        for i in range(n_layers):
            layer_lr = base_lr * (decay ** (n_layers - i))
            layer_params = [(n, p) for n, p in model.named_parameters()
                            if f"layer.{i}." in n or f"layers.{i}." in n]
            if not layer_params:
                continue
            groups.append({
                "params": [p for n, p in layer_params if not any(nd in n for nd in no_decay)],
                "lr":     layer_lr,
                "weight_decay": self.wd,
            })
            groups.append({
                "params": [p for n, p in layer_params if     any(nd in n for nd in no_decay)],
                "lr":     layer_lr,
                "weight_decay": 0.0,
            })

        # Embeddings — LR mínimo
        emb_lr = base_lr * (decay ** (n_layers + 1))
        emb_params = [(n, p) for n, p in model.named_parameters()
                      if any(k in n for k in ["embeddings", "embed_tokens", "wte"])
                      and p.requires_grad]
        if emb_params:
            groups.append({
                "params": [p for n, p in emb_params if not any(nd in n for nd in no_decay)],
                "lr":     emb_lr,
                "weight_decay": self.wd,
            })
            groups.append({
                "params": [p for n, p in emb_params if     any(nd in n for nd in no_decay)],
                "lr":     emb_lr,
                "weight_decay": 0.0,
            })

        # Qualquer outro parâmetro (defensivo)
        captured = set()
        for g in groups:
            captured.update(id(p) for p in g["params"])
        leftover = [(n, p) for n, p in model.named_parameters()
                    if p.requires_grad and id(p) not in captured]
        if leftover:
            logger.info(f"LLRD: {len(leftover)} params não classificados → LR base")
            groups.append({
                "params": [p for n, p in leftover],
                "lr":     base_lr,
                "weight_decay": self.wd,
            })

        self.optimizer = torch.optim.AdamW(groups, lr=base_lr)
        return self.optimizer


class SWACallback(TrainerCallback):
    """Coleta média móvel de pesos nas últimas 25% épocas."""
    def __init__(self, swa_lr: float = 5e-6):
        self.swa_lr    = swa_lr
        self.swa_model = None
        self.scheduler = None
        self.active    = False

    def on_train_begin(self, args, state, control, model=None, **kwargs):
        if model is None:
            return
        self.swa_model = AveragedModel(model)
        self.total_epochs = args.num_train_epochs
        self.swa_start = int(self.total_epochs * 0.75)
        logger.info(f"SWA ativado: inicia na época {self.swa_start}/{self.total_epochs}, swa_lr={self.swa_lr}")

    def on_epoch_end(self, args, state, control, model=None, optimizer=None, **kwargs):
        cur_epoch = int(state.epoch)
        if cur_epoch >= self.swa_start and self.swa_model is not None:
            self.swa_model.update_parameters(model)
            if not self.active:
                self.scheduler = SWALR(optimizer, swa_lr=self.swa_lr, anneal_epochs=1)
                self.active = True
                logger.info(f"[SWA] iniciando swa_scheduler na época {cur_epoch}")
            self.scheduler.step()
            logger.info(f"[SWA] peso médio atualizado época {cur_epoch}")

    def apply_final_weights(self, model):
        if self.swa_model is not None and self.active:
            model.load_state_dict(self.swa_model.module.state_dict())
            logger.info("[SWA] pesos finais aplicados ao modelo")


def main():
    args = parse_args()
    use_gpu = torch.cuda.is_available()
    logger.info(f"GPU: {use_gpu} | device: {'cuda' if use_gpu else 'cpu'}")
    if use_gpu:
        logger.info(f"  name: {torch.cuda.get_device_name(0)}")
        logger.info(f"  memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f}GB")

    # === Dados ===
    logger.info(f"Carregando train: {args.train}")
    train_df = pd.read_parquet(args.train)
    logger.info(f"Carregando val:   {args.val}")
    val_df   = pd.read_parquet(args.val)

    if args.smoke:
        train_df = train_df.sample(n=min(2000, len(train_df)), random_state=42)
        val_df   = val_df.sample(n=min(500,  len(val_df)),   random_state=42)
        args.epochs = 1
        logger.info(f"[SMOKE] train={len(train_df)}, val={len(val_df)}, epochs=1")

    logger.info(f"Train: {len(train_df):,} ({100*train_df['label'].mean():.1f}% positivos)")
    logger.info(f"Val:   {len(val_df):,} ({100*val_df['label'].mean():.1f}% positivos)")

    # Soft labels — opcional (KD). Aceita coluna 'confidence_v2' ou 'soft_label'.
    soft_tr = soft_va = None
    if args.distill_alpha > 0:
        for col in [args.soft_label_col, "soft_label"]:
            if col in train_df.columns:
                soft_tr = train_df[col].fillna(train_df["label"].astype(float)).astype(float)
                soft_va = val_df[col].fillna(val_df["label"].astype(float)).astype(float)
                logger.info(f"KD: usando coluna '{col}' como soft label (α={args.distill_alpha}, T={args.distill_temp})")
                break
        if soft_tr is None:
            logger.warning(f"Distillation pedida mas coluna '{args.soft_label_col}' não existe — KD desligado.")
            args.distill_alpha = 0.0

    # === Tokenizer & model ===
    logger.info(f"Carregando tokenizer e modelo: {args.model_name}")
    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model_name,
        num_labels=2,
        id2label={0: "nao_tecnico", 1: "tecnico"},
        label2id={"nao_tecnico": 0, "tecnico": 1},
    )

    train_ds = CommentDataset(train_df["text"], train_df["label"], tokenizer,
                              args.max_len, soft_labels=soft_tr)
    val_ds   = CommentDataset(val_df["text"],   val_df["label"],   tokenizer,
                              args.max_len, soft_labels=soft_va)

    # Sample weights para balanceamento de batch (WeightedRandomSampler)
    sample_weights = None
    if args.oversample:
        labels_arr = train_df["label"].values
        n_pos = int((labels_arr == 1).sum())
        n_neg = int((labels_arr == 0).sum())
        target_pos = args.oversample_ratio
        # peso por amostra: ajustado para que P(sortear pos) = target_pos
        w_pos = target_pos / max(n_pos, 1)
        w_neg = (1 - target_pos) / max(n_neg, 1)
        sample_weights = torch.tensor(
            [w_pos if l == 1 else w_neg for l in labels_arr],
            dtype=torch.double,
        )
        logger.info(f"Oversample: {n_pos} pos, {n_neg} neg | target={target_pos:.0%} pos por batch")

    # === Training args ===
    tmp_ckpt = Path(tempfile.mkdtemp(prefix="ckpt_v2_"))
    training_args = TrainingArguments(
        output_dir=str(tmp_ckpt),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.eval_batch_size,
        learning_rate=args.learning_rate,
        warmup_ratio=args.warmup_ratio,
        weight_decay=args.weight_decay,
        eval_strategy="steps",
        eval_steps=500,
        save_strategy="steps",
        save_steps=500,
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        save_total_limit=2,
        logging_steps=100,
        dataloader_num_workers=2 if use_gpu else 0,
        report_to="none",
        use_cpu=not use_gpu,
        fp16=args.fp16 and use_gpu,
    )

    callbacks = [EarlyStoppingCallback(early_stopping_patience=3)]
    swa_cb = None
    if args.swa:
        swa_cb = SWACallback(swa_lr=args.swa_lr)
        callbacks.append(swa_cb)

    trainer = V2Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        compute_metrics=compute_metrics,
        callbacks=callbacks,
        pos_weight=args.pos_weight,
        label_smoothing=args.label_smoothing,
        distill_alpha=args.distill_alpha,
        distill_temp=args.distill_temp,
        rdrop_alpha=args.rdrop_alpha,
        llrd_decay=args.llrd_decay,
        base_lr=args.learning_rate,
        weight_decay=args.weight_decay,
        use_focal=args.focal_loss,
        focal_gamma=args.focal_gamma,
        sample_weights=sample_weights,
    )

    logger.info("=== Iniciando treinamento ===")
    trainer.train()

    # Aplica pesos SWA no final
    if swa_cb:
        swa_cb.apply_final_weights(model)

    # === Avaliação final ===
    results = trainer.evaluate()
    logger.info("=== Resultados finais (threshold=0.5) ===")
    for k, v in results.items():
        logger.info(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")

    # === Threshold tuning no val ===
    logger.info("=== Tuning de threshold no val ===")
    pred_output = trainer.predict(val_ds)
    val_logits = pred_output.predictions
    val_labels = pred_output.label_ids
    val_probs = torch.softmax(torch.tensor(val_logits), dim=-1)[:, 1].numpy()

    best_f1 = 0.0
    best_thr_f1 = 0.5
    best_p_at_r90 = 0.0
    best_thr_p_at_r90 = 0.5
    threshold_results = []
    for thr in [round(x, 2) for x in np.arange(0.05, 0.96, 0.05)]:
        preds = (val_probs >= thr).astype(int)
        if preds.sum() == 0 or preds.sum() == len(preds):
            continue
        f1 = f1_score(val_labels, preds, zero_division=0)
        prec = precision_score(val_labels, preds, zero_division=0)
        rec = recall_score(val_labels, preds, zero_division=0)
        threshold_results.append({"thr": thr, "f1": f1, "precision": prec, "recall": rec})
        if f1 > best_f1:
            best_f1 = f1
            best_thr_f1 = thr
        if rec >= 0.90 and prec > best_p_at_r90:
            best_p_at_r90 = prec
            best_thr_p_at_r90 = thr

    logger.info(f"Best threshold (max F1):              {best_thr_f1:.2f} -> F1={best_f1:.4f}")
    logger.info(f"Best threshold (max P @ recall>=0.90): {best_thr_p_at_r90:.2f} -> P={best_p_at_r90:.4f}")
    results["best_threshold_f1"] = best_thr_f1
    results["best_f1_tuned"] = best_f1
    results["best_threshold_p_at_r90"] = best_thr_p_at_r90
    results["best_precision_at_recall_90"] = best_p_at_r90
    results["threshold_sweep"] = threshold_results

    # === Salvar ===
    final_dir = Path(args.output_dir)
    if not str(final_dir).startswith("gs://"):
        final_dir.mkdir(parents=True, exist_ok=True)
        trainer.save_model(str(final_dir))
        tokenizer.save_pretrained(str(final_dir))
        (final_dir / "metrics.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        (final_dir / "model_info.json").write_text(json.dumps({
            "model_name":      args.model_name,
            "max_len":         args.max_len,
            "epochs":          args.epochs,
            "pos_weight":      args.pos_weight,
            "label_smoothing": args.label_smoothing,
            "distill_alpha":   args.distill_alpha,
            "distill_temp":    args.distill_temp,
            "rdrop_alpha":     args.rdrop_alpha,
            "llrd_decay":      args.llrd_decay,
            "swa":             args.swa,
            "training_size":   len(train_df),
            "val_size":        len(val_df),
        }, indent=2), encoding="utf-8")
        logger.info(f"Modelo salvo em: {final_dir}")
    else:
        local_final = Path(tempfile.mkdtemp(prefix="final_v2_"))
        trainer.save_model(str(local_final))
        tokenizer.save_pretrained(str(local_final))
        (local_final / "metrics.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

        from google.cloud import storage  # type: ignore
        parts = args.output_dir.replace("gs://", "").split("/", 1)
        bucket_name, prefix = parts[0], (parts[1].rstrip("/") if len(parts) > 1 else "")
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        for f in local_final.rglob("*"):
            if f.is_file():
                rel = f.relative_to(local_final)
                blob_name = f"{prefix}/{rel}" if prefix else str(rel)
                bucket.blob(blob_name).upload_from_filename(str(f))
                logger.info(f"upload: gs://{bucket_name}/{blob_name}")
        logger.info(f"Modelo salvo em: {args.output_dir}")


if __name__ == "__main__":
    main()
