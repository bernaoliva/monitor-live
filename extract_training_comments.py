# -*- coding: utf-8 -*-
"""
Extrai comentarios reais do Firestore para retreino do DistilBERT.

Faz amostragem inteligente de uma live especifica:
  - ~500 candidatos tecnicos (contem palavras ambiguas)
  - ~1500 negativos aleatorios (comentarios normais)

Saida: training/real_comments_raw.csv

Uso:
  python extract_training_comments.py
  python extract_training_comments.py --video_id V580YrkHCB8 --tech_sample 500 --neg_sample 1500
  python extract_training_comments.py --all_lives   # extrai de todas as lives
"""

import argparse
import csv
import os
import random
import re
import sys

import firebase_admin
from firebase_admin import credentials as fb_credentials, firestore as fb_firestore

random.seed(42)

# ─── PALAVRAS AMBIGUAS ────────────────────────────────────────────────────────
# Palavras que podem indicar problema tecnico MAS tambem aparecem em contexto
# de jogo/torcida. Queremos exemplos reais dessas para o modelo aprender.
_AMBIGUOUS_WORDS = re.compile(
    r"\b("
    r"delay|atraso|atrasad[ao]|adiantad[ao]"
    r"|sinal|sem sinal|sinal caiu"
    r"|lag\b|lagand[ao]|lagou|laga"
    r"|trav[oaeu]\w*|congelou|congeland[ao]|congelad[ao]"
    r"|caiu|cai[ur]|ca[ií]nd[ao]"
    r"|cortou|cortand[ao]"
    r"|som\b|audio|áudio"
    r"|tela\b|tela preta|black ?screen"
    r"|quebrou|bugou|bug\b|bugad[ao]"
    r"|pixelou|pixeland[ao]|pixelad[ao]"
    r"|buffer\w*|carregand[ao]|loading"
    r"|travada|travado"
    r"|sem narr|narrador sumiu|narrador caiu"
    r"|eco\b|chiand[ao]|estourad[ao]|distorcid[ao]"
    r"|dessincroniz\w*|desincroniz\w*|fora de sinc"
    r"|n[aã]o abre|n[aã]o carrega|n[aã]o funciona"
    r"|dando erro|erro de reprodu"
    r")\b",
    re.IGNORECASE,
)


def get_firestore():
    cred_path = os.environ.get("FIREBASE_CREDENTIALS", "firebase-credentials.json")
    abs_cred = os.path.abspath(cred_path)
    if not os.path.exists(abs_cred):
        print(f"ERRO: credenciais nao encontradas em {abs_cred}")
        sys.exit(1)
    db_id = os.environ.get("FIRESTORE_DATABASE", "(default)")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(fb_credentials.Certificate(abs_cred))
    return fb_firestore.client(database_id=db_id)


def extract_from_live(fs, video_id):
    """Extrai todos os comentarios de uma live."""
    comments_ref = fs.collection("lives").document(video_id).collection("comments")
    comments = []
    for doc in comments_ref.stream():
        data = doc.to_dict()
        text = (data.get("text") or "").strip()
        if not text or len(text) < 3:
            continue
        comments.append({
            "text": text,
            "current_label": 1 if data.get("is_technical") else 0,
            "category": data.get("category") or "",
            "issue": data.get("issue") or "",
            "dismissed": 1 if data.get("dismissed") else 0,
            "video_id": video_id,
            "ts": data.get("ts") or "",
        })
    return comments


def sample_comments(comments, tech_sample=500, neg_sample=1500):
    """Separa em candidatos tecnicos (palavras ambiguas) e negativos aleatorios."""
    tech_candidates = []
    normal_pool = []

    for c in comments:
        if _AMBIGUOUS_WORDS.search(c["text"]):
            tech_candidates.append(c)
        else:
            normal_pool.append(c)

    print(f"  Candidatos tecnicos (palavras ambiguas): {len(tech_candidates)}")
    print(f"  Pool de normais: {len(normal_pool)}")

    # Amostra de candidatos tecnicos
    if len(tech_candidates) > tech_sample:
        random.shuffle(tech_candidates)
        tech_candidates = tech_candidates[:tech_sample]
        print(f"  Amostrados {tech_sample} candidatos tecnicos")
    else:
        print(f"  Usando todos {len(tech_candidates)} candidatos tecnicos")

    # Amostra de negativos
    if len(normal_pool) > neg_sample:
        random.shuffle(normal_pool)
        normal_pool = normal_pool[:neg_sample]
        print(f"  Amostrados {neg_sample} negativos")
    else:
        print(f"  Usando todos {len(normal_pool)} negativos")

    return tech_candidates + normal_pool


def deduplicate(comments):
    """Deduplica por texto normalizado."""
    seen = set()
    unique = []
    for c in comments:
        key = c["text"].strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def save_csv(comments, path):
    fieldnames = ["text", "current_label", "category", "issue",
                  "dismissed", "video_id", "ts"]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in comments:
            writer.writerow(c)


def parse_args():
    p = argparse.ArgumentParser(description="Extrai comentarios do Firestore para retreino")
    p.add_argument("--video_id", default="V580YrkHCB8",
                   help="ID da live alvo (default: V580YrkHCB8)")
    p.add_argument("--all_lives", action="store_true",
                   help="Extrai de todas as lives (ignora --video_id)")
    p.add_argument("--tech_sample", type=int, default=500,
                   help="Maximo de candidatos tecnicos (default: 500)")
    p.add_argument("--neg_sample", type=int, default=1500,
                   help="Maximo de negativos aleatorios (default: 1500)")
    p.add_argument("--output", default="training/real_comments_raw.csv",
                   help="Caminho do CSV de saida")
    return p.parse_args()


def main():
    args = parse_args()

    print("Conectando ao Firestore...")
    fs = get_firestore()

    all_comments = []

    if args.all_lives:
        print("Extraindo de TODAS as lives...")
        lives = fs.collection("lives").stream()
        for live_doc in lives:
            vid = live_doc.id
            print(f"  Live {vid}...", end=" ", flush=True)
            comments = extract_from_live(fs, vid)
            print(f"{len(comments)} comentarios")
            all_comments.extend(comments)
    else:
        print(f"Extraindo da live {args.video_id}...")
        all_comments = extract_from_live(fs, args.video_id)
        print(f"  Total: {len(all_comments)} comentarios")

    if not all_comments:
        print("ERRO: nenhum comentario encontrado.")
        sys.exit(1)

    # Deduplica
    unique = deduplicate(all_comments)
    print(f"\nApos deduplicacao: {len(unique)} comentarios unicos")

    # Estatisticas
    tech = sum(1 for c in unique if c["current_label"] == 1)
    dismissed = sum(1 for c in unique if c["dismissed"] == 1)
    print(f"  Label tecnico (modelo atual): {tech}")
    print(f"  Dismissed (falso positivo confirmado): {dismissed}")

    # Amostragem inteligente
    print(f"\nAmostragem inteligente...")
    sampled = sample_comments(unique, args.tech_sample, args.neg_sample)

    # Salva
    save_csv(sampled, args.output)
    print(f"\nSalvo em: {args.output}")
    print(f"Total: {len(sampled)} comentarios")
    print(f"\nProximo passo:")
    print(f"  cd training && python relabel_with_claude.py")


if __name__ == "__main__":
    main()
