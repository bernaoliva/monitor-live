# Monitor de Lives — YouTube

Sistema de monitoramento de transmissões ao vivo do YouTube que coleta comentários do chat em tempo real e usa IA para detectar problemas técnicos relatados pelos espectadores.

Projetado para canais de grande audiência (500k+ espectadores simultâneos).

## O que faz

Analisa milhares de comentários por minuto e classifica automaticamente reclamações técnicas — sem áudio, tela preta, travando, buffering, delay, placar sumiu — exibindo tudo em um dashboard em tempo real para a equipe de operações agir rápido.

## Arquitetura

```
YouTube Chat → Coletor Python → Pré-filtro → DistilBERT (GPU) → Guard → Firestore → Dashboard
```

- **Coletor**: captura mensagens do chat via pytchat, envia em batches para classificação
- **IA**: DistilBERT multilingual fine-tuned (F1 = 0.93) servido em Cloud Run GPU
- **3 camadas de classificação**: pré-filtro regex → modelo de IA → guard de keywords
- **Dashboard**: Next.js com dados em tempo real via Firestore `onSnapshot`

### Alto volume

Pipeline assíncrono que aguenta ~500 msgs/s:

```
chat → pré-filtro (descarta ~80%) → batch queue (64 items / 100ms)
  → 1 request HTTP para N textos → Firestore WriteBatch
  → contadores em memória → flush a cada 3s
```

## Dashboard

- **AO VIVO** — cards por stream com feed de problemas, gráfico de volume por minuto, breakdown por categoria (Áudio, Vídeo, Rede, GC), alerta sonoro, dismiss de falsos positivos
- **HISTÓRICO** — lives encerradas com métricas e gráfico final
- **Detalhe** — feed completo com filtros, exportação

## Stack

| Componente | Tecnologia |
|---|---|
| Coletor de chat | Python, pytchat, threading |
| Classificação | DistilBERT multilingual fine-tuned |
| Inferência | Cloud Run GPU (T4) + fallback CPU local |
| Treino | Vertex AI (A100 80GB) |
| Banco de dados | Firebase Firestore |
| Dashboard | Next.js 16, Tailwind CSS, Recharts |
| Hosting | Vercel |

## Estrutura

```
├── monitor.py                  # Coletor + classificação + Firestore
├── dashboard/                  # Frontend Next.js
│   ├── app/                    # Rotas (/, /historico, /live/[id])
│   ├── components/             # LiveCard, CommentsChart, etc.
│   └── lib/                    # Firebase config, tipos
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

## Métricas do modelo

| Métrica | Valor |
|---|---|
| F1-Score | 0.933 |
| Precision | 0.911 |
| Recall | 0.957 |
| Dataset | 3k exemplos (70/30) |

## Licença

Uso pessoal.
