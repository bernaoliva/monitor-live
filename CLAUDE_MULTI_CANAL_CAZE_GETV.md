# Multi-Canal: CAZETV + GETV

> Ultima atualizacao: 2026-02-23

## Objetivo

Replicar o monitor atual para dois canais no mesmo projeto:
- Aba `CAZETV` (como ja estava)
- Aba `GETV`

## Mudancas aplicadas

### 1) Backend monitor (VM)

Arquivo: `monitor.py`

- Adicionado segundo canal em `CHANNELS`:
  - `CAZETV` (`@CazeTV`)
  - `GETV` (`@GETV`, `UCgCKagVhzGnZcuP9bSMgMCg`)
- Ajustado multiprocessing no `__main__`:
  - Linux usa `fork`
  - Windows usa `spawn`
- Motivo: com `spawn` na VM, o segundo monitor estava falhando com:
  - `FileNotFoundError` em `multiprocessing.synchronize.SemLock._rebuild`
- Com `fork`, os dois monitores sobem juntos e o chat da GETV passa a gravar normalmente.

### 2) Frontend dashboard

Arquivo: `dashboard/app/page.tsx`

- Adicionadas abas de canal:
  - `CAZETV`
  - `GETV`
- Cada aba mostra apenas as lives daquele canal.
- Contador por aba exibido no botao.
- Aba selecionada persiste em `localStorage` (`channel_tab`).

## Deploy aplicado

### VM

```bash
scp -i ~/.ssh/monitor_vm monitor.py USUARIO@IP_DA_VM:/home/monitor-cazetv/monitor/monitor.py
ssh -i ~/.ssh/monitor_vm USUARIO@IP_DA_VM "sudo systemctl restart monitor-cazetv.service"
```

### Dashboard (Vercel)

Deploy:
- `https://dashboard-6jv8hcw91-bernardos-projects-416180bb.vercel.app`

Alias atualizado:
- `https://monitor-cazetv.vercel.app`

## Validacao

- Logs mostram:
  - supervisor `CAZETV` e `GETV` iniciando.
  - viewer_count para ambos.
- Firestore `lives/DoHhD-HCBik` (GETV):
  - `channel=GETV`
  - `total_comments` e `last_seen_at` avancando
  - novos comments com `ts` recente.

## Commit sugerido

```bash
git add monitor.py dashboard/app/page.tsx CLAUDE_MULTI_CANAL_CAZE_GETV.md
git commit -m "feat: adiciona monitor e aba para GETV junto com CAZETV"
git push
```

## Observacao

- Existe mudanca local em `dashboard/app/live/[id]/page.tsx` que nao faz parte deste escopo.
