# CRIA - Chats em Revisão por Inteligência Artificial

Monitor de lives do YouTube dos canais **CazéTV** e **GETV** que coleta comentários do chat em tempo real e usa IA para detectar problemas técnicos relatados pelos espectadores.

Projetado para canais de grande audiência (500k+ espectadores simultâneos).

## O que faz

Analisa milhares de comentários por minuto e classifica automaticamente reclamações técnicas — sem áudio, tela preta, travando, buffering, delay, placar sumiu — exibindo tudo em um dashboard em tempo real para a equipe de operações agir rápido.

## Topologia

```
┌───────────────────────────────────────────┐
│            YOUTUBE LIVE CHAT               │
│            CazéTV + GETV                   │
└─────────────────┬─────────────────────────┘
                  │ pytchat (1 thread por live)
                  │ coleta mensagens do chat
                  ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                          VM LOCAL (192.168.99.111)                                │
│                          monitor.py (systemd service)                             │
│                                                                                   │
│  ┌────────────────────┐  batch 64 msgs   ┌──────────────────────────────────┐    │
│  │ COLETA              │  ou 100ms        │ AUDIÊNCIA (1x/min por live)      │    │
│  │                     │────────────────▶│ YouTube Data API v3 + InnerTube  │    │
│  │ 1 thread por live   │                  │                                  │    │
│  │ dedup 5000 msgs     │                  │ decide rota de classificação     │    │
│  └────────────────────┘                  └──────────┬──────────┬────────────┘    │
│                                            < 300k    │          │  >= 300k        │
│                                                      ▼          ▼                  │
│                                           ┌────────────┐  ┌──────────────┐        │
│                                           │ CPU LOCAL   │  │ CLOUD RUN    │        │
│                                           │ :8080       │  │ GPU (T4)     │        │
│                                           │             │  │ us-central1  │        │
│                                           │ DistilBERT  │  │ DistilBERT   │        │
│                                           │ fine-tuned  │  │ fine-tuned   │        │
│                                           │ linguagem   │  │ linguagem    │        │
│                                           │ de chat     │  │ de chat      │        │
│                                           │ timeout 4s  │  │ timeout 15s  │        │
│                                           │ fallback ──▶│  │ $0.90/2h     │        │
│                                           └──────┬─────┘  └──────┬───────┘        │
│                                                  └───────┬───────┘                │
└─────────────────────────────────────────────────────────┼────────────────────────┘
                                                          │ WriteBatch (400 ops)
                                                          │ comentários classificados
                                                          │ + contadores (flush 3s)
                                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          FIRESTORE (youtube-monitor-474920)                     │
│                                                                                 │
│  /lives/{video_id}                                                              │
│    ├── status, title, viewers, counters, issue_counts                           │
│    ├── 📁 comments/{hash}  →  author, text, ts, category, severity             │
│    └── 📁 minutes/{YYYY-MM-DDTHH:mm}  →  total, technical, viewers             │
└────────────────┬────────────────────────────────────────────┬───────────────────┘
                 │ onSnapshot (WebSocket)                     │ export comentários
                 │ updates em tempo real                      │ rotulados + dismisses
                 ▼                                            ▼
┌───────────────────────────────────────────┐  ┌──────────────────────────────────┐
│            VERCEL (CDN)                    │  │  RETREINO (futuro)               │
│                                            │  │                                  │
│  Next.js 16 + Tailwind + Recharts          │  │  Vertex AI / local               │
│  SSR + Static, Edge Network                │  │                                  │
│                                            │  │  • Comentários técnicos +        │
│  /              AO VIVO (grid de lives)    │  │    dismissed = dataset            │
│  /historico     Lives encerradas           │  │    supervisionado                 │
│  /live/[id]     Detalhe + feed completo    │  │  • Fine-tune DistilBERT           │
│                                            │  │    linguagem de chat              │
│  Auth: Firebase Auth (Google provider)     │  │  • Deploy novo modelo             │
└─────────────────┬─────────────────────────┘  │    no Cloud Run / CPU             │
                  │ HTTPS                       └──────────────────────────────────┘
                  ▼
┌───────────────────────────────────────────┐
│               USUÁRIOS                     │
│       monitor-cazetv.vercel.app            │
│       Login: Google SSO (@livemode.com)    │
└───────────────────────────────────────────┘
```

## Stack

| Componente | Tecnologia |
|---|---|
| Coletor de chat | Python, pytchat, threading |
| Classificação | DistilBERT multilingual fine-tuned |
| Inferência GPU | Cloud Run (NVIDIA T4, scale-to-zero) |
| Inferência CPU | Local na VM (porta 8080) |
| Treino | Vertex AI (A100 80GB) |
| Banco de dados | Firebase Firestore |
| Dashboard | Next.js 16, Tailwind CSS, Recharts |
| Hosting | Vercel |
| Auth | Google SSO (@livemode.com) |

## Métricas do modelo

| Métrica | Valor |
|---|---|
| F1-Score | 0.933 |
| Precision | 0.911 |
| Recall | 0.957 |
| Dataset | 3k exemplos (70/30) |

## Dashboard

- **AO VIVO** — cards por stream com feed de problemas, gráfico de volume por minuto, breakdown por categoria (Áudio, Vídeo, Rede, GC), alerta sonoro, dismiss de falsos positivos
- **HISTÓRICO** — lives encerradas com métricas e gráfico final
- **Detalhe** — feed completo com filtros, exportação

## Estrutura

```
├── monitor.py                  # Coletor + classificação + Firestore
├── dashboard/                  # Frontend Next.js
│   ├── app/                    # Rotas (/, /historico, /live/[id])
│   ├── components/             # LiveCard, CommentsChart, etc.
│   └── lib/                    # Firebase config, tipos, health-score
├── serving/                    # Serviço de inferência (Cloud Run)
│   ├── app.py                  # FastAPI + DistilBERT
│   └── Dockerfile
├── trainer/                    # Fine-tune do modelo
│   └── train.py
├── training/                   # Pipeline de dados
│   ├── clean_gpt_labels.py     # Limpeza de labels
│   └── merge_training_data.py  # Merge + balanceamento
├── training_data.csv           # Dataset de treino
├── submit_training_job.py      # Submete treino (Vertex AI)
├── deploy_serving.py           # Deploy no Cloud Run
└── download_model.py           # Baixa modelo do GCS
```

## Licença

Uso interno — CazéTV / LiveMode.
