# Handoff pronto para Claude (assumir e commitar)

> Data: 2026-02-23

## Escopo entregue ate agora

### Backend (`monitor.py`)
- Monitor multi-canal: `CAZETV` + `GETV`.
- Em Linux usa `fork` (evita erro `SemLock/FileNotFoundError` no segundo processo).
- Ajustes de tempo real:
  - chat com `ts` normalizado em ISO para nao quebrar ordenacao;
  - coleta de audiencia com parser mais robusto de `ytInitialData`;
  - atualizacao de `minutes/` e feed tecnico consistente.

### Frontend
- `dashboard/app/page.tsx`
  - seletor por logo com multi-selecao (sem botao "TODOS");
  - botoes de canal movidos para o header, ao lado de "Painel de Controle";
  - se marcar os 2 canais, mostra todas as lives; se desmarcar tudo, estado vazio.
- `dashboard/components/LiveCard.tsx`
  - logo do canal ao lado do link/botao `YOUTUBE`;
  - tamanho da GETV reduzido no card para ficar proporcional.
- `dashboard/public/getv-logo.png`
  - asset usado no seletor e no card.

### Deploy ja aplicado
- URL ativa: `https://monitor-cazetv.vercel.app`

## Arquivos para commit (somente estes)

- `monitor.py`
- `dashboard/app/page.tsx`
- `dashboard/components/LiveCard.tsx`
- `dashboard/public/getv-logo.png`
- `CLAUDE_FIX_CHAT_AUDIENCIA_REALTIME.md`
- `CLAUDE_MULTI_CANAL_CAZE_GETV.md`
- `CLAUDE_FILTRO_CANAIS_LOGOS.md`
- `CLAUDE_HANDOFF_AGORA.md`

## Arquivos para NAO incluir

- `dashboard/app/live/[id]/page.tsx` (mudanca paralela pre-existente)
- `CAZÉTV_BRANCO.png`, `GE_TV_logo.png`, `cazetv-logo.png` (fontes locais)
- scripts auxiliares e datasets (`*.csv`, `extract_comments.py`, `relabel_with_claude.py`, etc.)

## Passo a passo (Claude)

```bash
git status --short
```

```bash
git add monitor.py dashboard/app/page.tsx dashboard/components/LiveCard.tsx dashboard/public/getv-logo.png CLAUDE_FIX_CHAT_AUDIENCIA_REALTIME.md CLAUDE_MULTI_CANAL_CAZE_GETV.md CLAUDE_FILTRO_CANAIS_LOGOS.md CLAUDE_HANDOFF_AGORA.md
git commit -m "feat: consolida monitor multi-canal e ajustes de UX no dashboard"
git push origin main
```

## Verificacao rapida depois do push

```bash
git show --name-only --oneline -1
```

Conferir que `dashboard/app/live/[id]/page.tsx` NAO entrou.
