# Dashboard - Fix de Pulsar e Dismiss no Grafico

> Ultima atualizacao: 2026-02-20

## Problemas reportados

1. O efeito de "pulsar/flash" ao chegar problema tecnico novo parou.
2. Ao clicar no `X` para descartar comentario tecnico, o ponto nao sumia do grafico.

## Causa raiz

### 1) Pulsar
- Em `LiveCard`, o flash era disparado comparando apenas `visibleComments.length`.
- Quando o volume ficava estavel (ou voltava de 0 para 1 em cenarios especificos), o trigger podia nao disparar.

### 2) Grafico
- O grafico do card usa a subcolecao `minutes/` (`technical` por minuto).
- O dismiss mudava `comments.is_technical=false` e decrementava `technical_comments`, mas **nao** ajustava `minutes/{HH:mm}.technical`.

## Correcao aplicada

### Arquivo: `dashboard/components/LiveCard.tsx`
- Trigger de flash trocado para evento real de chegada:
  - `onSnapshot(...).docChanges()` com `type === "added"` (ignora snapshot inicial).
- No dismiss:
  - ajuste otimista local do `chartData` (remove 1 do minuto do comentario),
  - persistencia no Firestore em `lives/{video}/minutes/{HH:mm}` com `technical: increment(-1)`.
- Ajuste de consistencia da view principal:
  - contador "Problemas" do card agora usa `visibleComments.length` (nao `live.technical_comments`),
  - serie tecnica do grafico do card passa a ser derivada dos comentarios tecnicos visiveis por minuto (evita drift quando agregados ficam defasados).

### Arquivo: `dashboard/app/live/[id]/page.tsx`
- Mesmo ajuste de persistencia do dismiss:
  - ao descartar, tambem decrementa `minutes/{HH:mm}.technical`.
- Mantem consistencia entre tela de detalhe, card da home e historico.

## Deploy

- Deploy realizado em producao.
- URL de producao:
  - `https://dashboard-qqav5i1zo-bernardos-projects-416180bb.vercel.app`
- Alias atualizado:
  - `https://monitor-cazetv.vercel.app`

## Validacao esperada

1. Entrando novo comentario tecnico: card volta a piscar.
2. Clicar `X` em comentario tecnico: linha tecnica do grafico reduz no minuto correspondente (quase imediato).
3. Home, detalhe e historico ficam coerentes apos dismiss.
