// Validação do formulário de área comum espelhando o schema da API
// (backend/app/modules/reservas/schemas.py, AreaComumEntrada) e os limites de /arquivos/fotos.

export interface AreaPayload {
  nome: string
  foto_arquivo_id: string
  regras: string | null
  abre_as: string
  fecha_as: string
  capacidade: number
}

/** Campos já validados; falta só o id da foto, que vem do upload (ou da área, na edição). */
export type AreaFields = Omit<AreaPayload, 'foto_arquivo_id'>

export interface PhotoInfo {
  name: string
  type: string
  size: number
}

export interface AreaFormValues {
  nome: string
  regras: string
  abreAs: string
  fechaAs: string
  capacidade: string
  /** Arquivo escolhido agora; `null` quando o usuário não trocou a foto. */
  foto: PhotoInfo | null
  /** Foto atual da área (só na edição). */
  fotoAtualId?: string | null
}

export type AreaFormField = 'nome' | 'regras' | 'abre_as' | 'fecha_as' | 'capacidade' | 'foto'
export type AreaFormErrors = Partial<Record<AreaFormField, string>>

export type AreaFormResult =
  | { ok: true; fields: AreaFields }
  | { ok: false; errors: AreaFormErrors }

export const NAME_MAX = 100
export const RULES_MAX = 2000
export const CAPACITY_MAX = 32767
export const PHOTO_MAX_BYTES = 5 * 1024 * 1024
export const PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp']

// Mesmo padrão do backend: 00:00 a 23:00, sempre em hora cheia.
const FULL_HOUR = /^([01]\d|2[0-3]):00$/
// Extensões que o storage aceita para cada tipo (ele confere os dois).
const PHOTO_EXTENSIONS: Record<string, string[]> = {
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/png': ['.png'],
  'image/webp': ['.webp'],
}

/** Horas cheias oferecidas nos selects de abertura e fechamento. */
export const FULL_HOURS = Array.from(
  { length: 24 },
  (_, hour) => `${String(hour).padStart(2, '0')}:00`,
)

/** Conta caracteres como o Python (code points), para não divergir da API com emoji. */
export function charCount(value: string) {
  return [...value].length
}

export function photoError(photo: PhotoInfo): string | null {
  const name = photo.name.toLowerCase()
  const extensions = PHOTO_EXTENSIONS[photo.type]
  if (!extensions || !extensions.some((extension) => name.endsWith(extension)))
    return 'Use uma imagem JPG, PNG ou WebP.'
  if (photo.size === 0) return 'O arquivo da foto está vazio.'
  if (photo.size > PHOTO_MAX_BYTES) return 'A foto deve ter no máximo 5 MB.'
  return null
}

export function validateAreaForm(values: AreaFormValues): AreaFormResult {
  const errors: AreaFormErrors = {}
  const nome = values.nome.trim()
  const regras = values.regras.trim()

  if (!nome) errors.nome = 'Informe o nome da área.'
  else if (charCount(nome) > NAME_MAX) errors.nome = `Use no máximo ${NAME_MAX} caracteres.`

  if (charCount(regras) > RULES_MAX) errors.regras = `Use no máximo ${RULES_MAX} caracteres.`

  const abreValida = FULL_HOUR.test(values.abreAs)
  const fechaValida = FULL_HOUR.test(values.fechaAs)
  if (!abreValida) errors.abre_as = 'Escolha a abertura em hora cheia (ex.: 08:00).'
  if (!fechaValida) errors.fecha_as = 'Escolha o fechamento em hora cheia (ex.: 22:00).'
  // Com as duas horas cheias, "fecha > abre" já garante a janela mínima de 1 hora.
  if (abreValida && fechaValida && values.fechaAs <= values.abreAs)
    errors.fecha_as = 'O fechamento deve ser pelo menos 1 hora depois da abertura.'

  const capacidadeTexto = values.capacidade.trim()
  const capacidade = Number(capacidadeTexto)
  if (!/^\d+$/.test(capacidadeTexto) || capacidade < 1 || capacidade > CAPACITY_MAX)
    errors.capacidade = `Informe um número inteiro de 1 a ${CAPACITY_MAX}.`

  if (values.foto) {
    const problem = photoError(values.foto)
    if (problem) errors.foto = problem
  } else if (!values.fotoAtualId) {
    errors.foto = 'Envie uma foto da área.'
  }

  if (Object.keys(errors).length) return { ok: false, errors }
  return {
    ok: true,
    fields: {
      nome,
      // Regras vazias viram null: a API aceita a ausência, e não guardamos string em branco.
      regras: regras || null,
      abre_as: values.abreAs,
      fecha_as: values.fechaAs,
      capacidade,
    },
  }
}

export function buildAreaPayload(fields: AreaFields, fotoArquivoId: string): AreaPayload {
  return { ...fields, foto_arquivo_id: fotoArquivoId }
}
