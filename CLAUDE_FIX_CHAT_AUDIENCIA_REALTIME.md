# YouTube Monitor - Fix Chat/Audiencia em Tempo Real (VM)

> Ultima atualizacao: 2026-02-23

## Problema observado

- O feed de "ultimas 3000 msgs" travava em timestamps antigos.
- A audiencia ficava sem atualizar (ou com valor incoerente).

## Causa raiz

1. `ts` dos comentarios estava sendo salvo em formatos mistos:
- ISO com `T` (ex.: `2026-02-22T19:44:36.987000-03:00`)
- formato com espaco (ex.: `2026-02-22 21:07:54`)

Como o dashboard ordena por string (`orderBy("ts")`), o formato com espaco passa a ordenar "antes" do formato com `T`, quebrando o recorte das ultimas 3000 mensagens.

2. Na VM, `YOUTUBE_API_KEY` nao estava configurada no `systemd`, e a coleta de audiencia por API nao rodava.

## Correcao aplicada

Arquivo alterado: `monitor.py`

### 1) Timestamp do chat normalizado

- Novo helper: `chat_ts_iso_brt(ts_raw_ms, ts_raw_str)`.
- Prioriza `c.timestamp` (epoch em ms), converte para BRT e salva sempre em ISO:
  - `YYYY-MM-DDTHH:MM:SS.mmm-03:00`
- `now_iso()` tambem padronizado com `timespec="milliseconds"`.

Resultado: novos comentarios voltam a entrar corretamente no topo da ordenacao do feed.

### 2) Audiencia com fallback sem API key

- `SERVING_URL` default alinhado com Cloud Run atual.
- `_fetch_concurrent_viewers(video_id)` agora:
  - tenta API v3 (se `YOUTUBE_API_KEY` existir),
  - fallback por scraping do watch page.
- O valor principal do fallback passou a vir do `ytInitialData > videoPrimaryInfoRenderer > viewCount` (texto `assistindo agora` do video principal).
- Removido fallback generico que podia capturar numeros baixos de cards relacionados e derrubar a audiencia.

Resultado: `concurrent_viewers` voltou a atualizar na VM mesmo sem `YOUTUBE_API_KEY`.

## Deploy aplicado na VM

```bash
scp -i ~/.ssh/monitor_vm monitor.py USUARIO@IP_DA_VM:/home/monitor-cazetv/monitor/monitor.py
ssh -i ~/.ssh/monitor_vm USUARIO@IP_DA_VM "sudo systemctl restart monitor-cazetv.service"
```

## Validacao feita

- `systemctl status` do servico: ativo.
- Firestore (`lives/{videoId}`):
  - `last_seen_at` avancando,
  - `concurrent_viewers` atualizando.
- Firestore (`comments` order by `ts desc`):
  - timestamps novos em ISO/BRT no topo (nao mais preso em `19:44`).

## Commit sugerido

```bash
git add monitor.py CLAUDE_FIX_CHAT_AUDIENCIA_REALTIME.md
git commit -m "fix: restaura chat realtime (ultimas 3000) e audiencia na VM"
git push
```
