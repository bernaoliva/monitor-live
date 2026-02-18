# Monitor de Lives — YouTube

Monitor de transmissoes ao vivo do YouTube que coleta comentarios do chat em tempo real e usa IA para detectar problemas tecnicos relatados pelos espectadores (sem audio, travando, tela preta, buffering, etc.).

## Arquitetura

```
YouTube Chat
    |
    v
monitor.py (pytchat)
    |
    v
Classificacao IA -----> Firestore
  (Cloud Run GPU)           |
                            v
                      Dashboard Next.js
                      (Vercel)
```

**Coletor** (`monitor.py`): captura mensagens do chat via pytchat, classifica cada uma com IA e salva no Firestore.

**Classificador**: DistilBERT multilingual fine-tuned servido no Cloud Run com GPU. Sistema de 3 camadas: pre-filtro por regex, modelo de IA, e guard de keywords para evitar falsos positivos.

**Dashboard** (`dashboard/`): Next.js 16 + Tailwind + Recharts com dados em tempo real via Firestore `onSnapshot`.

## Dashboard

- **AO VIVO**: cards de streams ativas com feed de problemas, grafico de volume por minuto, categorias detectadas (Audio, Video, Rede, GC)
- **HISTORICO**: lista de streams encerradas com metricas e grafico final
- **Detalhe** (`/live/[id]`): view completa com todos os comentarios, filtros (todos/problemas), dismiss de falsos positivos, exportacao

## Stack

| Componente | Tecnologia |
|---|---|
| Coletor de chat | Python + pytchat |
| Classificacao IA | DistilBERT multilingual (fine-tuned) |
| Inferencia | Cloud Run GPU (NVIDIA T4) |
| Banco de dados | Firebase Firestore |
| Dashboard | Next.js 16 + Tailwind CSS + Recharts |
| Hosting | Vercel |
| Treino do modelo | Vertex AI (Google Cloud) |

## Setup

### 1. Dashboard

```bash
cd dashboard
cp .env.local.example .env.local
# Preencha .env.local com as credenciais do seu projeto Firebase
npm install
npm run dev
```

### 2. Monitor (coletor)

```bash
pip install pytchat firebase-admin requests

# Coloque seu firebase-credentials.json na raiz do projeto
# Configure a URL do classificador (Cloud Run)
export SERVING_URL="https://seu-servico.run.app"

python monitor.py
```

### 3. Treino do modelo (opcional)

```bash
# Gerar dataset sintetico
python generate_training_data.py

# Configurar GCP
python setup_gcp.py --project_id SEU_PROJECT_ID --bucket_name SEU_BUCKET

# Submeter treino no Vertex AI
python submit_training_job.py --project_id SEU_PROJECT_ID --bucket_name SEU_BUCKET --use_gpu

# Baixar modelo treinado
python download_model.py --bucket_name SEU_BUCKET

# Deploy do servico de inferencia
python deploy_serving.py --project_id SEU_PROJECT_ID --bucket_name SEU_BUCKET
```

## Estrutura do projeto

```
monitor-live/
├── monitor.py                  # Coletor de chat + classificacao + Firestore
├── generate_training_data.py   # Gera dataset sintetico (1850 exemplos)
├── training_data.csv           # Dataset de treino
├── dashboard/                  # Frontend Next.js
│   ├── app/                    # Rotas (/, /historico, /live/[id])
│   ├── components/             # LiveCard, HistoricoCard, CommentsChart, etc.
│   ├── lib/                    # Firebase config, types
│   └── .env.local.example      # Template de variaveis de ambiente
├── serving/                    # Servico de inferencia (Cloud Run)
│   ├── app.py                  # FastAPI servindo DistilBERT
│   ├── Dockerfile
│   └── requirements.txt
├── trainer/                    # Fine-tune do DistilBERT
│   ├── train.py
│   └── requirements.txt
├── setup_gcp.py                # Configuracao inicial do GCP
├── submit_training_job.py      # Submete treino no Vertex AI
├── deploy_serving.py           # Deploy do classificador no Cloud Run
└── download_model.py           # Baixa modelo treinado do GCS
```

## Variaveis de ambiente

### Dashboard (`dashboard/.env.local`)

| Variavel | Descricao |
|---|---|
| `NEXT_PUBLIC_FIREBASE_API_KEY` | API key do Firebase |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | Auth domain |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Project ID |
| `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET` | Storage bucket |
| `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID` | Sender ID |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | App ID |

### Monitor (`monitor.py`)

| Variavel | Descricao | Default |
|---|---|---|
| `FIREBASE_CREDENTIALS` | Caminho para o JSON de credenciais | `firebase-credentials.json` |
| `SERVING_URL` | URL do classificador no Cloud Run | (obrigatorio) |
| `LLM_WORKERS` | Workers paralelos de classificacao | `4` |

## Licenca

Este projeto e de uso pessoal.
