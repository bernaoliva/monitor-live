# Regras de Commit para Atualizar o Projeto no GitHub

Este arquivo define **o que deve entrar em commit** para manter o projeto atualizado com qualidade.

## Objetivo

Sempre que uma tarefa estiver concluida e validada, gerar commit e push com foco no **resultado da mudanca**, nao no caminho/estrutura de pastas.

## Como decidir o que commitar

Agrupar por **tema de produto**:

1. Monitoramento de lives (deteccao, estabilidade, audiencia, historico)
2. Dashboard e visualizacao (UI, UX, interacoes, graficos)
3. Infra e deploy (scripts, ajustes operacionais)
4. Documentacao e contexto operacional

Cada commit deve tratar **um unico tema**.

## O que deve entrar no commit

- Arquivos que implementam diretamente a mudanca aprovada.
- Ajustes tecnicos necessarios para essa mesma mudanca funcionar.
- Documentacao da mudanca quando houver alteracao de comportamento.

## O que nao deve entrar no commit

- Credenciais, chaves, tokens, arquivos locais sensiveis.
- Logs temporarios, cache, arquivos gerados sem relevancia de codigo.
- Mudancas paralelas nao relacionadas ao tema do commit.

## Politica de mensagem de commit

Usar mensagem curta e clara, descrevendo efeito real:

- `fix: corrige detecao de live encerrada na nuvem`
- `feat: adiciona destaque visual para novos problemas tecnicos`
- `chore: ajusta fluxo operacional de deploy`
- `docs: atualiza guia de operacao da VM`

## Politica de push

Quando o usuario pedir para atualizar GitHub:

1. Conferir que a mudanca foi validada.
2. Commitar somente o tema aprovado.
3. Fazer push para `main`.
4. Informar no final:
   - hash curto do commit
   - resumo do que mudou
   - impacto esperado no projeto

## Regra de qualidade

Se houver mudancas de backend e frontend no mesmo pedido, preferir **2 commits separados** (um por tema), salvo instrucao explicita para consolidar em 1 commit.
