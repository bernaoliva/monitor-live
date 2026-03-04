# -*- coding: utf-8 -*-
"""
Exporta comentários do Firestore → CSV para retreino do modelo.

Conecta ao Firestore usando firebase-credentials.json local,
itera por todas as lives e exporta todos os comentários com metadados.

Saída: real_comments_raw.csv
"""

import csv
import os
import sys
import time

import firebase_admin
from firebase_admin import credentials as fb_credentials, firestore as fb_firestore


def get_firestore():
    cred_path = os.environ.get("FIREBASE_CREDENTIALS", "firebase-credentials.json")
    abs_cred = os.path.abspath(cred_path)
    if not os.path.exists(abs_cred):
        print(f"ERRO: credenciais não encontradas em {abs_cred}")
        sys.exit(1)
    db_id = os.environ.get("FIRESTORE_DATABASE", "(default)")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(fb_credentials.Certificate(abs_cred))
    return fb_firestore.client(database_id=db_id)


def get_all_live_ids(fs, retries=3):
    """Busca todos os IDs de lives com retry."""
    for attempt in range(retries):
        try:
            docs = list(fs.collection("lives").stream())
            return [(d.id, (d.to_dict() or {}).get("status", "unknown")) for d in docs]
        except Exception as e:
            if attempt < retries - 1:
                print(f"    [retry {attempt+1}] erro ao listar lives: {e}")
                time.sleep(2 ** attempt)
            else:
                raise


def extract_comments_from_live(fs, video_id, retries=3):
    """Extrai comentários de uma live com retry."""
    for attempt in range(retries):
        try:
            comments_ref = fs.collection("lives").document(video_id).collection("comments")
            result = []
            for comment_doc in comments_ref.stream():
                data = comment_doc.to_dict()
                text = (data.get("text") or "").strip()
                if not text:
                    continue
                result.append({
                    "text": text,
                    "current_label": 1 if data.get("is_technical") else 0,
                    "category": data.get("category") or "",
                    "issue": data.get("issue") or "",
                    "severity": data.get("severity") or "none",
                    "dismissed": 1 if data.get("dismissed") else 0,
                    "video_id": video_id,
                    "ts": data.get("ts") or "",
                    "author": data.get("author") or "",
                })
            return result
        except Exception as e:
            if attempt < retries - 1:
                print(f"    [retry {attempt+1}] {e}")
                time.sleep(2 ** attempt)
            else:
                print(f"    [FALHOU] {video_id}: {e}")
                return []


def extract_all_comments(fs):
    """Itera por todas as lives e extrai comentários."""
    print("  Listando lives...", flush=True)
    lives = get_all_live_ids(fs)
    print(f"  {len(lives)} lives encontradas")

    all_comments = []
    for video_id, status in lives:
        print(f"  Live {video_id} ({status}) ...", end=" ", flush=True)
        comments = extract_comments_from_live(fs, video_id)
        all_comments.extend(comments)
        print(f"{len(comments)} comentários")

    return all_comments


def deduplicate(comments):
    """Deduplica por texto (mantém primeiro encontrado)."""
    seen = set()
    unique = []
    for c in comments:
        key = c["text"].strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def save_csv(comments, path):
    fieldnames = ["text", "current_label", "category", "issue", "severity",
                  "dismissed", "video_id", "ts", "author"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in comments:
            writer.writerow(c)


def main():
    print("Conectando ao Firestore...")
    fs = get_firestore()

    print("Extraindo comentários de todas as lives...")
    comments = extract_all_comments(fs)
    print(f"\nTotal bruto: {len(comments)} comentários")

    # Estatísticas antes de dedup
    tech = sum(1 for c in comments if c["current_label"] == 1)
    dismissed = sum(1 for c in comments if c["dismissed"] == 1)
    print(f"  Técnicos (label atual): {tech}")
    print(f"  Dismissed: {dismissed}")

    # Deduplicar
    unique = deduplicate(comments)
    print(f"\nApós deduplicação: {len(unique)} comentários únicos")

    tech_u = sum(1 for c in unique if c["current_label"] == 1)
    print(f"  Técnicos únicos: {tech_u}")
    print(f"  Normais únicos: {len(unique) - tech_u}")

    out_path = "real_comments_raw.csv"
    save_csv(unique, out_path)
    print(f"\nSalvo em: {out_path}")


if __name__ == "__main__":
    main()
