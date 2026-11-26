/**
 * Telas de suporte, comunicados e relatório de encomendas (TASK-61 e TASK-62).
 * Ficam desligadas por padrão até a validação: com `VITE_SUPPORT_SCREENS=true` no ambiente
 * do front, as rotas, o menu lateral e os atalhos da visão geral aparecem.
 */
export const supportScreensEnabled = import.meta.env.VITE_SUPPORT_SCREENS === 'true'
