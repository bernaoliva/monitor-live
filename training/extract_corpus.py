# -*- coding: utf-8 -*-
"""
Fase 1 do re-treino: dump completo do Firestore para Parquet.

Para cada live em lives/, percorre a subcoleção comments/ e grava um parquet
com metadata da live + todos os campos do comentário (velhos + novos da Fase 0).

Saídas:
  training/corpus/corpus.parquet  — 2M linhas, ~400MB
  training/corpus/stats.json      — contagens por channel / is_technical / method

Uso:
  python training/extract_corpus.py
  python training/extract_corpus.py --out training/corpus --resume

Dependências: firebase-admin, pandas, pyarrow.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Iterator, Optional

import firebase_admin
import pyarrow as pa
import pyarrow.parquet as pq
from firebase_admin import credentials as fb_credentials, firestore as fb_firestore


# Campos que vamos extrair por comentário
SCHEMA = pa.schema([
    ("video_id",              pa.string()),
    ("comment_id",            pa.string()),
    ("channel",               pa.string()),
    ("live_title",            pa.string()),
    ("live_started_at",       pa.string()),
    ("live_ended_at",         pa.string()),
    ("live_status",           pa.string()),
    ("live_total_comments",   pa.int64()),
    ("live_concurrent_viewers", pa.int64()),
    # Campos do comentário
    ("author",                pa.string()),
    ("text",                  pa.string()),
    ("ts",                    pa.string()),
    # Labels do modelo v1 (atual)
    ("is_technical_v1",       pa.bool_()),
    ("category_v1",           pa.string()),
    ("issue_v1",              pa.string()),
    ("severity_v1",           pa.string()),
    # Telemetria Fase 0 (só presente em comentários novos)
    ("model_confidence",      pa.float64()),
    ("classification_method", pa.string()),
    ("model_version",         pa.string()),
    ("dismissed_by_admin",    pa.bool_()),
    # Flags
    ("synthetic",             pa.bool_()),
])


def get_firestore():
    cred_path = os.environ.get("FIREBASE_CREDENTIALS", "firebase-credentials.json")
    abs_cred = os.path.abspath(cred_path)
    if not os.path.exists(abs_cred):
        print(f"ERRO: credenciais não encontradas em {abs_cred}", file=sys.stderr)
        sys.exit(1)
    db_id = os.environ.get("FIRESTORE_DATABASE", "(default)")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(fb_credentials.Certificate(abs_cred))
    return fb_firestore.client(database_id=db_id)


def _as_int(v) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _as_bool(v) -> bool:
    return bool(v) if v is not None else False


def _as_str(v) -> Optional[str]:
    if v is None:
        return None
    return str(v)


def iter_comments(fs, live_id: str, live_meta: dict) -> Iterator[dict]:
    """Stream comentários de uma live como dicts já no schema final."""
    comments_ref = fs.collection("lives").document(live_id).collection("comments")
    for doc in comments_ref.stream():
        d = doc.to_dict() or {}
        text = (d.get("text") or "").strip()
        if not text:
            continue
        yield {
            "video_id":               live_id,
            "comment_id":             doc.id,
            "channel":                live_meta.get("channel"),
            "live_title":             live_meta.get("title"),
            "live_started_at":        live_meta.get("started_at"),
            "live_ended_at":          live_meta.get("ended_at"),
            "live_status":            live_meta.get("status"),
            "live_total_comments":    _as_int(live_meta.get("total_comments")),
            "live_concurrent_viewers": _as_int(live_meta.get("concurrent_viewers")),
            "author":                 _as_str(d.get("author")),
            "text":                   text,
            "ts":                     _as_str(d.get("ts")),
            "is_technical_v1":        _as_bool(d.get("is_technical")),
            "category_v1":            _as_str(d.get("category")),
            "issue_v1":               _as_str(d.get("issue")),
            "severity_v1":            _as_str(d.get("severity") or "none"),
            "model_confidence":       d.get("model_confidence"),
            "classification_method":  _as_str(d.get("classification_method")),
            "model_version":          _as_str(d.get("model_version")),
            "dismissed_by_admin":     _as_bool(d.get("dismissed_by_admin")),
            "synthetic":              _as_bool(d.get("synthetic")),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="training/corpus", help="diretório de saída")
    ap.add_argument("--chunk-rows", type=int, default=50_000,
                    help="linhas por chunk escrito no parquet")
    ap.add_argument("--resume", action="store_true",
                    help="pula lives já processadas (lista em processed.txt)")
    ap.add_argument("--max-lives", type=int, default=0,
                    help="limita N primeiras lives (smoke test; 0 = todas)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = out_dir / "corpus.parquet"
    stats_path   = out_dir / "stats.json"
    processed_path = out_dir / "processed.txt"

    # Resume: carrega IDs já processados
    processed_ids = set()
    if args.resume and processed_path.exists():
        processed_ids = set(processed_path.read_text(encoding="utf-8").split())
        print(f"[resume] pulando {len(processed_ids)} lives já processadas")

    print("Conectando ao Firestore...")
    fs = get_firestore()

    print("Listando todas as lives...")
    t0 = time.time()
    live_docs = list(fs.collection("lives").stream())
    print(f"  {len(live_docs)} lives em {time.time()-t0:.1f}s")
    if args.max_lives > 0:
        live_docs = live_docs[:args.max_lives]
        print(f"  [--max-lives] limitando a {len(live_docs)} lives")

    # Writer parquet único, acumula chunks
    writer = pq.ParquetWriter(parquet_path, SCHEMA, compression="zstd")
    total_rows = 0
    total_tech = 0
    per_channel: dict = {}
    per_method: dict = {}

    buffer: list = []
    t_start = time.time()

    def _flush():
        nonlocal buffer, total_rows
        if not buffer:
            return
        table = pa.Table.from_pylist(buffer, schema=SCHEMA)
        writer.write_table(table)
        total_rows += len(buffer)
        buffer = []

    try:
        for idx, live_doc in enumerate(live_docs, start=1):
            if live_doc.id in processed_ids:
                continue
            live_meta = live_doc.to_dict() or {}

            t_live = time.time()
            n_before = total_rows + len(buffer)
            for row in iter_comments(fs, live_doc.id, live_meta):
                buffer.append(row)
                if row["is_technical_v1"]:
                    total_tech += 1
                ch = row["channel"] or "UNKNOWN"
                per_channel[ch] = per_channel.get(ch, 0) + 1
                m = row["classification_method"] or "legacy"
                per_method[m] = per_method.get(m, 0) + 1
                if len(buffer) >= args.chunk_rows:
                    _flush()
            n_live = (total_rows + len(buffer)) - n_before

            # Marca live como processada
            with processed_path.open("a", encoding="utf-8") as f:
                f.write(live_doc.id + "\n")

            dt = time.time() - t_live
            elapsed = time.time() - t_start
            rate = (total_rows + len(buffer)) / max(elapsed, 1)
            print(f"  [{idx}/{len(live_docs)}] {live_doc.id} "
                  f"({live_meta.get('channel') or '?'}) "
                  f"{n_live} comentários em {dt:.1f}s "
                  f"— total {total_rows + len(buffer):,} ({rate:.0f}/s)")

        _flush()
    finally:
        writer.close()

    # Stats
    stats = {
        "total_rows":            total_rows,
        "total_technical_v1":    total_tech,
        "total_lives":           len(live_docs),
        "per_channel":           per_channel,
        "per_classification_method": per_method,
        "elapsed_seconds":       time.time() - t_start,
        "parquet_path":          str(parquet_path),
        "parquet_size_mb":       round(parquet_path.stat().st_size / 1024 / 1024, 2),
    }
    stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"DONE: {total_rows:,} comentários em {stats['elapsed_seconds']:.0f}s")
    print(f"Técnicos (v1): {total_tech:,} ({100*total_tech/max(total_rows,1):.1f}%)")
    print(f"Parquet: {parquet_path} ({stats['parquet_size_mb']} MB)")
    print(f"Stats:   {stats_path}")


if __name__ == "__main__":
    main()
