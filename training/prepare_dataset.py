# -*- coding: utf-8 -*-
"""
Fase 4: prepara dataset final para treino do BERTimbau.

A partir do labeled_500k.parquet:
  1. Reserva 2000 comentários estratificados como test_gold (revisão humana)
  2. Split dos restantes em train (85%) / val (15%), estratificado
  3. Mapeia category_v2/severity_v2 para índices inteiros (multi-task ready)
  4. Opcionalmente aplica augmentation leve nos positivos
  5. Salva train.parquet, val.parquet, test_gold.parquet + test_gold_review.csv

Uso:
  python training/prepare_dataset.py
  python training/prepare_dataset.py --gold-size 2000 --augment
"""

import argparse
import json
import random
import re
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split


RANDOM_SEED = 42

CATEGORY_LABELS = ["NONE", "AUDIO", "VIDEO", "REDE", "SINC", "GC", "OUTROS"]
CATEGORY_TO_ID  = {c: i for i, c in enumerate(CATEGORY_LABELS)}

SEVERITY_LABELS = ["none", "low", "medium", "high"]
SEVERITY_TO_ID  = {s: i for i, s in enumerate(SEVERITY_LABELS)}


def augment_text(text: str) -> list[str]:
    """Gera variantes leves de um texto positivo."""
    variants = []

    # upper / lower / capitalize
    if text != text.lower():
        variants.append(text.lower())
    if text != text.upper():
        variants.append(text.upper())

    # sem pontuação
    no_punct = re.sub(r"[.,!?;:\-_/\\]+", "", text).strip()
    if no_punct and no_punct != text:
        variants.append(no_punct)

    # swap de 2 chars adjacentes (simula typo) — apenas em texto > 5 chars
    if len(text) > 5:
        rng = random.Random(hash(text) & 0xFFFF)
        i = rng.randint(1, len(text) - 3)
        typo = text[:i] + text[i+1] + text[i] + text[i+2:]
        variants.append(typo)

    return variants


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in",  dest="inp", default="training/corpus/labeled_500k.parquet")
    ap.add_argument("--out-dir", default="training/corpus")
    ap.add_argument("--gold-size", type=int, default=2000,
                    help="tamanho do test_gold set (revisão humana)")
    ap.add_argument("--val-frac", type=float, default=0.15)
    ap.add_argument("--augment", action="store_true",
                    help="aplica augmentation leve nos positivos")
    args = ap.parse_args()

    random.seed(RANDOM_SEED)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Carregando {args.inp}...")
    df = pd.read_parquet(args.inp)
    print(f"  {len(df):,} linhas")

    # Precisa ter labels v2 válidos (sem erro de API)
    has_label = df["is_technical_v2"].notna() & df["category_v2"].notna() & df["severity_v2"].notna()
    dropped = (~has_label).sum()
    if dropped > 0:
        print(f"  descartando {dropped:,} linhas sem label válido")
        df = df[has_label].reset_index(drop=True)

    # === Normalização: category_v2 e severity_v2 → IDs inteiros ===
    df["category_id"] = df["category_v2"].map(lambda c: CATEGORY_TO_ID.get(str(c), CATEGORY_TO_ID["NONE"]))
    df["severity_id"] = df["severity_v2"].map(lambda s: SEVERITY_TO_ID.get(str(s), SEVERITY_TO_ID["none"]))
    df["label"]       = df["is_technical_v2"].astype(int)

    print("\nDistribuição final:")
    print(f"  positivos (is_technical_v2): {df['label'].sum():,} ({100*df['label'].mean():.1f}%)")
    print(f"  por categoria:")
    print(df["category_v2"].value_counts().to_string())
    print(f"  por severidade:")
    print(df["severity_v2"].value_counts().to_string())

    # === 1. Test gold set — estratificado por categoria + positivos em excesso ===
    # Queremos diversidade: todas as categorias representadas
    gold_pieces = []
    per_category_target = max(1, args.gold_size // (len(CATEGORY_LABELS) * 2))
    for cat in CATEGORY_LABELS:
        cat_df = df[df["category_v2"] == cat]
        if len(cat_df) == 0:
            continue
        n = min(per_category_target, len(cat_df))
        gold_pieces.append(cat_df.sample(n=n, random_state=RANDOM_SEED))

    gold = pd.concat(gold_pieces).drop_duplicates("comment_id")

    # Completa com positivos até atingir o alvo
    deficit = args.gold_size - len(gold)
    if deficit > 0:
        pool = df[~df["comment_id"].isin(gold["comment_id"])]
        extras = pool[pool["label"] == 1].sample(
            n=min(deficit // 2, pool[pool["label"] == 1].shape[0]),
            random_state=RANDOM_SEED,
        )
        gold = pd.concat([gold, extras])
        deficit = args.gold_size - len(gold)

    # Completa o resto com random
    if deficit > 0:
        pool = df[~df["comment_id"].isin(gold["comment_id"])]
        extras = pool.sample(n=min(deficit, len(pool)), random_state=RANDOM_SEED)
        gold = pd.concat([gold, extras])

    gold = gold.sample(frac=1, random_state=RANDOM_SEED).reset_index(drop=True)
    print(f"\nTest gold: {len(gold):,} (alvo: {args.gold_size})")

    # Remove gold do pool de treino/val
    trainval = df[~df["comment_id"].isin(gold["comment_id"])].reset_index(drop=True)

    # === 2. Train/Val split estratificado por (label x category) ===
    # Garante que val tenha amostras de cada categoria (GC/OUTROS/SINC sao raras)
    cat_counts = trainval.groupby(["label", "category_v2"]).size()
    rare_buckets = set(
        (lbl, cat) for (lbl, cat), n in cat_counts.items() if n < 4
    )
    def make_strat(row):
        if (row["label"], row["category_v2"]) in rare_buckets:
            return f"{row['label']}|RARE"
        return f"{row['label']}|{row['category_v2']}"
    trainval["strat_key"] = trainval.apply(make_strat, axis=1)

    train_df, val_df = train_test_split(
        trainval,
        test_size=args.val_frac,
        random_state=RANDOM_SEED,
        stratify=trainval["strat_key"],
    )
    train_df = train_df.drop(columns=["strat_key"]).reset_index(drop=True)
    val_df   = val_df.drop(columns=["strat_key"]).reset_index(drop=True)

    print("\nVal por categoria (positivos):")
    val_pos = val_df[val_df["label"] == 1]
    print(val_pos["category_v2"].value_counts().to_string())

    print(f"\nTrain: {len(train_df):,} ({100*train_df['label'].mean():.1f}% positivos)")
    print(f"Val:   {len(val_df):,} ({100*val_df['label'].mean():.1f}% positivos)")
    print(f"Test gold: {len(gold):,} ({100*gold['label'].mean():.1f}% positivos)")

    # === 3. Augmentation (opcional, só no train, só nos positivos) ===
    if args.augment:
        positives = train_df[train_df["label"] == 1]
        print(f"\nAugmentation: {len(positives):,} positivos -> gerando variantes...")
        aug_rows = []
        for _, row in positives.iterrows():
            for variant in augment_text(row["text"]):
                new = row.copy()
                new["text"] = variant
                new["comment_id"] = row["comment_id"] + "_aug" + str(hash(variant) & 0xFFFF)
                aug_rows.append(new)
        aug_df = pd.DataFrame(aug_rows)
        train_df = pd.concat([train_df, aug_df], ignore_index=True)
        train_df = train_df.sample(frac=1, random_state=RANDOM_SEED).reset_index(drop=True)
        print(f"Train após augmentation: {len(train_df):,} ({100*train_df['label'].mean():.1f}% positivos)")

    # === 4. Salvar ===
    keep_cols = [
        "comment_id", "text", "label", "category_id", "severity_id",
        "is_technical_v2", "category_v2", "severity_v2", "issue_v2", "confidence_v2",
        "is_technical_v1", "category_v1", "severity_v1",
        "channel", "video_id", "stratum",
    ]
    keep_cols = [c for c in keep_cols if c in train_df.columns]

    train_out = out_dir / "train.parquet"
    val_out   = out_dir / "val.parquet"
    gold_out  = out_dir / "test_gold.parquet"
    gold_csv  = out_dir / "test_gold_review.csv"

    train_df[keep_cols].to_parquet(train_out, compression="zstd", index=False)
    val_df[keep_cols].to_parquet(val_out, compression="zstd", index=False)
    gold[keep_cols].to_parquet(gold_out, compression="zstd", index=False)

    # CSV amigável para revisão humana (só colunas relevantes + coluna vazia pro humano)
    review_cols = ["comment_id", "text", "channel",
                   "is_technical_v2", "category_v2", "severity_v2", "issue_v2",
                   "is_technical_v1", "category_v1", "severity_v1"]
    gold_review = gold[[c for c in review_cols if c in gold.columns]].copy()
    # Colunas pro humano preencher — ficam vazias
    gold_review["HUMAN_is_technical"] = ""
    gold_review["HUMAN_category"]     = ""
    gold_review["HUMAN_severity"]     = ""
    gold_review["HUMAN_notes"]        = ""
    gold_review.to_csv(gold_csv, index=False, encoding="utf-8")
    print(f"\n[REVISAO MANUAL]: abrir {gold_csv} e preencher colunas HUMAN_* nos 2k exemplos.")
    print(f"   Isso e o unico ground truth pro val/test - investir ~1-2h aqui e critico.")

    print(f"\nSalvos:")
    print(f"  {train_out}  ({train_out.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"  {val_out}    ({val_out.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"  {gold_out}   ({gold_out.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"  {gold_csv}   (revisão humana)")

    stats = {
        "train":     int(len(train_df)),
        "val":       int(len(val_df)),
        "test_gold": int(len(gold)),
        "train_positives": int(train_df["label"].sum()),
        "val_positives":   int(val_df["label"].sum()),
        "gold_positives":  int(gold["label"].sum()),
        "category_labels": CATEGORY_LABELS,
        "severity_labels": SEVERITY_LABELS,
    }
    (out_dir / "dataset_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
