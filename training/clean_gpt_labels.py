# -*- coding: utf-8 -*-
"""
Limpa falsos positivos óbvios nos labels do GPT.

Corrige dois tipos de erro:
  1. "vascou/vascando" em contexto esportivo (= falhou no jogo, não a live)
  2. Confirmações positivas ("tem imagem", "voltou o áudio") — live está OK

Lê:   real_comments_gpt_labeled.csv
Gera: real_comments_gpt_cleaned.csv
"""

import csv
import re
from pathlib import Path

INPUT  = Path("real_comments_gpt_labeled.csv")
OUTPUT = Path("real_comments_gpt_cleaned.csv")

# "vascou/vascando" SEM contexto de live/stream/transmissão = esportivo
_VASCOU = re.compile(r"\bvasco[uU]|vascand", re.I)
_VASCOU_TECH_CTX = re.compile(
    r"\b(live|stream|transmiss|sinal|audio|som|video|imagem|tela|aplicativo|app)\b",
    re.I,
)

# Confirmações positivas (live está funcionando)
_POSITIVE_CONFIRM = re.compile(
    r"\b(tem|ta|tá|voltou|apareceu|funcionou|funcionando|resolveu|voltou)\b.{0,30}"
    r"\b(imagem|audio|áudio|som|sinal|video|vídeo|live)\b"
    r"|^(tem imagem|tem audio|tem som|voltou|ta funcionando|tá funcionando)[\s!.]*$",
    re.I,
)


def should_flip_to_zero(text: str) -> str | None:
    """Retorna motivo se o label deve ser trocado de 1 para 0, senão None."""
    t = text.strip()

    # Vascou sem contexto técnico
    if _VASCOU.search(t) and not _VASCOU_TECH_CTX.search(t):
        return "vascou_esportivo"

    # Confirmação positiva
    if _POSITIVE_CONFIRM.search(t):
        return "confirmacao_positiva"

    return None


def main():
    if not INPUT.exists():
        print(f"ERRO: {INPUT} não encontrado.")
        print("Execute label_with_gpt.py primeiro.")
        return

    with open(INPUT, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    total    = len(rows)
    flipped  = 0
    reasons  = {}

    output_rows = []
    for row in rows:
        new_row = dict(row)
        if row.get("label") == "1":
            motivo = should_flip_to_zero(row.get("text", ""))
            if motivo:
                new_row["label"] = "0"
                flipped += 1
                reasons[motivo] = reasons.get(motivo, 0) + 1
        output_rows.append(new_row)

    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_rows[0].keys())
        writer.writeheader()
        writer.writerows(output_rows)

    pos_before = sum(1 for r in rows if r.get("label") == "1")
    pos_after  = sum(1 for r in output_rows if r.get("label") == "1")

    print(f"Total: {total}")
    print(f"Positivos antes : {pos_before} ({pos_before/total*100:.1f}%)")
    print(f"Positivos depois: {pos_after}  ({pos_after/total*100:.1f}%)")
    print(f"Corrigidos: {flipped}")
    for motivo, n in reasons.items():
        print(f"  {motivo}: {n}")
    print(f"Salvo em: {OUTPUT}")


if __name__ == "__main__":
    main()
