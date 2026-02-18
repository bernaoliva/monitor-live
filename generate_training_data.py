# -*- coding: utf-8 -*-
"""
Gerador de dados sintéticos para treino do classificador de comentários técnicos.
Gera exemplos positivos (problema técnico) e negativos (comentário normal)
com variações para aumentar a diversidade do dataset.

Saída: training_data.csv  (colunas: text, label)
  label=1 → problema técnico
  label=0 → comentário normal
"""

import csv
import random
import re

random.seed(42)

# ─────────────────────────────────────────────────────────────────────────────
# BASE: EXEMPLOS POSITIVOS (label=1) — problemas técnicos reais
# ─────────────────────────────────────────────────────────────────────────────

POSITIVOS = [
    # ── ÁUDIO: SEM SOM ──
    "sem audio", "sem áudio", "sem som", "cadê o áudio", "cadê o som",
    "não tem áudio", "não tem som", "sumiu o áudio", "sumiu o som",
    "o áudio sumiu", "o som sumiu", "perdeu o áudio", "perdeu o som",
    "áudio caiu", "som caiu", "áudio foi", "foi o áudio",
    "tá sem áudio", "tá sem som", "ficou sem áudio", "ficou sem som",
    "audio sumiu", "sem audio aqui", "sem som aqui", "sem áudio aqui",
    "não tô ouvindo nada", "não ouço nada", "silêncio total",
    "o áudio morreu", "morreu o áudio", "áudio bugou", "audio bugou",
    "tô sem áudio", "tô sem som", "meu áudio sumiu",
    "não tem mais áudio", "não tem mais som",

    # ── ÁUDIO: CORTANDO ──
    "o áudio tá cortando", "áudio cortando", "som cortando",
    "o som tá cortando", "áudio tá picotando", "som picotando",
    "o áudio fica cortando", "áudio travando", "áudio gaguejando",
    "audio cortando", "ficando sem áudio", "o áudio some vez ou outra",
    "áudio interrompendo", "o som fica sumindo",

    # ── ÁUDIO: CHIADO / ESTOURADO ──
    "áudio chiando", "som chiando", "o áudio tá chiando",
    "áudio estourado", "som estourado", "o som tá estourado",
    "áudio horrível", "som horrível", "qualidade do áudio péssima",
    "áudio distorcido", "som distorcido", "o áudio distorceu",
    "áudio ruim demais", "som ruim demais",

    # ── ÁUDIO: ECO / DUPLICADO ──
    "áudio duplicado", "som duplicado", "dois áudios ao mesmo tempo",
    "dois sons ao mesmo tempo", "eco no áudio", "áudio com eco",
    "o áudio tá com eco", "o som tá com eco", "eco enorme",
    "tá com eco", "eco no som",

    # ── ÁUDIO: ATRASO / DESSINCRONIA ──
    "áudio atrasado", "som atrasado", "o áudio tá atrasado",
    "o som tá atrasado", "áudio fora de sincronia", "desincronizado",
    "áudio dessincronizado", "o áudio não tá sincronizado",
    "áudio adiantado", "som adiantado", "o áudio tá na frente",
    "o som tá uns 2 segundos atrás", "o áudio tá uns 3s adiantado",
    "vídeo na frente do áudio", "áudio na frente do vídeo",
    "o áudio tá fora de sincronia", "fora de sinc",
    "boca e voz não tão sincronizados", "o narrador tá atrasado",

    # ── ÁUDIO: SEM NARRAÇÃO ──
    "sem narração", "sem narrador", "cadê o narrador",
    "narrador sumiu", "narrador caiu", "o narrador sumiu",
    "tá sem narrador", "tá sem narração", "perdeu o narrador",
    "a narração sumiu", "ficou sem narração", "não tem narrador",
    "o narrador foi", "sumiu a narração",

    # ── VÍDEO: TELA PRETA ──
    "tela preta", "tá tela preta", "só tela preta",
    "ficou tela preta", "a tela ficou preta", "tela preta aqui",
    "tela preta pra mim", "só vejo tela preta", "tela preta do nada",
    "a transmissão ficou tela preta", "black screen",

    # ── VÍDEO: TRAVANDO / CONGELANDO ──
    "travando", "tá travando", "tá travando muito", "travando demais",
    "travou", "congelou", "tá congelado", "a imagem congelou",
    "o vídeo travou", "vídeo congelou", "vídeo travando",
    "travando aqui", "travando pra caramba", "travando feio",
    "tá congelando", "fica congelando", "ficou congelado",
    "imagem travada", "vídeo parado", "a imagem parou",
    "fica parando", "para toda hora", "travou de vez",

    # ── VÍDEO: PIXELANDO / QUALIDADE ──
    "pixelando", "tá pixelado", "muito pixelado", "pixelou",
    "imagem pixelada", "vídeo pixelado", "cheio de pixel",
    "resolução caiu", "resolução baixou", "qualidade caiu",
    "qualidade horrível", "qualidade péssima", "qualidade baixou",
    "tá em 144p", "tá em baixíssima qualidade", "imagem borrada",
    "borrado demais", "muito borrado", "desfocado demais",
    "comprimido demais", "qualidade ruim", "ficou em baixa resolução",
    "resolução tá horrível",

    # ── REDE / PLATAFORMA: BUFFERING ──
    "buffering", "bufferizando", "buffering infinito",
    "não carrega", "fica carregando", "tá carregando infinito",
    "o carregamento não acaba", "fica no loading", "loading eterno",
    "tá rodando", "fica rodando", "só fica carregando",
    "o círculo fica girando", "não sai do buffer",
    "buffering demais", "muito buffering",

    # ── REDE / PLATAFORMA: LIVE CAIU ──
    "live caiu", "a live caiu", "caiu pra mim", "caiu aqui",
    "a transmissão caiu", "transmissão caiu", "saiu do ar",
    "foi do ar", "a live foi do ar", "a live encerrou do nada",
    "a live fechou", "a live caiu de novo", "live caindo",
    "caiu a live", "a live reiniciou", "reiniciou do zero",
    "voltou do zero", "recomeçou do zero", "a live recomeçou",
    "live foi abaixo", "a transmissão encerrou sozinha",

    # ── REDE / PLATAFORMA: ERRO / NÃO ABRE ──
    "não abre", "dá erro aqui", "erro ao carregar",
    "não consegue carregar", "não consigo assistir",
    "não tá funcionando", "tá dando erro", "erro de reprodução",
    "não carrega de jeito nenhum", "ficou com erro",
    "dá erro toda hora", "não abre a live", "a live não abre",
    "não reproduz", "não toca", "dá bug aqui",

    # ── PLACAR / GC ──
    "PLACAR ERRADO",
]

# ─────────────────────────────────────────────────────────────────────────────
# BASE: EXEMPLOS NEGATIVOS (label=0) — comentários normais
# ─────────────────────────────────────────────────────────────────────────────

NEGATIVOS = [
    # ── REAÇÕES GENÉRICAS ──
    "kkkkk", "kkkkkkkk", "kkk", "kk", "kkkkkkkkkkk",
    "hahahaha", "haha", "hauhauha", "huehuehue",
    "rsrsrs", "rsrsrsrs", "rsrs",
    "😂😂😂", "😂😂", "🤣🤣🤣", "😆😆",
    "kkk que isso", "que cena kkk", "kkk mano",
    "hauahauahau", "KKKKKKK", "KKK",

    # ── EXCLAMAÇÕES ──
    "nossa", "caramba", "meu Deus", "que isso",
    "incrível", "sensacional", "absurdo", "impossível",
    "não acredito", "que loucura", "que coisa",
    "que absurdo", "uau", "nossa senhora",
    "cara", "mano", "que situação",

    # ── GOL / LANCE ──
    "GOOOOOOL", "goool", "gol!", "que gol!",
    "vai vaaaai", "vai vai vai", "bora bora bora",
    "que golaço", "golaço", "que lindo",
    "que pintura", "que chute", "que cabeçada",
    "que defesa", "que falha", "frango",
    "frango do goleiro", "goleiro ruim",
    "olha o goleiro", "que erro",

    # ── TORCIDA ──
    "vai Flamengo!", "Flamengo é o maior", "bora Mengão",
    "Fla campeão", "Mengão!", "FLA FLA FLA",
    "vai Palmeiras", "Palmeiras campeão", "Porco!",
    "vai Corinthians", "Corinthians!", "Timão!",
    "vai São Paulo", "Tricolor!", "vai Santos",
    "vai Grêmio", "vai Internacional", "vai Athletico",
    "vai Brasil", "bora Brasil", "Brasil campeão",
    "vai seleção", "seleção!", "BRASIL",
    "joga mais", "que time", "time bom",
    "time ruim", "time fraco", "que time hein",

    # ── OPINIÕES SOBRE O JOGO ──
    "era pênalti", "não foi pênalti", "pênalti isso",
    "isso foi fora né?", "era falta", "não foi falta",
    "juiz horrível", "esse juiz é roubado", "juiz vendido",
    "roubaram", "roubaram demais", "que juiz",
    "árbitro ruim", "árbitro favorecendo",
    "jogo bom", "jogaço", "que partida",
    "jogo ruim", "jogo fraco", "que jogo chato",
    "melhor jogo do ano", "melhor gol do ano",
    "jogada linda", "que jogada", "que drrible",

    # ── PERGUNTAS SOBRE O JOGO ──
    "quem tá ganhando?", "quanto tá o placar?",
    "quando começa?", "que horário é?", "que horas começa?",
    "alguém sabe o placar?", "qual é o resultado?",
    "quantos gols fez?", "quem fez o gol?",
    "quando volta?", "quando retorna?",
    "qual é o canal?", "onde assistir?",
    "o jogo é quando?", "já começou?",

    # ── SAUDAÇÕES / CHAT GERAL ──
    "boa tarde galera", "boa noite pessoal", "bom dia",
    "oi pessoal", "salve!", "salve galera",
    "fala galera", "e aí pessoal", "chegando aqui",
    "cheguei", "aqui chegando", "to aqui",
    "to assistindo", "assistindo aqui",
    "olá a todos", "olá",

    # ── RESPOSTAS CURTAS / EMOJIS ──
    "top", "show", "demais", "boa", "boa!", "legal",
    "massa", "maneiro", "dahora", "dahora!",
    "👏👏👏", "👏👏", "🔥🔥🔥", "🔥🔥", "🔥",
    "💪💪", "💪", "👍", "👍👍", "❤️❤️", "❤️",
    "🏆", "⚽", "⚽⚽", "🎉🎉", "🎉",
    "😍", "😍😍", "🙌🙌", "🙌",
    "10", "10/10", "nota 10",

    # ── NEGAÇÃO DE PROBLEMA TÉCNICO (casos difíceis) ──
    "agora voltou o som", "áudio voltou", "voltou o áudio",
    "resolveu o som", "o áudio voltou normal",
    "aqui tá normal", "aqui não tá travando",
    "aqui tá ótimo", "pra mim tá bom", "pra mim tá perfeito",
    "aqui tá perfeito", "não tá travando aqui",
    "aqui tá funcionando", "o meu tá normal",
    "aqui tá ok", "resolveu", "voltou",
    "já voltou", "já resolveu", "tá bom agora",
    "melhorou", "tá melhor agora",
    "aqui tá liso", "aqui tá suave",
    "voltou a live", "a live voltou", "voltou a transmissão",
    "a transmissão voltou",

    # ── COMENTÁRIOS VAGOS (não técnicos) ──
    "sla", "sei lá", "num sei", "não sei",
    "e daí?", "e aí?", "e então?",
    "o que foi?", "o que houve?",
    "nada a ver", "que nada a ver",
    "não entendi", "confuso",
    "interessante", "que interessante",
    "depende", "talvez", "pode ser",

    # ── SOBRE JOGADORES / NARRADOR ──
    "que narrador bom", "o narrador tá ótimo", "narração boa",
    "narrador animado", "que animação do narrador",
    "que comentarista", "comentarista bom",
    "o jogador foi bem", "que craque", "craque demais",
    "jogador ruim", "que jogador", "esse jogador não presta",
]

# ─────────────────────────────────────────────────────────────────────────────
# AUGMENTATION: variações para aumentar diversidade
# ─────────────────────────────────────────────────────────────────────────────

def augment(text: str, n: int = 3) -> list[str]:
    """Gera `n` variações do texto aplicando transformações aleatórias."""
    results = set()
    results.add(text)

    transforms = [
        lambda t: t.upper(),
        lambda t: t.lower(),
        lambda t: t.capitalize(),
        lambda t: t + "!!!",
        lambda t: t + "??",
        lambda t: t + " 😭",
        lambda t: t + " 😤",
        lambda t: t + " kk",
        lambda t: t + " kkk",
        lambda t: t + " cara",
        lambda t: t + " mano",
        lambda t: t + " gente",
        lambda t: t + " aqui tb",
        lambda t: t + " tbm",
        lambda t: t + " aqui também",
        lambda t: t + " pra mim também",
        lambda t: "ué " + t,
        lambda t: "gente " + t,
        lambda t: "mano " + t,
        lambda t: "cara " + t,
        lambda t: "socorro " + t,
        lambda t: t.replace("á", "a").replace("ã", "a").replace("é", "e")
                   .replace("ê", "e").replace("í", "i").replace("ó", "o")
                   .replace("ô", "o").replace("ú", "u").replace("ç", "c"),
        lambda t: re.sub(r'\s+', ' ', t + " " + t),  # repetição
        lambda t: t + "...",
        lambda t: t + " pqp",
        lambda t: t + " que isso",
        lambda t: t + " de novo",
        lambda t: t + " ainda",
        lambda t: t + " sempre isso",
        lambda t: t + " horrível",
        lambda t: t + " absurdo",
        lambda t: "alguém mais " + t + "?",
        lambda t: "só eu " + t + "?",
        lambda t: "todo mundo " + t,
        lambda t: t + " pessoal",
        lambda t: t.replace("qu", "q"),  # typo leve
    ]

    attempts = 0
    while len(results) < n + 1 and attempts < 100:
        t = random.choice(transforms)(text)
        t = t.strip()
        if t and len(t) < 200:
            results.add(t)
        attempts += 1

    return list(results)[1 : n + 1]  # exclui o original


# ─────────────────────────────────────────────────────────────────────────────
# GERAÇÃO DO DATASET
# ─────────────────────────────────────────────────────────────────────────────

def build_dataset(aug_per_example: int = 4) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []

    # positivos base
    for text in POSITIVOS:
        rows.append((text, 1))
        for v in augment(text, aug_per_example):
            rows.append((v, 1))

    # negativos base
    for text in NEGATIVOS:
        rows.append((text, 0))
        for v in augment(text, aug_per_example):
            rows.append((v, 0))

    # remove duplicatas exatas
    seen = set()
    unique: list[tuple[str, int]] = []
    for text, label in rows:
        key = (text.strip().lower(), label)
        if key not in seen:
            seen.add(key)
            unique.append((text.strip(), label))

    random.shuffle(unique)
    return unique


def save_csv(rows: list[tuple[str, int]], path: str):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["text", "label"])
        for text, label in rows:
            writer.writerow([text, label])


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    dataset = build_dataset(aug_per_example=4)

    pos = sum(1 for _, l in dataset if l == 1)
    neg = sum(1 for _, l in dataset if l == 0)

    print(f"Total de exemplos : {len(dataset)}")
    print(f"  Positivos (1)   : {pos}")
    print(f"  Negativos (0)   : {neg}")
    print(f"  Balanço         : {pos/(pos+neg)*100:.1f}% / {neg/(pos+neg)*100:.1f}%")

    out = "training_data.csv"
    save_csv(dataset, out)
    print(f"\nSalvo em: {out}")

    # preview
    print("\n--- Amostra de positivos ---")
    sample_pos = [t for t, l in dataset if l == 1][:6]
    for s in sample_pos:
        print(f"  [1] {s}")

    print("\n--- Amostra de negativos ---")
    sample_neg = [t for t, l in dataset if l == 0][:6]
    for s in sample_neg:
        print(f"  [0] {s}")
