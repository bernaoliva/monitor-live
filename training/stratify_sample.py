# -*- coding: utf-8 -*-
"""
Fase 2: estratifica amostra de ~500k comentários a partir do corpus.

Estratos (prioridade — mais cedo ganha em caso de overlap):
  A. Todos os positivos (is_technical_v1=True AND NOT synthetic)
  B. Comentários ±3 min de eventos de F-surge (synthetic=True)
  C. Dismissed por admin (dismissed_by_admin=True)
  D. Random negativos — preenche o resto até o alvo, estratificado por canal+mês

Filtros aplicados:
  - Texto vazio, < 2 chars ou > 500 chars
  - Deduplicação por text.lower().strip() (mantém 1 ocorrência por texto único)
  - Exclui synthetic=True (eventos CRIA não devem virar label)

Uso:
  python training/stratify_sample.py --target 500000
  python training/stratify_sample.py --in training/corpus/corpus.parquet --out training/corpus/sample_500k.parquet
"""

import argparse
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


RANDOM_SEED = 42
SURGE_NEIGHBOR_MINUTES = 3  # ±3 min em torno do evento de F-surge


def parse_ts_minute(ts: str) -> str:
    """Extrai chave de minuto YYYY-MM-DDTHH:mm do timestamp ISO."""
    if not ts or len(ts) < 16:
        return ""
    return ts[:16]


def minute_add(minute_key: str, delta: int) -> str:
    """Soma N minutos a uma chave YYYY-MM-DDTHH:mm."""
    try:
        dt = datetime.strptime(minute_key, "%Y-%m-%dT%H:%M")
        return (dt + timedelta(minutes=delta)).strftime("%Y-%m-%dT%H:%M")
    except ValueError:
        return minute_key


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in",  dest="inp", default="training/corpus/corpus.parquet")
    ap.add_argument("--out", default="training/corpus/sample_500k.parquet")
    ap.add_argument("--target", type=int, default=500_000,
                    help="tamanho alvo da amostra final")
    ap.add_argument("--min-chars", type=int, default=2)
    ap.add_argument("--max-chars", type=int, default=500)
    args = ap.parse_args()

    random.seed(RANDOM_SEED)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Carregando {args.inp}...")
    df = pq.read_table(args.inp).to_pandas()
    print(f"  {len(df):,} linhas brutas")

    # === Filtros de qualidade ===
    before = len(df)
    df = df[df["text"].notna()]
    df["text_norm"] = df["text"].str.strip()
    mask_len = (df["text_norm"].str.len() >= args.min_chars) & (df["text_norm"].str.len() <= args.max_chars)
    df = df[mask_len]
    print(f"  após filtro de tamanho: {len(df):,} ({before-len(df):,} removidos)")

    # === Deduplicação por texto normalizado ===
    before = len(df)
    df["text_key"] = df["text_norm"].str.lower()
    # Em caso de duplicata, preferir comentários com label técnico (fonte mais valiosa)
    df = df.sort_values(["is_technical_v1"], ascending=False).drop_duplicates("text_key", keep="first")
    print(f"  após dedup: {len(df):,} ({before-len(df):,} removidos)")

    # === Identificar minutos de F-surge ===
    synthetic = df[df["synthetic"] == True]
    print(f"  eventos de F-surge: {len(synthetic)}")
    surge_minutes = set()
    for _, row in synthetic.iterrows():
        base = parse_ts_minute(row["ts"] or "")
        if not base:
            continue
        for d in range(-SURGE_NEIGHBOR_MINUTES, SURGE_NEIGHBOR_MINUTES + 1):
            surge_minutes.add((row["video_id"], minute_add(base, d)))
    print(f"  minutos marcados como surge-neighbor: {len(surge_minutes):,}")

    # === Excluir synthetic do corpus principal ===
    df = df[df["synthetic"] == False].copy()

    # === Classificar por estrato ===
    df["minute_key"] = df["ts"].astype(str).str[:16]
    df["is_surge_neighbor"] = df.apply(
        lambda r: (r["video_id"], r["minute_key"]) in surge_minutes, axis=1
    )
    df["live_month"] = df["live_started_at"].astype(str).str[:7]

    def classify_stratum(row):
        if row["is_technical_v1"]:
            return "A_positive"
        if row["dismissed_by_admin"]:
            return "C_dismissed"
        if row["is_surge_neighbor"]:
            return "B_surge_neighbor"
        return "D_negative"

    df["stratum"] = df.apply(classify_stratum, axis=1)
    print("\nDistribuição por estrato (antes do sampling):")
    print(df["stratum"].value_counts().to_string())

    # === Sampling por estrato ===
    # A: todos
    # B: todos
    # C: todos
    # D: random até fechar o alvo, stratified por (channel, live_month)
    pieces = []
    for stratum in ["A_positive", "C_dismissed", "B_surge_neighbor"]:
        piece = df[df["stratum"] == stratum].copy()
        pieces.append(piece)
        print(f"  [{stratum}] mantém todos: {len(piece):,}")

    taken = sum(len(p) for p in pieces)
    remaining = max(0, args.target - taken)

    neg_pool = df[df["stratum"] == "D_negative"].copy()
    if remaining > 0 and len(neg_pool) > 0:
        # Stratified sample por (channel, live_month) — distribui proporcionalmente
        neg_pool["strat_key"] = neg_pool["channel"].fillna("UNKNOWN") + "|" + neg_pool["live_month"].fillna("UNKNOWN")
        n_neg = min(remaining, len(neg_pool))
        # amostragem estratificada: mantém proporção por strat_key
        sampled = (
            neg_pool.groupby("strat_key", group_keys=False)
            .apply(lambda g: g.sample(
                n=max(1, int(round(n_neg * len(g) / len(neg_pool)))),
                random_state=RANDOM_SEED,
            ))
        )
        # Ajusta: pode ter pegado um pouco a mais/menos pelo arredondamento
        if len(sampled) > n_neg:
            sampled = sampled.sample(n=n_neg, random_state=RANDOM_SEED)
        elif len(sampled) < n_neg:
            extra_needed = n_neg - len(sampled)
            leftover = neg_pool[~neg_pool.index.isin(sampled.index)]
            if len(leftover) > 0:
                extra = leftover.sample(n=min(extra_needed, len(leftover)), random_state=RANDOM_SEED)
                sampled = pd.concat([sampled, extra])
        pieces.append(sampled)
        print(f"  [D_negative]   amostrado: {len(sampled):,} (pool: {len(neg_pool):,})")
    else:
        print(f"  [D_negative]   skip (já atingimos o alvo ou pool vazio)")

    final = pd.concat(pieces, ignore_index=True)
    final = final.sample(frac=1, random_state=RANDOM_SEED).reset_index(drop=True)

    print(f"\nAmostra final: {len(final):,} linhas")
    print("\nDistribuição final por estrato:")
    print(final["stratum"].value_counts().to_string())
    print("\nDistribuição por canal:")
    print(final["channel"].value_counts().to_string())
    print(f"\nPositivos na amostra: {final['is_technical_v1'].sum():,} "
          f"({100*final['is_technical_v1'].mean():.1f}%)")

    # Remove colunas auxiliares antes de salvar
    drop_cols = ["text_norm", "text_key", "minute_key", "is_surge_neighbor", "live_month"]
    final = final.drop(columns=[c for c in drop_cols if c in final.columns])

    final.to_parquet(out_path, compression="zstd", index=False)
    print(f"\nSalvo em: {out_path} ({out_path.stat().st_size / 1024 / 1024:.1f} MB)")

    # Stats
    stats = {
        "total":            len(final),
        "target":           args.target,
        "positives":        int(final["is_technical_v1"].sum()),
        "by_stratum":       final["stratum"].value_counts().to_dict(),
        "by_channel":       final["channel"].value_counts().to_dict(),
    }
    stats_path = out_path.with_name(out_path.stem + "_stats.json")
    stats_path.write_text(json.dumps(stats, indent=2, default=str), encoding="utf-8")
    print(f"Stats: {stats_path}")


if __name__ == "__main__":
    main()
