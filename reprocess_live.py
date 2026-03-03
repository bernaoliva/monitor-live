# -*- coding: utf-8 -*-
"""
Reprocessa comentários de uma live específica no Firestore,
aplicando regras de classificação atualizadas para encontrar
problemas técnicos que foram ignorados anteriormente.

Uso:
  python reprocess_live.py <video_id>              # interativo
  python reprocess_live.py <video_id> --yes        # auto-confirma
  python reprocess_live.py <video_id> --dry-run    # só mostra, não grava
"""

import re
import sys
import firebase_admin
from firebase_admin import credentials, firestore

# ─── Regras de classificação (sincronizadas com serving/app.py + monitor.py) ──

RULES = [
    # ÁUDIO
    (re.compile(r"sem ?(audio|áudio|som)|sumiu.*(audio|áudio|som)|(audio|áudio|som) sumiu|não (tem|há|ouço|ouve|escuto) ?(audio|áudio|som|nada)|cadê.*(audio|áudio|som)|perdeu.*(audio|áudio|som)", re.I),
     "ÁUDIO", "SEM ÁUDIO", "high"),
    (re.compile(r"(audio|áudio|som) (cortando|picotando|gaguejando|interrompendo|travando)|cortando.*(audio|áudio|som)", re.I),
     "ÁUDIO", "ÁUDIO CORTANDO", "medium"),
    (re.compile(r"(audio|áudio|som).*(chiando|estourado|distorcido|horrível|ruim)|chiando|estourado", re.I),
     "ÁUDIO", "ÁUDIO DISTORCIDO", "medium"),
    (re.compile(r"eco|(audio|áudio|som) duplicado|dois (audio|áudios|sons)", re.I),
     "ÁUDIO", "ÁUDIO COM ECO/DUPLICADO", "medium"),
    (re.compile(r"(audio|áudio|som).*(atrasado|adiantado|atraso|dessincronizado|fora de sincronia|desincronizado)|fora de sinc|boca.*voz|voz.*boca", re.I),
     "SINCRONIZAÇÃO", "ÁUDIO FORA DE SINCRONIA", "medium"),
    (re.compile(r"sem (narração|narrador)|narrador (sumiu|caiu|foi)|sumiu.*(narração|narrador)|cadê.*(narrador|narração)", re.I),
     "ÁUDIO", "SEM NARRAÇÃO", "high"),

    # VÍDEO
    (re.compile(r"tela preta|black screen", re.I),
     "VÍDEO", "TELA PRETA", "high"),
    (re.compile(r"pixelando|pixelado|pixelou|muitos? pixels?|resolução (caiu|baixou)|qualidade (caiu|baixou|péssima|horrível)|baixa resolução|borrado|imagem borrada|em 144p", re.I),
     "VÍDEO", "QUALIDADE BAIXA", "low"),

    # REDE/PLATAFORMA — buffering/travamento
    (re.compile(r"travando|travou|travada|travado|congelou|congelando|congelado|lagando|lagou|lag\b|imagem (parou|travou|congelou)|fica parando|para toda hora", re.I),
     "REDE/PLATAFORMA", "BUFFERING", "medium"),
    (re.compile(r"buffering|bufferizando|fica carregando|carregando infinito|loading eterno|círculo girando|não (carrega|sai do buffer)", re.I),
     "REDE/PLATAFORMA", "BUFFERING", "medium"),

    # REDE/PLATAFORMA — live caiu
    (re.compile(r"live (caiu|foi|encerrou|fechou|reiniciou)|caiu.*(live|transmissão)|saiu do ar|foi do ar|transmissão (caiu|encerrou|foi)", re.I),
     "REDE/PLATAFORMA", "LIVE CAIU", "high"),
    (re.compile(r"vascou|vascando|vai vascar", re.I),
     "REDE/PLATAFORMA", "LIVE CAIU", "high"),

    # REDE/PLATAFORMA — erro ao carregar
    (re.compile(r"(não|nao) (abre|carrega|reproduz|funciona)|dá? erro|erro ao (carregar|abrir|reproduzir)|bug", re.I),
     "REDE/PLATAFORMA", "ERRO AO CARREGAR", "high"),

    # REDE — sinal
    (re.compile(r"sem sinal|sinal (caiu|ruim|horrível|horrivel|péssimo|péssim|pessim|cortou|sumiu|zoado)|cad[eê] o? ?sinal|perd(eram|eu|ido) o? ?sinal|f sinal", re.I),
     "REDE", "SEM SINAL", "high"),

    # REDE/PLATAFORMA — delay
    (re.compile(r"delay.*(stream|live|transmiss)|delay (alto|enorme|absurdo|gigante|gigantesco|de \d+|demais|imenso|insuportável)|(stream|live|transmiss).*(delay|atraso|atrasad)|com delay|muito delay|ta com delay|tá com delay|latência|latencia", re.I),
     "REDE/PLATAFORMA", "DELAY", "medium"),

    # REDE/PLATAFORMA — internet (piada técnica)
    (re.compile(r"(não|nao|n) (pagou?|paga) (a |o )?(internet|wifi|wi-fi|net\b)|pag(a|ue) a (internet|wifi|wi-fi)|internet.*(cortaram|discada|caiu)|cortaram.*(internet|wifi)", re.I),
     "REDE/PLATAFORMA", "CONEXÃO", "medium"),

    # PLACAR
    (re.compile(r"PLACAR ERRADO", re.I),
     "PLACAR/GC", "PLACAR ERRADO", "medium"),
]

# Exclusões: evitar falsos positivos de contexto esportivo
EXCLUSIONS = [
    re.compile(r"travou\s+(?:a\s+zag|a\s+defes|o\s+atacant|o\s+lanc|a\s+jogad|na\s+hora|no\s+lance|o\s+golei)", re.I),
]


def classify_text(text: str):
    """Retorna (category, issue, severity) ou None se não for técnico."""
    for excl in EXCLUSIONS:
        if excl.search(text):
            return None
    for pattern, cat, issue, sev in RULES:
        if pattern.search(text):
            return cat, issue, sev
    return None


def main():
    if len(sys.argv) < 2:
        print("Uso: python reprocess_live.py <video_id> [--yes] [--dry-run]")
        sys.exit(1)

    video_id = sys.argv[1]
    auto_yes = "--yes" in sys.argv
    dry_run = "--dry-run" in sys.argv

    cred = credentials.Certificate("firebase-credentials.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    live_ref = db.collection("lives").document(video_id)
    live_doc = live_ref.get()
    if not live_doc.exists:
        print(f"Live {video_id} não encontrada no Firestore")
        sys.exit(1)

    live_data = live_doc.to_dict()
    print(f"Live: {live_data.get('title', video_id)}")
    print(f"Canal: {live_data.get('channel_name', '?')}")
    print(f"tech_comments antes: {live_data.get('tech_comments', 0)}")
    print()

    # Buscar TODOS os comentários
    comments_ref = live_ref.collection("comments")
    all_comments = list(comments_ref.stream())
    print(f"Total de comentários na subcoleção: {len(all_comments)}")

    # Reclassificar os não-técnicos
    found = []
    for doc in all_comments:
        data = doc.to_dict()
        if data.get("is_technical"):
            continue
        text = data.get("text", "")
        result = classify_text(text)
        if result:
            cat, issue, sev = result
            found.append({
                "id": doc.id,
                "text": text,
                "author": data.get("author", "?"),
                "ts": data.get("ts", "?"),
                "category": cat,
                "issue": issue,
                "severity": sev,
            })

    if not found:
        print("\nNenhum comentário técnico novo encontrado.")
        return

    print(f"\n{'='*60}")
    print(f"  {len(found)} comentários técnicos encontrados para reclassificar:")
    print(f"{'='*60}\n")

    for i, c in enumerate(found, 1):
        print(f"  {i}. [{c['category']}:{c['issue']}] [{c['severity']}] {c['text'][:100]}")
        print(f"     — {c['author']} às {c['ts']}")

    if dry_run:
        print(f"\n[DRY RUN] Nenhuma alteração feita.")
        return

    if not auto_yes:
        print(f"\n{'='*60}")
        resp = input(f"Atualizar {len(found)} comentários no Firestore? (s/n): ").strip().lower()
        if resp != "s":
            print("Cancelado.")
            return

    # Atualizar comentários em batch
    batch = db.batch()
    batch_ops = 0
    issue_counts_delta = {}
    minutes_delta = {}  # chave_minuto -> {total_tech_delta, issues_delta}

    for c in found:
        ref = comments_ref.document(c["id"])
        batch.update(ref, {
            "is_technical": True,
            "category": c["category"],
            "issue": c["issue"],
            "severity": c["severity"],
            "dismissed": False,
            "_reprocessed": True,
        })
        batch_ops += 1

        # Contadores por categoria
        key = f"{c['category']}:{c['issue']}"
        issue_counts_delta[key] = issue_counts_delta.get(key, 0) + 1

        # Contadores por minuto
        ts = str(c.get("ts", ""))
        if len(ts) >= 16:
            minute_key = ts[:16]  # "2026-03-03T18:09"
            if minute_key not in minutes_delta:
                minutes_delta[minute_key] = 0
            minutes_delta[minute_key] += 1

        if batch_ops >= 400:
            batch.commit()
            batch = db.batch()
            batch_ops = 0

    if batch_ops > 0:
        batch.commit()

    print(f"\n{len(found)} comentários atualizados!")

    # Atualizar contadores da live
    current_tech = live_data.get("tech_comments", 0)
    current_issues = live_data.get("issue_counts", {})

    for key, delta in issue_counts_delta.items():
        current_issues[key] = current_issues.get(key, 0) + delta

    live_ref.update({
        "tech_comments": current_tech + len(found),
        "issue_counts": current_issues,
    })

    print(f"\nContadores da live atualizados:")
    print(f"  tech_comments: {current_tech} -> {current_tech + len(found)}")
    for key, count in issue_counts_delta.items():
        print(f"  {key}: +{count}")

    # Atualizar subcoleção minutes
    for minute_key, tech_delta in minutes_delta.items():
        min_ref = live_ref.collection("minutes").document(minute_key)
        min_doc = min_ref.get()
        if min_doc.exists:
            min_ref.update({"tech": firestore.Increment(tech_delta)})
            print(f"  minute {minute_key}: tech +{tech_delta}")
        else:
            print(f"  minute {minute_key}: doc não existe, pulando")

    print("\nReprocessamento concluído!")


if __name__ == "__main__":
    main()
