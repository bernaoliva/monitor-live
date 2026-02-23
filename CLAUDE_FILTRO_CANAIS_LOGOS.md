# Filtro de canais com logos (estado atual)

> Data: 2026-02-23

## Objetivo

Melhorar visualizacao no topo do dashboard sem ocupar area dos cards:
- selecao por logo de canal;
- botoes ao lado de "Painel de Controle";
- logo do canal visivel dentro do card ao lado do link `YOUTUBE`.

## Arquivos alterados

- `dashboard/app/page.tsx`
  - seletor multi-canal por logo (`CAZETV` e `GETV`);
  - sem botao "TODOS";
  - persistencia em `localStorage` (`channel_selected`);
  - seletor movido para o header (mesma linha do titulo).
- `dashboard/components/LiveCard.tsx`
  - logo do canal reposicionada ao lado de `YOUTUBE`;
  - ajuste de tamanho no card:
    - CAZETV: `60x18`
    - GETV: `48x14`
- `dashboard/public/getv-logo.png`
  - logo usada no seletor e no card.

## Comportamento final

- Clique em uma logo ativa/desativa o canal.
- Com as duas ativas: mostra todas as lives.
- Com uma ativa: mostra somente aquele canal.
- Com nenhuma ativa: mostra estado vazio pedindo selecao.
- Sem caixa/borda de botao em volta da logo (somente logo + indicador inferior quando selecionada).

## Deploy aplicado

- URL atual:
  - `https://monitor-cazetv.vercel.app`

## Commit sugerido (parte de UI)

```bash
git add dashboard/app/page.tsx dashboard/components/LiveCard.tsx dashboard/public/getv-logo.png CLAUDE_FILTRO_CANAIS_LOGOS.md
git commit -m "feat: ajusta seletor por logos e layout dos cards por canal"
git push origin main
```

## Nao incluir neste commit

- `dashboard/app/live/[id]/page.tsx` (mudanca paralela)
- arquivos de treino/backfill (`*.csv`, scripts auxiliares)
- logos-fonte fora de `dashboard/public/`
