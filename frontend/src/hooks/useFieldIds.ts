import { useId } from 'react'

/**
 * Gera os ids que ligam um campo ao seu label, dica e mensagem de erro,
 * para leitores de tela anunciarem tudo junto (aria-describedby).
 */
export function useFieldIds(idProp?: string, hint?: string, error?: string) {
  const generatedId = useId()
  const id = idProp ?? generatedId
  const hintId = hint ? `${id}-hint` : undefined
  const errorId = error ? `${id}-error` : undefined
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined

  return { id, hintId, errorId, describedBy, invalid: Boolean(error) }
}
