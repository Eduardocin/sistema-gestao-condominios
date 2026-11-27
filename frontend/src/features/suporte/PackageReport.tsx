import { useCallback, useState } from 'react'
import type { FormEvent } from 'react'
import { Button, Card, Input, MetricCard, Notice, Table, Text } from '../../components'
import { CommunityLoadError } from '../resident/ResidentCommunity'
import styles from '../resident/ResidentWorkspace.module.css'
import { reportPeriodError } from './suporte-api.ts'
import type { PackageReportFilters, SupportClient } from './suporte-api.ts'
import { useSupportQuery } from './support-state.ts'

const headers = [
  'Unidade',
  'Registradas',
  'Aguardando retirada',
  'Aguardando confirmação',
  'Retiradas',
]

function periodText({ de, ate }: { de: string | null; ate: string | null }) {
  const format = (date: string) => new Date(`${date}T12:00:00`).toLocaleDateString('pt-BR')
  if (de && ate) return `De ${format(de)} a ${format(ate)}`
  if (de) return `A partir de ${format(de)}`
  if (ate) return `Até ${format(ate)}`
  return 'Todo o período'
}

/** Relatório de encomendas da Administração (US-404): contagem por status, no total e por unidade. */
export function PackageReportView({ api }: { api: SupportClient }) {
  const [draft, setDraft] = useState<PackageReportFilters>({})
  const [filters, setFilters] = useState<PackageReportFilters>({})
  const [error, setError] = useState('')
  const { result, reload } = useSupportQuery(
    useCallback((signal) => api.packageReport(filters, signal), [api, filters]),
  )
  const report = result?.data

  function apply(event: FormEvent) {
    event.preventDefault()
    const problem = reportPeriodError(draft)
    setError(problem)
    if (!problem) setFilters(draft)
  }

  return (
    <>
      <form className={styles.filters} onSubmit={apply} aria-label="Período do relatório">
        <Input
          label="De"
          type="date"
          value={draft.data_de ?? ''}
          onChange={(event) => setDraft({ ...draft, data_de: event.target.value })}
        />
        <Input
          label="Até"
          type="date"
          value={draft.data_ate ?? ''}
          onChange={(event) => setDraft({ ...draft, data_ate: event.target.value })}
        />
        <div className={styles.actions}>
          <Button type="submit">Filtrar</Button>
          <Button
            variant="secondary"
            onClick={() => {
              setDraft({})
              setFilters({})
              setError('')
            }}
          >
            Limpar período
          </Button>
        </div>
      </form>
      {error && (
        <Notice tone="alert" role="alert">
          {error}
        </Notice>
      )}
      {!result && <Text role="status">Carregando relatório…</Text>}
      {result?.error && <CommunityLoadError retry={reload}>{result.error}</CommunityLoadError>}
      {report && (
        <>
          <Text tone="secondary">{periodText(report.periodo)}</Text>
          <div className={styles.tools}>
            <MetricCard
              label="Registradas"
              value={report.totais.registradas}
              description="Chegaram ao condomínio"
            />
            <MetricCard
              label="Aguardando retirada"
              value={report.totais.aguardando_retirada}
              description="Ainda na portaria"
              tone="warning"
            />
            <MetricCard
              label="Aguardando confirmação"
              value={report.totais.entregue_aguardando_confirmacao}
              description="Entregues, sem confirmação do morador"
              tone="warning"
            />
            <MetricCard
              label="Retiradas"
              value={report.totais.retirada_confirmada}
              description="Confirmadas pelo morador"
              tone="success"
            />
          </div>
          <Card>
            <Table
              caption="Encomendas por unidade"
              headers={headers}
              emptyMessage="Nenhuma encomenda no período."
              rows={report.por_unidade.map((row) => [
                row.unidade.identificacao,
                row.registradas,
                row.aguardando_retirada,
                row.entregue_aguardando_confirmacao,
                row.retirada_confirmada,
              ])}
            />
          </Card>
        </>
      )}
    </>
  )
}
