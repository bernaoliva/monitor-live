# -*- coding: utf-8 -*-
"""
Re-rotula comentários usando Claude Haiku API.

Lê real_comments_raw.csv e gera real_comments_labeled.csv com labels
de alta qualidade para retreino do DistilBERT.

Regras:
  - dismissed=1 → label=0 (falso positivo confirmado pelo operador)
  - Resto → classifica via Claude Haiku em batches de 50

Requer: ANTHROPIC_API_KEY no .env ou variável de ambiente.
  pip install anthropic python-dotenv
"""

import csv
import json
import os
import sys
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import anthropic

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BATCH_SIZE = 50           # comentários por chamada ao Claude
MODEL = "claude-haiku-4-5-20251001"
INPUT_FILE = "real_comments_raw.csv"
OUTPUT_FILE = "real_comments_labeled.csv"
PROGRESS_FILE = "relabel_progress.json"  # checkpoint para retomar

SYSTEM_PROMPT = """Você é um rotulador de dados para treino de modelo de IA.

Contexto: chat ao vivo do YouTube durante transmissão de futebol/esportes (canal CazéTV).

Para cada comentário, classifique:
- is_technical: true se o espectador está REPORTANDO um problema técnico na transmissão (áudio, vídeo, buffering, tela preta, etc). false se é reação ao jogo, torcida, opinião, zueira, ou qualquer coisa que NÃO seja problema técnico.

ATENÇÃO a falsos positivos comuns:
- "travou" pode ser sobre o jogo (jogador travou, jogo travou = parou de ter gol), não sobre a transmissão
- "sem áudio" pode ser piada/ironia
- "congelou" pode ser sobre clima ou reação emocional
- Emojis e reações curtas NÃO são problemas técnicos
- "voltou o áudio", "agora tá bom" = resolução, NÃO é problema ativo (label=0)
- "narração boa", "narrador ótimo" = elogio, NÃO é problema técnico (label=0)
- Perguntas sobre o jogo, torcida, opinião sobre jogadores = NÃO técnico (label=0)
- Xingamentos e ofensas genéricas = NÃO técnico (label=0)

Responda SOMENTE com JSON array, um objeto por comentário:
[{"index": 0, "is_technical": true, "reason": "breve justificativa"}, ...]"""


def load_comments(path):
    """Carrega CSV de comentários."""
    comments = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            comments.append(row)
    return comments


def load_progress():
    """Carrega checkpoint de progresso (índice do último batch processado)."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            return json.load(f)
    return {"last_batch_idx": -1, "results": []}


def save_progress(progress):
    """Salva checkpoint."""
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f)


def classify_batch_with_claude(client, texts, start_index):
    """Envia batch de textos ao Claude e retorna labels."""
    # Monta prompt com os comentários numerados
    comments_block = "\n".join(
        f"[{i}] {text}" for i, text in enumerate(texts)
    )

    user_prompt = f"""Classifique os {len(texts)} comentários abaixo.

{comments_block}

Responda com JSON array:"""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )

            # Parse resposta
            content = response.content[0].text.strip()
            # Remove possível markdown wrapper
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            results = json.loads(content)

            # Valida formato
            if not isinstance(results, list):
                raise ValueError(f"Esperado array, recebeu {type(results)}")

            # Monta dict indexado
            label_map = {}
            for item in results:
                idx = item.get("index", -1)
                is_tech = item.get("is_technical", False)
                reason = item.get("reason", "")
                label_map[idx] = {"label": 1 if is_tech else 0, "reason": reason}

            # Preenche missing com label=0
            final = []
            for i in range(len(texts)):
                if i in label_map:
                    final.append(label_map[i])
                else:
                    final.append({"label": 0, "reason": "missing_from_response"})

            return final

        except anthropic.RateLimitError:
            wait = 30 * (attempt + 1)
            print(f"    Rate limit — aguardando {wait}s...")
            time.sleep(wait)

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            print(f"    Erro ao parsear resposta (tentativa {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(5)

        except Exception as e:
            print(f"    Erro inesperado (tentativa {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(10)

    # Fallback: marca tudo como 0 se falhou após retries
    print(f"    FALHA após {max_retries} tentativas — batch marcado como label=0")
    return [{"label": 0, "reason": "api_failure"} for _ in texts]


def main():
    # Verifica API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERRO: ANTHROPIC_API_KEY não definida.")
        print("Defina no .env ou como variável de ambiente.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # Carrega comentários
    print(f"Carregando {INPUT_FILE}...")
    comments = load_comments(INPUT_FILE)
    print(f"Total: {len(comments)} comentários")

    # Carrega progresso
    progress = load_progress()
    results = progress["results"]
    start_batch = progress["last_batch_idx"] + 1

    # Fase 1: Labels automáticos (sem gastar API)
    auto_labeled = 0
    needs_api = []

    for i, c in enumerate(comments):
        if i < len(results):
            # Já processado em execução anterior
            continue

        if c.get("dismissed") == "1":
            # Falso positivo confirmado pelo operador
            results.append({"label": 0, "reason": "dismissed_by_operator"})
            auto_labeled += 1
        else:
            needs_api.append((i, c))

    print(f"Auto-rotulados (dismissed): {auto_labeled}")
    print(f"Precisam de API: {len(needs_api)}")

    # Preenche results com placeholders para os que precisam de API
    while len(results) < len(comments):
        results.append(None)

    # Fase 2: Classificar com Claude Haiku em batches
    api_indices = [idx for idx, _ in needs_api]
    api_texts = [c["text"] for _, c in needs_api]

    total_batches = (len(api_texts) + BATCH_SIZE - 1) // BATCH_SIZE
    processed_batches = 0

    # Calcula quais batches já foram processados
    already_done = 0
    for idx in api_indices:
        if results[idx] is not None:
            already_done += 1

    if already_done > 0:
        print(f"Retomando — {already_done} já processados via checkpoint")

    for batch_start in range(0, len(api_texts), BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, len(api_texts))
        batch_texts = api_texts[batch_start:batch_end]
        batch_indices = api_indices[batch_start:batch_end]
        batch_num = batch_start // BATCH_SIZE

        # Pula batches já processados
        if all(results[idx] is not None for idx in batch_indices):
            processed_batches += 1
            continue

        print(f"  Batch {batch_num+1}/{total_batches} "
              f"({len(batch_texts)} textos, índices {batch_indices[0]}-{batch_indices[-1]})...",
              end=" ", flush=True)

        labels = classify_batch_with_claude(client, batch_texts, batch_start)

        # Atribui resultados
        for idx, label_info in zip(batch_indices, labels):
            results[idx] = label_info

        processed_batches += 1
        tech_count = sum(1 for l in labels if l["label"] == 1)
        print(f"OK ({tech_count} técnicos)")

        # Salva checkpoint
        progress["last_batch_idx"] = batch_num
        progress["results"] = results
        save_progress(progress)

        # Pequena pausa entre batches para não sobrecarregar API
        if batch_start + BATCH_SIZE < len(api_texts):
            time.sleep(0.5)

    # Fase 3: Salvar CSV final
    print(f"\nSalvando {OUTPUT_FILE}...")

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["text", "label", "reason", "current_label", "category",
                         "video_id", "ts"])
        for i, c in enumerate(comments):
            label_info = results[i]
            if label_info is None:
                label_info = {"label": 0, "reason": "unprocessed"}
            writer.writerow([
                c["text"],
                label_info["label"],
                label_info["reason"],
                c.get("current_label", ""),
                c.get("category", ""),
                c.get("video_id", ""),
                c.get("ts", ""),
            ])

    # Estatísticas finais
    total = len(results)
    tech = sum(1 for r in results if r and r["label"] == 1)
    normal = total - tech
    print(f"\nResultado final:")
    print(f"  Total: {total}")
    print(f"  Técnicos (1): {tech} ({tech/total*100:.1f}%)")
    print(f"  Normais (0): {normal} ({normal/total*100:.1f}%)")
    print(f"\nSalvo em: {OUTPUT_FILE}")

    # Limpa checkpoint após sucesso
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
        print("Checkpoint removido.")


if __name__ == "__main__":
    main()
