# YouTube Monitor - Diagnostico VM Cloud (Live Discovery)

> Ultima atualizacao: 2026-02-20 (ajuste de falso positivo apos encerramento)

## O que aconteceu

Na VM Google Cloud, o monitor continuou ativo (`systemd` rodando), mas a deteccao de lives caiu para `0 live(s)` mesmo com lives no ar.

## Evidencias validadas na VM

- Servico `monitor-cazetv.service` ativo e estavel.
- `monitor.py` local e da VM com o mesmo hash SHA256:
  - `832792993ADECB37F5B075CD86508DA177A2E2DFEE351B005DBE0D4E018B96C9`
- `resolve_channel_id_by_handle("@CazeTV")` funcionando.
- `list_live_videos_any("@CazeTV", "")` retornando `[]` na VM.
- HTML de `@CazeTV/streams` chegando com tamanho normal, mas sem `videoId` e sem `watch?v=...`.
- Teste por feed XML do canal encontrou lives ativas.

## Causa raiz

A estrategia de scraping HTML (`/videos?live_view=501`, `/streams`, `/live`) ficou fragil na VM porque o HTML retornado passou a vir sem os campos que o parser usa para extrair IDs de videos.

O codigo em si nao estava diferente. O que mudou foi o formato da resposta do YouTube para aquele ambiente.

## Correcao aplicada

Arquivo alterado: `monitor.py`

### Mudancas

1. Nova funcao `_extract_video_ids_from_channel_feed(channel_id, limit=30)`
- Consulta `https://www.youtube.com/feeds/videos.xml?channel_id=...`
- Extrai `<yt:videoId>...`
- Deduplica IDs

2. `list_live_videos_any(...)` ganhou etapa `D`:
- Depois dos caminhos HTML, adiciona IDs recentes vindos do feed XML.
- Mantem validacao final via `is_live_now(...)` antes de considerar live ativa.

3. Ajuste de encerramento/falso positivo:
- O fallback de chat (`fallback chat ativo`) deixou de rodar para IDs vindos do feed XML.
- Agora esse fallback so roda para IDs encontrados em fontes de "live" (`live_view=501`, `/streams`, `/live`).
- Motivo: video encerrado pode aparecer no feed recente e ainda ter chat replay, mantendo live "presa" como ativa com audiencia `0`.

4. Ajuste para detectar novas lives mais cedo (tempo real):
- `_extract_live_video_ids_from_html(...)` ficou mais tolerante a marcadores `AO VIVO` e estilos `LIVE_*`.
- Novo fallback `_extract_live_video_ids_from_html_loose(...)`:
  - procura `videoId` perto de sinais de live no HTML bruto (`isLiveNow`, `live_now`, `ao vivo`, `assistindo`, etc.).
- Em `/streams` e home:
  - evita poluir candidatos com muitos `videoId` genericos quando ja existem candidatos de live.
- Limites de candidatos ajustados para reduzir ruído e acelerar confirmacao:
  - feed XML limitado,
  - lista final de candidatos reduzida para verificacao.
- Cadencia do supervisor reduzida para varrer mais frequente:
  - `SUPERVISOR_POLL_SECONDS: 15 -> 8`.

## Por que resolve

Mesmo quando a pagina HTML vier sem `videoId`, o feed XML costuma continuar listando os uploads/recentes do canal. A validacao `is_live_now` filtra os que realmente estao ao vivo.

## Comandos uteis de verificacao (VM)

```bash
ssh -i ~/.ssh/monitor_vm monitor-cazetv@35.184.93.23
sudo systemctl status monitor-cazetv.service --no-pager -l
sudo journalctl -u monitor-cazetv.service -n 120 --no-pager
```

### Teste rapido de discovery na VM

```bash
cd /home/monitor-cazetv/monitor
/home/monitor-cazetv/monitor/venv/bin/python3 -c "import monitor; print(monitor.list_live_videos_any('@CazeTV','',max_results=20))"
```

## Deploy para VM (se necessario)

```bash
scp -i ~/.ssh/monitor_vm monitor.py monitor-cazetv@35.184.93.23:/home/monitor-cazetv/monitor/monitor.py
ssh -i ~/.ssh/monitor_vm monitor-cazetv@35.184.93.23 "sudo systemctl restart monitor-cazetv.service"
```

## Risco residual

- Se o feed XML atrasar alguns minutos, pode haver pequeno delay para detectar live nova.
- A validacao `is_live_now` continua sendo o gate final, evitando falso positivo por feed.
- Ainda pode existir pequena janela logo apos encerramento, mas bem menor sem fallback de chat para IDs do feed.
