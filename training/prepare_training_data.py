# -*- coding: utf-8 -*-
"""
Prepara dataset final para retreino do DistilBERT.

Lê real_comments_labeled.csv (saída do relabel_with_claude.py) e gera
training_data.csv pronto para o pipeline de treino existente (train.py).

Etapas:
  1. Filtra comentários muito curtos (<3 chars) ou só emojis
  2. Deduplica por texto normalizado
  3. Balanceia classes (alvo: 60-70% negativos, 30-40% positivos)
  4. Augmentation leve nos positivos (se necessário)
  5. Faz backup do dataset sintético anterior
  6. Salva training_data.csv (text, label)
"""

import csv
import os
import random
import re
import shutil
import sys
import unicodedata

random.seed(42)

INPUT_FILE = "real_comments_labeled.csv"
OUTPUT_FILE = "training_data.csv"
BACKUP_FILE = "training_data_backup_sintetico.csv"

# Alvo de balanço
TARGET_POSITIVE_RATIO_MIN = 0.30
TARGET_POSITIVE_RATIO_MAX = 0.40


# ─── FILTROS ──────────────────────────────────────────────────────────────────

# Regex para detectar textos que são só emojis/símbolos
_ONLY_EMOJI_OR_SYMBOLS = re.compile(
    r"^[\s\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
    r"\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
    r"\U00002702-\U000027B0\U000024C2-\U0001F251"
    r"\U0000200D\U0000FE0F\U00002640\U00002642"
    r"\U00002600-\U000026FF\U00002700-\U000027BF"
    r"\U0000FE00-\U0000FE0F\U0001F900-\U0001F9FF"
    r"\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF"
    r"!?.,;:()[\]{}<>@#$%^&*+=|/\\~`\"'_\-]+$"
)

# Regex para emojis custom do YouTube (:nome:)
_YT_CUSTOM_EMOJI = re.compile(r":[a-zA-Z0-9_\-]+:")


def is_valid_comment(text):
    """Retorna True se o comentário é válido para treino."""
    # Remove emojis custom do YT
    cleaned = _YT_CUSTOM_EMOJI.sub("", text).strip()
    if len(cleaned) < 3:
        return False
    if _ONLY_EMOJI_OR_SYMBOLS.match(cleaned):
        return False
    return True


def normalize_text(text):
    """Normaliza texto para deduplicação."""
    t = text.strip().lower()
    # Normaliza unicode (NFD → NFC)
    t = unicodedata.normalize("NFC", t)
    # Remove espaços múltiplos
    t = re.sub(r"\s+", " ", t)
    return t


# ─── AUGMENTATION ─────────────────────────────────────────────────────────────

def strip_diacritics(text):
    """Remove acentos: á→a, é→e, etc."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def augment(text, n=2):
    """Gera n variações leves do texto."""
    results = set()

    transforms = [
        lambda t: t.upper(),
        lambda t: t.lower(),
        lambda t: t + "!!!",
        lambda t: t + " aqui tb",
        lambda t: t + " mano",
        lambda t: t + " gente",
        lambda t: "mano " + t,
        lambda t: "gente " + t,
        lambda t: strip_diacritics(t),
        lambda t: t + " de novo",
        lambda t: t + "...",
        lambda t: "só eu " + t + "?",
    ]

    attempts = 0
    while len(results) < n and attempts < 50:
        t = random.choice(transforms)(text).strip()
        if t and len(t) < 200 and t != text:
            results.add(t)
        attempts += 1

    return list(results)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"ERRO: {INPUT_FILE} não encontrado.")
        print("Execute relabel_with_claude.py primeiro.")
        sys.exit(1)

    # Backup do dataset sintético
    if os.path.exists(OUTPUT_FILE) and not os.path.exists(BACKUP_FILE):
        shutil.copy2(OUTPUT_FILE, BACKUP_FILE)
        print(f"Backup do dataset anterior salvo em: {BACKUP_FILE}")

    # Carrega dados rotulados
    print(f"Carregando {INPUT_FILE}...")
    rows = []
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    print(f"Total bruto: {len(rows)}")

    # Filtra comentários inválidos
    valid = [(r["text"], int(r["label"])) for r in rows if is_valid_comment(r["text"])]
    print(f"Após filtro (>=3 chars, não só emojis): {len(valid)}")

    # Deduplica por texto normalizado
    seen = set()
    unique = []
    for text, label in valid:
        key = (normalize_text(text), label)
        if key not in seen:
            seen.add(key)
            unique.append((text, label))
    print(f"Após deduplicação: {len(unique)}")

    # Contagem de classes
    positives = [(t, l) for t, l in unique if l == 1]
    negatives = [(t, l) for t, l in unique if l == 0]
    print(f"  Positivos: {len(positives)}")
    print(f"  Negativos: {len(negatives)}")

    total = len(unique)
    if total == 0:
        print("ERRO: nenhum comentário válido encontrado.")
        sys.exit(1)

    pos_ratio = len(positives) / total
    print(f"  Ratio positivos: {pos_ratio:.1%}")

    # Balanceamento
    final_positives = list(positives)
    final_negatives = list(negatives)

    if pos_ratio < TARGET_POSITIVE_RATIO_MIN:
        # Positivos sub-representados → augmentation + possível undersample negativos
        print(f"\nPositivos sub-representados ({pos_ratio:.1%}).")

        # Primeiro: augmentation nos positivos
        augmented = []
        for text, label in positives:
            for aug_text in augment(text, n=2):
                norm = normalize_text(aug_text)
                if (norm, 1) not in seen:
                    seen.add((norm, 1))
                    augmented.append((aug_text, 1))
        final_positives.extend(augmented)
        print(f"  Augmentation: +{len(augmented)} positivos")

        # Se ainda insuficiente, undersample negativos
        new_total = len(final_positives) + len(final_negatives)
        new_ratio = len(final_positives) / new_total

        if new_ratio < TARGET_POSITIVE_RATIO_MIN:
            # Calcula quantos negativos manter para atingir ratio mínimo
            target_neg = int(len(final_positives) / TARGET_POSITIVE_RATIO_MIN
                            - len(final_positives))
            if target_neg < len(final_negatives):
                random.shuffle(final_negatives)
                final_negatives = final_negatives[:target_neg]
                print(f"  Undersample negativos: {target_neg} mantidos")

    elif pos_ratio > TARGET_POSITIVE_RATIO_MAX:
        # Positivos sobre-representados → undersample positivos
        print(f"\nPositivos sobre-representados ({pos_ratio:.1%}).")
        target_pos = int(len(final_negatives) * TARGET_POSITIVE_RATIO_MAX
                         / (1 - TARGET_POSITIVE_RATIO_MAX))
        if target_pos < len(final_positives):
            random.shuffle(final_positives)
            final_positives = final_positives[:target_pos]
            print(f"  Undersample positivos: {target_pos} mantidos")
    else:
        print(f"\nDistribuição dentro do alvo ({TARGET_POSITIVE_RATIO_MIN:.0%}-{TARGET_POSITIVE_RATIO_MAX:.0%}).")

    # Monta dataset final
    dataset = final_positives + final_negatives
    random.shuffle(dataset)

    final_pos = sum(1 for _, l in dataset if l == 1)
    final_neg = sum(1 for _, l in dataset if l == 0)
    final_total = len(dataset)

    print(f"\nDataset final:")
    print(f"  Total: {final_total}")
    print(f"  Positivos: {final_pos} ({final_pos/final_total*100:.1f}%)")
    print(f"  Negativos: {final_neg} ({final_neg/final_total*100:.1f}%)")

    # Salva CSV no formato esperado pelo train.py (text, label)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["text", "label"])
        for text, label in dataset:
            writer.writerow([text, label])

    print(f"\nSalvo em: {OUTPUT_FILE}")
    print("Pronto para retreino com submit_training_job.py")


if __name__ == "__main__":
    main()
