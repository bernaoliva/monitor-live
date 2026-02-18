# -*- coding: utf-8 -*-
"""
Serviço de inferência — DistilBERT classificador de comentários técnicos.
Roda no Cloud Run. Substitui o Ollama local do monitor.py.

Endpoints:
  GET  /health          → status do serviço
  POST /classify        → classifica um comentário
  POST /classify/batch  → classifica vários de uma vez (mais eficiente)
"""

import json
import logging
import os
import re
from contextlib import asynccontextmanager
from typing import Optional

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import DistilBertForSequenceClassification, DistilBertTokenizerFast

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MODEL_DIR = os.environ.get("MODEL_DIR", "/app/model")
MAX_LEN   = int(os.environ.get("MAX_LEN", "64"))

# ─────────────────────────────────────────────────────────────────────────────
# REGRAS DE CATEGORIA/SEVERIDADE (baseadas em palavras-chave)
# Aplicadas SOMENTE quando o modelo classifica como técnico (label=1)
# ─────────────────────────────────────────────────────────────────────────────

ISSUE_RULES = [
    # (padrões regex, categoria, issue, severidade)
    (r"sem ?(audio|áudio|som)|sumiu.*(audio|áudio|som)|(audio|áudio|som) sumiu|não (tem|há|ouço|ouve|escuto) ?(audio|áudio|som|nada)|cadê.*(audio|áudio|som)|perdeu.*(audio|áudio|som)",
     "ÁUDIO", "SEM ÁUDIO", "high"),

    (r"(audio|áudio|som) (cortando|picotando|gaguejando|interrompendo|travando)|cortando.*(audio|áudio|som)",
     "ÁUDIO", "ÁUDIO CORTANDO", "medium"),

    (r"(audio|áudio|som).*(chiando|estourado|distorcido|horrível|ruim)|chiando|estourado",
     "ÁUDIO", "ÁUDIO DISTORCIDO", "medium"),

    (r"eco|(audio|áudio|som) duplicado|dois (audio|áudios|sons)",
     "ÁUDIO", "ÁUDIO COM ECO/DUPLICADO", "medium"),

    (r"(audio|áudio|som).*(atrasado|adiantado|atraso|dessincronizado|fora de sincronia|desincronizado)|fora de sinc|boca.*voz|voz.*boca",
     "SINCRONIZAÇÃO", "ÁUDIO FORA DE SINCRONIA", "medium"),

    (r"sem (narração|narrador)|narrador (sumiu|caiu|foi)|sumiu.*(narração|narrador)|cadê.*(narrador|narração)",
     "ÁUDIO", "SEM NARRAÇÃO", "high"),

    (r"tela preta|black screen",
     "VÍDEO", "TELA PRETA", "high"),

    (r"travando|travou|congelou|congelando|congelado|imagem (parou|travou|congelou)|fica parando|para toda hora",
     "REDE/PLATAFORMA", "BUFFERING", "medium"),

    (r"pixelando|pixelado|pixelou|muitos? pixels?|resolução (caiu|baixou)|qualidade (caiu|baixou|péssima|horrível)|baixa resolução|borrado|imagem borrada|em 144p",
     "VÍDEO", "QUALIDADE BAIXA", "low"),

    (r"buffering|bufferizando|fica carregando|carregando infinito|loading eterno|círculo girando|não (carrega|sai do buffer)",
     "REDE/PLATAFORMA", "BUFFERING", "medium"),

    (r"live (caiu|foi|encerrou|fechou|reiniciou)|caiu.*(live|transmissão)|saiu do ar|foi do ar|transmissão (caiu|encerrou|foi)",
     "REDE/PLATAFORMA", "LIVE CAIU", "high"),

    (r"(não|nao) (abre|carrega|reproduz|funciona)|dá? erro|erro ao (carregar|abrir|reproduzir)|bug",
     "REDE/PLATAFORMA", "ERRO AO CARREGAR", "high"),

    (r"PLACAR ERRADO",
     "PLACAR/GC", "PLACAR ERRADO", "medium"),
]

_compiled_rules = [
    (re.compile(pat, re.IGNORECASE), cat, iss, sev)
    for pat, cat, iss, sev in ISSUE_RULES
]


def get_category(text: str):
    """Retorna (category, issue, severity) baseado em palavras-chave."""
    for pattern, cat, iss, sev in _compiled_rules:
        if pattern.search(text):
            return cat, iss, sev
    return None, None, "none"


# ─────────────────────────────────────────────────────────────────────────────
# MODELO (carregado uma vez na inicialização)
# ─────────────────────────────────────────────────────────────────────────────

model_state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Carregando modelo de: {MODEL_DIR}")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Device: {device}")

    tokenizer = DistilBertTokenizerFast.from_pretrained(MODEL_DIR)
    model = DistilBertForSequenceClassification.from_pretrained(MODEL_DIR)
    model.to(device)
    model.eval()

    model_state["tokenizer"] = tokenizer
    model_state["model"]     = model
    model_state["device"]    = device

    logger.info("Modelo carregado. Servico pronto.")
    yield
    model_state.clear()


app = FastAPI(title="Classificador de Comentários Técnicos", lifespan=lifespan)


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

MAX_COMMENT_LENGTH = 5000

class ClassifyRequest(BaseModel):
    text: str

class BatchRequest(BaseModel):
    texts: list[str]

class ClassifyResult(BaseModel):
    is_technical: bool
    category:     Optional[str]
    issue:        Optional[str]
    severity:     str
    confidence:   float


# ─────────────────────────────────────────────────────────────────────────────
# INFERÊNCIA
# ─────────────────────────────────────────────────────────────────────────────

def _infer(texts: list[str]) -> list[ClassifyResult]:
    if not texts:
        return []

    tokenizer = model_state["tokenizer"]
    model     = model_state["model"]
    device    = model_state["device"]

    inputs = tokenizer(
        texts,
        truncation=True,
        padding=True,
        max_length=MAX_LEN,
        return_tensors="pt",
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)
        probs   = torch.softmax(outputs.logits, dim=-1)
        preds   = outputs.logits.argmax(dim=-1)

    results = []
    for i, (pred, prob) in enumerate(zip(preds, probs)):
        is_technical = bool(pred.item() == 1)
        confidence   = float(prob[pred].item())

        if is_technical:
            cat, iss, sev = get_category(texts[i])
            # Se nenhuma regra de keyword confirmou, é falso positivo
            if cat is None:
                is_technical = False
                sev = "none"
        else:
            cat, iss, sev = None, None, "none"

        results.append(ClassifyResult(
            is_technical=is_technical,
            category=cat,
            issue=iss,
            severity=sev,
            confidence=confidence,
        ))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "device": model_state.get("device", "loading"),
        "model":  MODEL_DIR,
    }


@app.post("/classify", response_model=ClassifyResult)
def classify(req: ClassifyRequest):
    if not model_state:
        raise HTTPException(status_code=503, detail="Modelo ainda carregando")
    if len(req.text) > MAX_COMMENT_LENGTH:
        raise HTTPException(status_code=400, detail=f"Texto excede o limite de {MAX_COMMENT_LENGTH} caracteres")
    results = _infer([req.text.strip()])
    return results[0]


@app.post("/classify/batch", response_model=list[ClassifyResult])
def classify_batch(req: BatchRequest):
    if not model_state:
        raise HTTPException(status_code=503, detail="Modelo ainda carregando")
    if len(req.texts) > 256:
        raise HTTPException(status_code=400, detail="Máximo 256 textos por batch")
    texts = [t.strip() for t in req.texts if t.strip()]
    return _infer(texts)
