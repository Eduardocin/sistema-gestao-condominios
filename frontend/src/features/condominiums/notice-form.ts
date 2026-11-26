export interface NoticeFormValues {
  titulo: string
  texto: string
  inicio: string
  fim: string
  importante: boolean
  responsavelId: string
}

export type NoticePayloadResult =
  | {
      ok: true
      payload: {
        titulo: string
        texto: string
        inicio_em: string
        fim_em: string
        importante: boolean
        responsavel_id: string
      }
    }
  | { ok: false; message: string }

export const NOTICE_PERIOD_ERROR = 'A data de término deve ser posterior ao início.'

/** Converte um instante ISO no valor de um `datetime-local` (horário local, sem fuso). */
export function localDate(value: string): string {
  const date = new Date(value)
  const pad = (part: number) => String(part).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function buildNoticePayload(values: NoticeFormValues): NoticePayloadResult {
  const start = new Date(values.inicio)
  const end = new Date(values.fim)
  if (
    !values.inicio ||
    !values.fim ||
    Number.isNaN(start.getTime()) ||
    Number.isNaN(end.getTime()) ||
    end <= start
  ) {
    return { ok: false, message: NOTICE_PERIOD_ERROR }
  }
  return {
    ok: true,
    payload: {
      titulo: values.titulo.trim(),
      texto: values.texto.trim(),
      inicio_em: start.toISOString(),
      fim_em: end.toISOString(),
      importante: values.importante,
      responsavel_id: values.responsavelId,
    },
  }
}
