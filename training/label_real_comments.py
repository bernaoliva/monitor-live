import csv
import re
import unicodedata
from pathlib import Path


INPUT_PATH = Path("training/real_comments_raw.csv")
OUTPUT_PATH = Path("training/real_comments_labeled.csv")


NEGATIVE_PATTERNS = [
    re.compile(r"\btravou (a|o) (zaga|jogo|time|ataque|defesa|meio|jogador)\b"),
    re.compile(r"\btravou o jogo\b"),
    re.compile(r"\btravou a zaga\b"),
    re.compile(r"\bdelay do\b"),
    re.compile(r"\bsinal de (truco|fumaca|fum[aá]ca|penalti|escanteio|impedimento)\b"),
    re.compile(r"\bcaiu (o|a) (time|jogo|rendimento|jogada|jogador|zaga|ataque|pipa)\b"),
    re.compile(r"\bcaiu sozinho\b"),
    re.compile(r"\bse for chorar manda audio\b"),
    re.compile(r"\bmanda audio\b"),
    re.compile(r"\b(prefiro|melhor) sem (som|audio)\b"),
    re.compile(r"\btv sem (som|audio)\b"),
    re.compile(r"\bnarra(cao|ção) (boa|otima|ótima|top|perfeita)\b"),
    re.compile(r"\bnarrador (bom|boa|otimo|ótimo|brabo|top)\b"),
    re.compile(r"\bvoltou (o )?(audio|som|video|imagem|sinal|stream|chat)\b"),
    re.compile(r"\bagora (ta|t[aá]|esta|est[aá]) (bom|boa|ok|normal)\b"),
    re.compile(r"\b(normalizou|arrumaram|consertaram|resolvido)\b"),
]


POSITIVE_PATTERNS = [
    re.compile(r"\bsem (som|audio|imagem|video)\b"),
    re.compile(r"\btela (preta|escura)\b"),
    re.compile(r"\b(audio|som) (estourad|chiad|ruim|baixo|alto|abafad|picot|cort)\w*"),
    re.compile(r"\b(imagem|video|tela) (trav|congel|ruim|pixel|borrad|cort|picot)\w*"),
    re.compile(r"\b(atrasad|delay|dessincron|desincron)\w* (no|na|do|da)? ?(audio|som|imagem|video|sinal|transmissao|transmissão|live|stream)\b"),
    re.compile(r"\b(audio|som|imagem|video|sinal|transmissao|transmissão|live|stream) (atrasad|com delay|dessincron|desincron)\w*"),
    re.compile(r"\b(buffering|carregando|fora do ar|queda de sinal)\b"),
    re.compile(r"\b(caiu|travou|bugou|lagou)\b.{0,20}\b(live|stream|transmissao|transmissão|youtube|sinal)\b"),
    re.compile(r"\b(live|stream|transmissao|transmissão|sinal)\b.{0,20}\b(caiu|trav|bug|lag|ruim|instavel|instável)\w*"),
]


TECH_OBJECTS = re.compile(
    r"\b(audio|som|imagem|video|tela|transmissao|transmissão|live|stream|sinal|youtube|chat)\b"
)
PROBLEM_WORDS = re.compile(
    r"\b(sem|mudo|trav|congel|delay|atras|bug|falh|chiad|estourad|picot|cort|pixel|borrad|buffer|carreg|fora do ar|queda|instavel|instável)\w*"
)
GAME_CONTEXT = re.compile(
    r"\b(jogo|zaga|ataque|defesa|meio|jogador|time|gol|juiz|arbitro|árbitro|escanteio|impedimento)\b"
)


def _fix_mojibake(text: str) -> str:
    # Tenta recuperar textos que chegaram como UTF-8 lido em latin1.
    try:
        fixed = text.encode("latin1").decode("utf-8")
        if fixed.count("Ã") + fixed.count("�") < text.count("Ã") + text.count("�"):
            return fixed
    except Exception:
        pass
    return text


def _normalize(text: str) -> str:
    t = _fix_mojibake((text or "").strip()).lower()
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def classify_comment(text: str, current_label: str, category: str) -> int:
    norm = _normalize(text)
    if not norm:
        return 0

    # Evita ruído de emoji/risada/xingamento curto.
    if len(re.sub(r"[^a-z0-9]+", "", norm)) < 3:
        return 0

    for pat in NEGATIVE_PATTERNS:
        if pat.search(norm):
            return 0

    for pat in POSITIVE_PATTERNS:
        if pat.search(norm):
            return 1

    has_object = bool(TECH_OBJECTS.search(norm))
    has_problem = bool(PROBLEM_WORDS.search(norm))
    has_game_context = bool(GAME_CONTEXT.search(norm))

    if has_object and has_problem and not has_game_context:
        return 1

    # Aproveita rótulo/categoria antigos só quando há indício técnico no texto.
    if (current_label or "").strip() == "1" and has_problem and not has_game_context:
        return 1
    if (category or "").strip().upper() in {"AUDIO", "VIDEO", "REDE", "GC"} and has_problem:
        return 1

    return 0


def main() -> None:
    with INPUT_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    out_rows = []
    for row in rows:
        text = row.get("text", "")
        current_label = row.get("current_label", "")
        category = row.get("category", "")
        out_rows.append(
            {
                "text": text,
                "label": str(classify_comment(text, current_label, category)),
                "reason": "chatgpt",
                "current_label": current_label,
                "category": category,
                "video_id": row.get("video_id", ""),
                "ts": row.get("ts", ""),
            }
        )

    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["text", "label", "reason", "current_label", "category", "video_id", "ts"],
        )
        writer.writeheader()
        writer.writerows(out_rows)

    positives = sum(1 for r in out_rows if r["label"] == "1")
    print(f"input_rows={len(rows)}")
    print(f"output_rows={len(out_rows)}")
    print(f"label_1={positives}")
    print(f"label_0={len(out_rows) - positives}")
    print(f"saved={OUTPUT_PATH}")


if __name__ == "__main__":
    main()
