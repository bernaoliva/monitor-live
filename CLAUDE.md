# YouTube Monitor — Contexto do Projeto

> Sessão Claude Code: `youtube-monitor`
> Para retomar: `claude --resume youtube-monitor`

## O que é este projeto

Monitor de lives do YouTube do canal **CazéTV** que coleta comentários do chat em tempo real e usa IA para detectar problemas técnicos relatados pelos espectadores (sem áudio, travando, tela preta, buffering, etc.).

## Arquitetura atual (local)

```
YouTube Chat → pytchat → fila → Ollama gemma3:4b (local) → classifica → dashboard FastAPI
```

- Roda na máquina do usuário
- IA local via Ollama
- Dashboard web em `localhost`
- Histórico em SQLite (`monitor_history.sqlite3`)

## Arquitetura alvo (nuvem)

```
YouTube Chat → Cloud Run (coletor) → Cloud Run GPU (DistilBERT) → BigQuery
                                             ↓
                                      dashboard web
```

- **Coletor**: `monitor.py` rodando no Cloud Run
- **IA**: DistilBERT multilingual fine-tuned, servido no Cloud Run com GPU (NVIDIA L4 ou T4)
- **Escala**: aguenta 1M+ espectadores (~250 msgs/seg) com GPU
- **Custo**: ~$1/live de 2h, Cloud Run escala para zero quando não há live
- **Melhoria contínua**: dados salvos no BigQuery, retreino semanal via Vertex AI Pipelines

## Arquivos do projeto

```
monitor_live/
├── monitor.py                  ← código principal (coleta + IA + dashboard)
├── CLAUDE.md                   ← este arquivo
│
├── generate_training_data.py   ← gera dataset sintético de treino
├── training_data.csv           ← 1850 exemplos gerados (889 positivos / 961 negativos)
│
├── trainer/
│   ├── train.py                ← fine-tune do DistilBERT (roda no Vertex AI)
│   └── requirements.txt        ← dependências do treino
│
├── setup_gcp.py                ← configura GCP uma vez (bucket, APIs, etc.)
├── submit_training_job.py      ← envia o job de treino ao Vertex AI
└── download_model.py           ← baixa o modelo treinado do GCS para pasta local
```

## Status atual

- [x] Código do monitor funcionando localmente com Ollama
- [x] Dataset sintético gerado (1850 exemplos balanceados)
- [x] Script de fine-tune do DistilBERT pronto (`trainer/train.py`)
- [x] Scripts de configuração e submissão do Vertex AI prontos
- [ ] Configurar GCP (rodar `setup_gcp.py`)
- [ ] Submeter treino no Vertex AI (rodar `submit_training_job.py`)
- [ ] Baixar modelo treinado (rodar `download_model.py`)
- [ ] Criar serviço de inferência (Cloud Run + GPU)
- [ ] Fazer deploy do coletor (`monitor.py`) no Cloud Run
- [ ] Integrar monitor.py com o endpoint de inferência (substituir `ollama_classify`)
- [ ] Loop de melhoria contínua (BigQuery + Vertex AI Pipelines)

## Como treinar o modelo no Vertex AI

### Pré-requisitos
```bash
pip install google-cloud-aiplatform google-cloud-storage
# Instalar gcloud CLI: https://cloud.google.com/sdk/docs/install
```

### Passo a passo
```bash
# 1. Configurar GCP (uma vez só)
python setup_gcp.py \
  --project_id SEU_PROJECT_ID \
  --bucket_name monitor-lives-bucket

# 2. Submeter treino (GPU T4, ~30-60min, ~$0.35)
python submit_training_job.py \
  --project_id SEU_PROJECT_ID \
  --bucket_name monitor-lives-bucket \
  --use_gpu

# 3. Acompanhar em:
# https://console.cloud.google.com/vertex-ai/training/custom-jobs

# 4. Baixar modelo quando terminar
python download_model.py --bucket_name monitor-lives-bucket
```

## Decisões técnicas importantes

| Decisão | Escolha | Motivo |
|---|---|---|
| Modelo de IA | DistilBERT multilingual | Menor, rápido em CPU/GPU, bom em português |
| Treino | Vertex AI Custom Training | Sem GPU local, usa créditos GCP |
| Serviço de inferência | Cloud Run + GPU | Escala para zero, paga só durante a live |
| Dados de treino | Sintéticos (1850 ex.) | Poucos dados reais (<500) no SQLite |
| GPU para inferência | NVIDIA T4 ou L4 | ~250 msgs/seg necessário para 1M espectadores |

## Créditos GCP disponíveis

$300 de créditos no Google Cloud (verificar data de expiração em console.cloud.google.com/billing).
Custo estimado total do projeto: **< $50** (treino + meses de uso).

| Serviço | Custo estimado |
|---|---|
| Treino Vertex AI (GPU T4, 1x) | ~$0.35 |
| Cloud Run GPU por live de 2h | ~$0.90 |
| Cloud Run CPU (coletor) | ~$0.05/live |
| 10 lives/mês | ~$9/mês |

---

## O que foi feito nesta sessão

### 1. Análise do monitor.py
- O código já faz exatamente o fluxo desejado, mas tudo local
- Usa `pytchat` para capturar chat do YouTube
- Usa Ollama (`gemma3:4b`) para classificar cada comentário via LLM local
- Dashboard FastAPI com gráficos de problemas por categoria
- SQLite guarda histórico de streams e issues detectados
- Problema: LLM local é lento e não escala para 1M espectadores

### 2. Definição da arquitetura cloud
- Discutimos volume real: 1M espectadores → ~250 msgs/seg
- DistilBERT em CPU aguenta ~50 msgs/seg — insuficiente
- DistilBERT em GPU T4 aguenta ~2.000 msgs/seg — mais que suficiente
- Cloud Run escala para zero → paga só durante a live (solução de custo)
- Loop de melhoria: classificações salvas → retreino semanal automático

### 3. Geração do dataset sintético (`generate_training_data.py`)
- Problema: SQLite só tem exemplos positivos (<500), sem negativos
- Solução: geração sintética com augmentation
- Resultado: **1.850 exemplos** (889 positivos / 961 negativos)
- Categorias cobertas nos positivos:
  - Áudio: sem som, cortando, chiando, eco, atraso, sem narração
  - Vídeo: tela preta, travando, pixelando, qualidade ruim
  - Rede: buffering, live caiu, erro ao abrir
- Negativos incluem casos difíceis: negações de problema ("áudio voltou", "aqui tá normal")
- Augmentation: variações com typos, emojis, sufixos ("kk", "mano"), maiúsculas

### 4. Script de fine-tune (`trainer/train.py`)
- Modelo: `distilbert-base-multilingual-cased` (HuggingFace)
- Classificação binária: 0 = não técnico, 1 = técnico
- Split 85/15 treino/validação estratificado
- EarlyStopping (patience=2) para evitar overfitting
- Métricas: accuracy, F1, precision, recall
- Salva modelo + tokenizer + metrics.json no GCS via AIP_MODEL_DIR

### 5. Scripts de infraestrutura GCP
- `setup_gcp.py`: cria bucket, habilita APIs, cria estrutura de pastas
- `submit_training_job.py`: faz upload do CSV e script, submete CustomTrainingJob
- `download_model.py`: baixa modelo treinado do GCS para pasta `model/`

---

## Próximo passo

Após rodar o treino e baixar o modelo, criar o serviço de inferência:
1. Criar `serving/app.py` — FastAPI servindo o DistilBERT
2. Criar `serving/Dockerfile` — container para Cloud Run com GPU
3. Fazer deploy no Cloud Run
4. Atualizar `monitor.py`: substituir `ollama_classify()` pela chamada HTTP ao endpoint
