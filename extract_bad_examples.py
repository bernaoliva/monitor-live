# -*- coding: utf-8 -*-
"""
Extrai dados de analise do Firestore para CSV/Parquet local.

Saida 1: bad_examples.csv
  Falsos positivos marcados pelo admin via dismiss no dashboard.
  Coluna 'classification_method' diz QUEM decidiu ser tecnico (modelo, regex, etc).

Saida 2: classified_comments_sample.csv
  Amostra de comentarios classificados com 'classification_method' = keyword_override.
  Mostra todos os casos onde a regex de fallback "salvou" o modelo (= o modelo
  errou ao dizer NAO, mas a regex forcou positivo).

Uso:
  python extract_bad_examples.py
  python extract_bad_examples.py --since 2026-04-01
  python extract_bad_examples.py --method keyword_override --max 5000
"""
import argparse
import csv
from datetime import datetime
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore


def init_firestore():
    cred_path = "firebase-credentials.json"
    if not Path(cred_path).exists():
        print(f"ERRO: {cred_path} nao encontrado.")
        print("Baixe a chave de servico do Firebase Console e salve neste diretorio.")
        raise SystemExit(1)
    cred = credentials.Certificate(cred_path)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()


def export_bad_examples(db, output: str = "bad_examples.csv"):
    """Exporta a colecao bad_examples (FPs marcados via dashboard)."""
    print(f"\n=== bad_examples (falsos positivos do admin) ===")
    docs = list(db.collection("bad_examples").stream())
    print(f"Total: {len(docs)} documentos")
    if not docs:
        print("(nenhum admin marcou FP ainda)")
        return

    rows = []
    for d in docs:
        data = d.to_dict()
        data["_doc_id"] = d.id
        rows.append(data)

    cols = [
        "_doc_id", "comment_id", "text", "author", "ts",
        "video_id", "channel", "live_title",
        "original_category", "original_issue", "original_severity",
        "model_confidence", "classification_method", "model_version",
        "dismissed_at", "dismissed_by",
    ]
    with open(output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            # Converte timestamps Firestore para string
            for k, v in list(r.items()):
                if hasattr(v, "isoformat"):
                    r[k] = v.isoformat()
            w.writerow(r)
    print(f"Salvo: {output}")

    # Stats por classification_method
    by_method = {}
    for r in rows:
        k = r.get("classification_method") or "unknown"
        by_method[k] = by_method.get(k, 0) + 1
    print("\nPor classification_method (= quem disse FP era tecnico):")
    for k, n in sorted(by_method.items(), key=lambda x: -x[1]):
        print(f"  {k:25s} {n:5d}")


def export_method_samples(db, method: str, max_lives: int = 100, max_per_live: int = 200,
                          since: str = None, output: str = None):
    """Exporta comentarios reais com um classification_method especifico, todas as lives."""
    output = output or f"comments_method_{method}.csv"
    print(f"\n=== Comentarios com classification_method='{method}' ===")
    print(f"(scaneando ate {max_lives} lives, {max_per_live} comments/live)")

    lives_q = db.collection("lives").order_by("started_at",
                                              direction=firestore.Query.DESCENDING).limit(max_lives)
    if since:
        lives_q = db.collection("lives").where("started_at", ">=", since).limit(max_lives)

    rows = []
    n_lives_scaneadas = 0
    for live_doc in lives_q.stream():
        n_lives_scaneadas += 1
        live = live_doc.to_dict()
        comments_q = (
            live_doc.reference.collection("comments")
            .where("classification_method", "==", method)
            .limit(max_per_live)
        )
        for c_doc in comments_q.stream():
            c = c_doc.to_dict()
            rows.append({
                "comment_id":            c_doc.id,
                "video_id":              live_doc.id,
                "channel":               live.get("channel"),
                "live_title":            live.get("title"),
                "live_started_at":       live.get("started_at"),
                "text":                  c.get("text"),
                "author":                c.get("author"),
                "ts":                    c.get("ts"),
                "is_technical":          c.get("is_technical"),
                "category":              c.get("category"),
                "issue":                 c.get("issue"),
                "severity":              c.get("severity"),
                "model_confidence":      c.get("model_confidence"),
                "classification_method": c.get("classification_method"),
                "model_version":         c.get("model_version"),
                "dismissed_by_admin":    c.get("dismissed_by_admin", False),
            })
            if len(rows) % 500 == 0:
                print(f"  ... {len(rows)} comentarios encontrados")

    print(f"Lives scaneadas: {n_lives_scaneadas}")
    print(f"Total comentarios com {method}: {len(rows)}")

    if not rows:
        print("(nenhum comentario com esse method)")
        return

    cols = list(rows[0].keys())
    with open(output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            for k, v in list(r.items()):
                if hasattr(v, "isoformat"):
                    r[k] = v.isoformat()
            w.writerow(r)
    print(f"Salvo: {output}")

    # Stats: quantos foram dismissed?
    dismissed = sum(1 for r in rows if r.get("dismissed_by_admin"))
    print(f"\nDestes, marcados como FP pelo admin (dismissed): {dismissed} ({100*dismissed/len(rows):.1f}%)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", default=None,
                    help="Extrair amostras com este classification_method (ex: keyword_override)")
    ap.add_argument("--max-lives", type=int, default=100,
                    help="Quantas lives recentes scanear")
    ap.add_argument("--max-per-live", type=int, default=200,
                    help="Quantos comments por live")
    ap.add_argument("--since", default=None,
                    help="Filtrar lives a partir desta data (YYYY-MM-DD)")
    ap.add_argument("--skip-bad-examples", action="store_true",
                    help="Pular export da colecao bad_examples")
    args = ap.parse_args()

    db = init_firestore()
    print(f"Firestore conectado em {datetime.now().isoformat()}")

    if not args.skip_bad_examples:
        export_bad_examples(db)

    if args.method:
        export_method_samples(db, args.method, args.max_lives, args.max_per_live,
                              since=args.since)
    else:
        print("\n[dica] use --method keyword_override para ver casos onde o regex 'salvou' o modelo")
        print("       use --method confidence_threshold para ver casos onde o modelo foi descartado")
        print("       use --method model para ver as decisoes puras do modelo")


if __name__ == "__main__":
    main()
