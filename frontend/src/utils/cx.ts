/** Junta nomes de classe ignorando valores vazios (substitui concatenação manual). */
export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ')
}
