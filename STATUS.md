# Monitor de Lives — Status do Projeto

> Ultima atualizacao: 2026-03-15

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
- **GETV** (`@GETV` / `SEU_CHANNEL_ID`)

---

## Ultimas entregas (cronologico)

| Data | O que foi feito |
|---|---|
| 2026-02-20 | Monitor multi-canal CAZETV + GETV; fix live discovery via feed XML |
| 2026-02-22 | Fix timezone BRT nos timestamps do chat; fix audiencia sem API key |
| 2026-02-22 | Multiprocessing com fork no Linux (evita SemLock no segundo monitor) |
| 2026-02-23 | Seletor de canal por logo no dashboard; logo do canal no LiveCard |
| 2026-03-11 | **Pos-mortem live XVvu1RXPRcw**: fix URL duplicada GPU, retry API, keyword override resiliente, regex melhorados |
| 2026-03-12 | **Health score redesenhado**: formula baseada em taxa (tech/total), fator de audiencia (chat pequeno pesa mais), peak penalty (pior janela 3min), recovery hibrido (sqrt minutos limpos). Correcao Firestore da live XVvu1RXPRcw (24 comentarios tecnicos restaurados). Historico: lazy load, cache localStorage, categoria SINC |
| 2026-03-15 | **Health score v3**: countPenalty por taxa/min (sqrt em vez de linear — concentrados pesam mais, espalhados menos), audienceFactor mais ingreme (4/log10, floor 0.4), recovery com threshold por audiencia (singles isolados = ruido). Live Cruzeiro x Vasco: 69→83 |

---

## Incidentes

### 2026-03-08 — Live XVvu1RXPRcw (Palmeiras x Novorizontino) — recall 21%

**Impacto**: De 52.001 comentarios, apenas 7 classificados como tecnicos. 26 comentarios tecnicos reais perdidos.

**Causa raiz 1 — URL GPU duplicada (CRITICO)**:
`SERVING_URL` na VM tinha `https://https://SEU_CLOUD_RUN.run.app` porque o `sed` de deploy adicionou `https://` sobre placeholder que ja incluia o prefixo. Resultado: 19.226 chamadas GPU falharam com `NameResolutionError` durante o pico (300k-2.76M viewers, ~23:16-01:37 BRT).

**Causa raiz 2 — keyword_override nao rodava com API falha**:
O `_keyword_override` estava dentro do bloco `if res:` no `_process_batch`. Quando a API retornava None (falha de rede), o keyword fallback simplesmente nao executava. Comentarios como "sem audio", "travando" que deveriam ser pegos por regex foram perdidos.

**Causa raiz 3 — regex muito rigidos**:
Padroes como `audio\s+ruim` nao matchavam "audio ta ruim" (palavra no meio). "borrado" so matchava com "imagem borrad". "bugou" nao tinha padrao.

**Correcoes aplicadas (2026-03-11)**:
1. URL VM corrigida manualmente
2. Placeholder mudou de `https://SUA_URL_CLOUD_RUN` para `SUA_URL_CLOUD_RUN` (previne duplicacao)
3. Validacao de URL no startup (autocorrige `https://https://`)
4. Retry simples (1 tentativa, 0.5s backoff) antes de desistir da API
5. Log de warning quando batch perde resultados da API
6. `_keyword_override` agora roda fora do `if res:` — funciona mesmo com API falha
7. Regex: audio+qualidade permite ate 3 palavras no meio, "borrado" isolado, "bugou" com contexto de stream
8. "bugou" removido de `_TECH_KEYWORDS` (giria generica) — regex exige contexto (live/transmissao/stream/tela)

**Resultado pos-fix**: 24/26 comentarios perdidos agora seriam capturados (92%). Os 2 restantes ("ta com delay", "esta com delay gol anulado") sao delay sem intensificador — risco alto de falso positivo em chat esportivo, modelo DistilBERT deve pegar esses.

**Correcao Firestore (2026-03-12)**: 24 comentarios tecnicos da live restaurados no Firestore com categoria/issue/severity corretos. Contadores `minutes/` e `issue_counts` do doc principal atualizados.

---

## Pendencias tecnicas

- [ ] **Feed "ultimas 3000 msgs"** (`/live/[id]`) — feed nao atualiza em tempo real apos fix do limitToLast. Investigar se o problema persiste com os novos timestamps ISO/BRT do monitor.
- [ ] **Comentarios expandiveis no LiveCard** — 8 recentes expandidos + botao "+N anteriores" colapsados. Ver plano: `C:\Users\Admin\.claude\plans\cheerful-crafting-badger.md`
- [x] ~~**Reduzir falsos positivos no keyword fallback**~~ — regex melhorados, keyword_override resiliente (2026-03-11)
- [x] ~~**Health score injusto para lives grandes**~~ — v3 deploy (2026-03-15): taxa/min, audienceFactor ingreme, recovery com threshold
- [ ] Validar monitor ao vivo na proxima transmissao CazeTV/GETV
- [ ] Deploy monitor.py atualizado na VM (fix bugou com contexto ainda nao enviado)

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
ssh -i ~/.ssh/monitor_vm USUARIO@IP_DA_VM "sed -i 's|SUA_URL_CLOUD_RUN|https://SEU_CLOUD_RUN.run.app|' /home/monitor-cazetv/monitor/monitor.py"
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
