import { useEffect } from 'react'

/** Mantém o teclado no conteúdo quando uma lista, formulário ou diálogo é substituído. */
export function useContentFocus(titleId: string, enabled = true) {
  useEffect(() => {
    if (enabled) document.getElementById(titleId)?.focus()
  }, [titleId, enabled])
}
