# Monitor de Lives — Status do Projeto

> Ultima atualizacao: 2026-02-23

---

## Estado atual (producao)

| Componente | Status | URL / Acesso |
|---|---|---|
| Monitor VM | Rodando | `ssh -i ~/.ssh/monitor_vm USUARIO@IP_DA_VM` |
| Dashboard | Deploy ativo | https://monitor-cazetv.vercel.app |
| Classificador IA | Rodando | Cloud Run GPU (T4) — us-central1 |
| Firestore | Ativo | Projeto `monitor-cazetv` |

---

## Canais monitorados

- **CAZETV** (`@CazeTV`)
- **GETV** (`@GETV` / `UCgCKagVhzGnZcuP9bSMgMCg`)

---

## Ultimas entregas (cronologico)

| Data | O que foi feito |
|---|---|
| 2026-02-20 | Monitor multi-canal CAZETV + GETV; fix live discovery via feed XML |
| 2026-02-22 | Fix timezone BRT nos timestamps do chat; fix audiencia sem API key |
| 2026-02-22 | Multiprocessing com fork no Linux (evita SemLock no segundo monitor) |
| 2026-02-23 | Seletor de canal por logo no dashboard; logo do canal no LiveCard |

---

## Pendencias tecnicas

- [ ] **Feed "ultimas 3000 msgs"** (`/live/[id]`) — feed nao atualiza em tempo real apos fix do limitToLast. Investigar se o problema persiste com os novos timestamps ISO/BRT do monitor.
- [ ] **Comentarios expandiveis no LiveCard** — 8 recentes expandidos + botao "+N anteriores" colapsados. Ver plano: `C:\Users\Admin\.claude\plans\cheerful-crafting-badger.md`
- [ ] **Reduzir falsos positivos no keyword fallback** — `caiu`, `travand`, `placar` gerando classificacoes erradas. Ver plano: `C:\Users\Admin\.claude\plans\sorted-foraging-scott.md`
- [ ] Validar monitor ao vivo na proxima transmissao CazeTV/GETV

---

## Operacoes comuns

### Deploy dashboard (Vercel)
```bash
cd dashboard && npx vercel --prod
npx vercel alias <deployment-url> monitor-cazetv.vercel.app
```

### Atualizar monitor na VM
```bash
# 1. Garantir que SERVING_URL esta como placeholder no arquivo local antes do scp
scp -i ~/.ssh/monitor_vm monitor.py USUARIO@IP_DA_VM:/home/monitor-cazetv/monitor/monitor.py
# 2. Restaurar URL real na VM
ssh -i ~/.ssh/monitor_vm USUARIO@IP_DA_VM "sed -i 's|SUA_URL_CLOUD_RUN|https://SUA_URL_CLOUD_RUN|' /home/monitor-cazetv/monitor/monitor.py"
# 3. Reiniciar servico
ssh -i ~/.ssh/monitor_vm USUARIO@IP_DA_VM "sudo systemctl restart monitor-cazetv.service"
```

### Verificar logs da VM
```bash
ssh -i ~/.ssh/monitor_vm USUARIO@IP_DA_VM "sudo journalctl -u monitor-cazetv.service -n 80 --no-pager"
```

### Commit e push
```bash
git add <arquivos> && git commit -m "<mensagem>" && git push origin main
# Verificar resultado:
git show --name-only --oneline -1
```

---

## Observacoes importantes

- `firebase.ts` e `monitor.py` tem **skip-worktree** ativo — valores locais sao reais, git ve placeholders
- Ao fazer `scp` do `monitor.py`, o `SERVING_URL` vira placeholder — restaurar com o `sed` acima
- `CLAUDE.md` esta no `.gitignore` — nao vai para o GitHub
- Repositorio publico: https://github.com/bernaoliva/monitor-live
