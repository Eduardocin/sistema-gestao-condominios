import { useCallback, useId, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router'
import {
  Badge,
  Button,
  Card,
  Heading,
  Input,
  Modal,
  Notice,
  Select,
  Table,
  Text,
  Toast,
} from '../../components'
import { FormField } from '../../components/FormField'
import fieldStyles from '../../components/FormField.module.css'
import { useAuth } from '../auth/context'
import { createAdminAreasClient } from './admin-areas-api'
import type { AdminAreasClient, AdminReservation, Responsible } from './admin-areas-api'
import { adminErrorMessage, errorStatus, isConflict } from './admin-errors'
import { AdminAreasShell } from './AdminAreasShell'
import {
  EMPTY_FILTERS,
  REASON_MAX,
  buildReservationParams,
  condoNow,
  formatDate,
  formatDateTime,
  isCancellable,
  validateCancellation,
} from './reservation-admin'
import type { ReservationFilters } from './reservation-admin'
import { useAdminQuery } from './use-admin-query'
import styles from './AdminAreas.module.css'

// O Select do design system trava a opção vazia (placeholder); "todas" usa um valor próprio.
const ALL = '*'
const statusOptions = [
  { value: ALL, label: 'Todos' },
  { value: 'ativa', label: 'Ativas' },
  { value: 'cancelada', label: 'Canceladas' },
]

export function AdminReservationsPage() {
  return (
    <AdminAreasShell activeKey="reservations">
      <ReservationsContent />
    </AdminAreasShell>
  )
}

function ReservationsContent() {
  const { client } = useAuth()
  const api = useMemo(() => createAdminAreasClient(client.http), [client])
  const [draft, setDraft] = useState<ReservationFilters>(EMPTY_FILTERS)
  const [applied, setApplied] = useState<ReservationFilters>(EMPTY_FILTERS)
  const [filterError, setFilterError] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<AdminReservation | null>(null)
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState('')
  const [error, setError] = useState('')

  const options = useAdminQuery(
    useCallback(
      (signal: AbortSignal) => Promise.all([api.allAreas(signal), api.units(signal)]),
      [api],
    ),
  )
  // Separado dos filtros: recarregar responsáveis (ex.: após um 404) não mexe nos selects.
  const responsibles = useAdminQuery(
    useCallback((signal: AbortSignal) => api.activeResponsibles(signal), [api]),
  )
  const reservations = useAdminQuery(
    useCallback(
      (signal: AbortSignal) => {
        const query = buildReservationParams(applied, page)
        // Os filtros aplicados já passaram pela validação; aqui é só defesa.
        if (!query.ok) return Promise.reject(new Error(query.message))
        return api.reservations(query.params, signal)
      },
      [api, applied, page],
    ),
  )
  const list = reservations.result?.data
  const pages = list ? Math.max(1, Math.ceil(list.total / list.page_size)) : 1
  const [areas, units] = options.result?.data ?? [[], []]
  const now = condoNow()

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const query = buildReservationParams(draft)
    if (!query.ok) {
      setFilterError(query.message)
      return
    }
    setFilterError('')
    setError('')
    setApplied(draft)
    setPage(1)
  }

  function clearFilters() {
    setDraft(EMPTY_FILTERS)
    setApplied(EMPTY_FILTERS)
    setFilterError('')
    setError('')
    setPage(1)
  }

  function update(field: keyof ReservationFilters, value: string) {
    setDraft((current) => ({ ...current, [field]: value === ALL ? '' : value }))
  }

  return (
    <>
      <div>
        <Badge variant="primary">Administração</Badge>
        <Heading level={1}>Reservas</Heading>
        <Text tone="secondary">
          Consulte as reservas de todas as áreas do condomínio e cancele, com motivo, as que ainda
          não começaram. A unidade recebe um aviso com o motivo.
        </Text>
      </div>
      {error && (
        <Notice tone="alert" role="alert">
          {error}
        </Notice>
      )}
      <Card>
        <Heading level={2} size="md">
          Filtros
        </Heading>
        {options.result?.error && (
          <Notice tone="alert" role="alert">
            Não foi possível carregar áreas e unidades. {options.result.error}
            <div className={styles.actions}>
              <Button size="sm" onClick={options.reload}>
                Tentar novamente
              </Button>
            </div>
          </Notice>
        )}
        {!options.result && (
          <Text size="sm" tone="secondary" role="status">
            Carregando áreas e unidades para os filtros…
          </Text>
        )}
        <form className={styles.filters} onSubmit={applyFilters} aria-label="Filtrar reservas">
          <Select
            label="Área"
            value={draft.areaId || ALL}
            options={[
              { value: ALL, label: 'Todas as áreas' },
              ...areas.map((area) => ({
                value: area.id,
                label: area.ativa ? area.nome : `${area.nome} (desativada)`,
              })),
            ]}
            onChange={(event) => update('areaId', event.target.value)}
          />
          <Select
            label="Unidade"
            value={draft.unidadeId || ALL}
            options={[
              { value: ALL, label: 'Todas as unidades' },
              ...units.map((unit) => ({ value: unit.id, label: unit.identificacao })),
            ]}
            onChange={(event) => update('unidadeId', event.target.value)}
          />
          <Input
            label="De"
            type="date"
            value={draft.dataDe}
            max={draft.dataAte || undefined}
            onChange={(event) => update('dataDe', event.target.value)}
          />
          <Input
            label="Até"
            type="date"
            value={draft.dataAte}
            min={draft.dataDe || undefined}
            onChange={(event) => update('dataAte', event.target.value)}
          />
          <Select
            label="Status"
            value={draft.status || ALL}
            options={statusOptions}
            onChange={(event) => update('status', event.target.value)}
          />
          <Button type="submit" variant="secondary">
            Filtrar
          </Button>
          <Button variant="secondary" onClick={clearFilters}>
            Limpar
          </Button>
        </form>
        {filterError && (
          <Notice tone="alert" role="alert">
            {filterError}
          </Notice>
        )}
      </Card>
      <Card>
        <div className={styles.header}>
          <Heading level={2} size="md">
            Reservas do condomínio
          </Heading>
        </div>
        {reservations.result?.error ? (
          <Notice tone="alert" role="alert">
            {reservations.result.error}
            <div className={styles.actions}>
              <Button size="sm" onClick={reservations.reload}>
                Tentar novamente
              </Button>
            </div>
          </Notice>
        ) : !list ? (
          <Text role="status">Carregando reservas…</Text>
        ) : (
          <>
            <Table
              className={styles.reservationsTable}
              caption="Reservas das áreas comuns"
              headers={[
                'Área',
                'Unidade',
                'Data',
                'Horário',
                'Status',
                'Reservada por',
                'Cancelamento',
                'Ação',
              ]}
              emptyMessage="Nenhuma reserva encontrada com esses filtros."
              rows={list.items.map((reservation) => [
                reservation.area.nome,
                reservation.unidade.identificacao,
                formatDate(reservation.data),
                `${reservation.hora_inicio} às ${reservation.hora_fim}`,
                <StatusBadge reservation={reservation} now={now} />,
                reservation.reservada_por?.nome ?? '—',
                <CancellationDetails reservation={reservation} />,
                isCancellable(reservation, now) ? (
                  <Button
                    size="sm"
                    variant="alert"
                    aria-label={`Cancelar reserva de ${reservation.area.nome}, unidade ${reservation.unidade.identificacao}, ${formatDate(reservation.data)} às ${reservation.hora_inicio}`}
                    onClick={() => {
                      setError('')
                      setSelected(reservation)
                    }}
                  >
                    Cancelar
                  </Button>
                ) : (
                  '—'
                ),
              ])}
            />
            {list.total > 0 && (
              <div className={styles.pagination}>
                <Text size="sm">
                  Página {list.page} de {pages} · {list.total}{' '}
                  {list.total === 1 ? 'reserva' : 'reservas'}
                </Text>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                >
                  Anterior
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={page >= pages}
                  onClick={() => setPage(page + 1)}
                >
                  Próxima
                </Button>
              </div>
            )}
          </>
        )}
      </Card>
      <Modal
        isOpen={!!selected}
        title="Cancelar reserva"
        onClose={() => {
          if (!busy) setSelected(null)
        }}
      >
        {selected && (
          <CancelReservation
            key={selected.id}
            api={api}
            reservation={selected}
            responsibles={responsibles.result?.data}
            responsiblesError={responsibles.result?.error}
            onRetryResponsibles={responsibles.reload}
            onBusy={setBusy}
            onClose={() => setSelected(null)}
            onDone={() => {
              setSelected(null)
              setToast('Reserva cancelada. A unidade recebeu um aviso com o motivo.')
              reservations.reload()
            }}
            onStale={(message) => {
              // Já cancelada ou já começou: a linha estava velha. Fecha e atualiza a lista.
              setSelected(null)
              setError(message)
              reservations.reload()
            }}
          />
        )}
      </Modal>
      <Toast message={toast} isVisible={!!toast} onClose={() => setToast('')} />
    </>
  )
}

function StatusBadge({ reservation, now }: { reservation: AdminReservation; now: string }) {
  if (reservation.status === 'cancelada') return <Badge variant="neutral">Cancelada</Badge>
  return isCancellable(reservation, now) ? (
    <Badge variant="success">Ativa</Badge>
  ) : (
    <Badge variant="primary" wrap>
      Ativa · horário iniciado
    </Badge>
  )
}

function CancellationDetails({ reservation }: { reservation: AdminReservation }) {
  const cancellation = reservation.cancelamento
  if (!cancellation) return '—'
  const byAdmin = cancellation.por === 'administracao'
  return (
    <span>
      {byAdmin ? 'Pela administração' : 'Pelo morador'} em {formatDateTime(cancellation.em)}
      {cancellation.responsavel && (
        <>
          <br />
          Responsável: {cancellation.responsavel.nome}
        </>
      )}
      {cancellation.motivo && (
        <>
          <br />
          Motivo: <span className={styles.preserveLines}>{cancellation.motivo}</span>
        </>
      )}
    </span>
  )
}

function CancelReservation({
  api,
  reservation,
  responsibles,
  onBusy,
  onClose,
  onDone,
  onStale,
  responsiblesError,
  onRetryResponsibles,
}: {
  api: AdminAreasClient
  reservation: AdminReservation
  /** `undefined` enquanto carrega. */
  responsibles: Responsible[] | undefined
  responsiblesError: string | undefined
  onRetryResponsibles: () => void
  onBusy: (busy: boolean) => void
  onClose: () => void
  onDone: () => void
  onStale: (message: string) => void
}) {
  const reasonId = useId()
  const [reason, setReason] = useState('')
  const [responsibleId, setResponsibleId] = useState('')
  const [errors, setErrors] = useState<{ motivo?: string; responsavel?: string }>({})
  const [step, setStep] = useState<'form' | 'confirm'>('form')
  const [apiError, setApiError] = useState('')
  const [pending, setPending] = useState(false)
  const submitting = useRef(false)
  const responsibleName = responsibles?.find((person) => person.id === responsibleId)?.nome

  function review(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const result = validateCancellation({ motivo: reason, responsavelId: responsibleId })
    setApiError('')
    if (!result.ok) {
      setErrors(result.errors)
      return
    }
    setErrors({})
    setStep('confirm')
  }

  async function confirm() {
    const result = validateCancellation({ motivo: reason, responsavelId: responsibleId })
    if (!result.ok || submitting.current) return
    submitting.current = true
    setPending(true)
    onBusy(true)
    setApiError('')
    try {
      await api.cancelReservation(reservation.id, result.motivo, result.responsavelId)
      onDone()
    } catch (failure) {
      const message = adminErrorMessage(failure, 'cancelamento')
      if (isConflict(failure)) {
        onStale(message)
        return
      }
      // 404 aqui é, na prática, responsável desativado: recarrega a lista do select.
      if (errorStatus(failure) === 404) {
        setResponsibleId('')
        onRetryResponsibles()
      }
      setApiError(message)
      setStep('form')
    } finally {
      submitting.current = false
      setPending(false)
      onBusy(false)
    }
  }

  const summary = (
    <dl className={styles.summary}>
      <div>
        <dt>Área</dt>
        <dd>{reservation.area.nome}</dd>
      </div>
      <div>
        <dt>Unidade</dt>
        <dd>{reservation.unidade.identificacao}</dd>
      </div>
      <div>
        <dt>Data e horário</dt>
        <dd>
          {formatDate(reservation.data)}, {reservation.hora_inicio} às {reservation.hora_fim}
        </dd>
      </div>
      {reservation.reservada_por && (
        <div>
          <dt>Reservada por</dt>
          <dd>{reservation.reservada_por.nome}</dd>
        </div>
      )}
    </dl>
  )

  if (step === 'confirm')
    return (
      <div className={styles.form}>
        {summary}
        <Notice tone="warning" title="Confirmar cancelamento?">
          O horário será liberado e a unidade receberá um aviso com o motivo. Essa ação não pode ser
          desfeita.
        </Notice>
        <Text size="sm">
          <strong>Motivo:</strong> <span className={styles.preserveLines}>{reason.trim()}</span>
        </Text>
        <Text size="sm">
          <strong>Responsável:</strong> {responsibleName}
        </Text>
        {apiError && (
          <Notice tone="alert" role="alert">
            {apiError}
          </Notice>
        )}
        <div className={styles.actions}>
          <Button variant="alert" loading={pending} onClick={() => void confirm()}>
            Confirmar cancelamento
          </Button>
          <Button variant="secondary" disabled={pending} onClick={() => setStep('form')}>
            Voltar
          </Button>
        </div>
      </div>
    )

  const counterId = `${reasonId}-counter`
  return (
    <form className={styles.form} noValidate onSubmit={review}>
      {summary}
      <FormField
        id={reasonId}
        label="Motivo do cancelamento"
        required
        error={errors.motivo}
        errorId={`${reasonId}-error`}
      >
        <textarea
          id={reasonId}
          className={fieldStyles.control}
          rows={3}
          required
          maxLength={REASON_MAX}
          value={reason}
          aria-invalid={errors.motivo ? true : undefined}
          aria-describedby={[counterId, errors.motivo && `${reasonId}-error`]
            .filter(Boolean)
            .join(' ')}
          onChange={(event) => setReason(event.target.value)}
        />
      </FormField>
      <Text id={counterId} size="sm" tone="secondary" className={styles.counter}>
        {reason.length}/{REASON_MAX} caracteres
      </Text>
      <Select
        label="Responsável pelo cancelamento"
        required
        value={responsibleId}
        options={(responsibles ?? []).map((person) => ({ value: person.id, label: person.nome }))}
        error={errors.responsavel}
        disabled={!responsibles}
        onChange={(event) => setResponsibleId(event.target.value)}
      />
      {responsiblesError ? (
        <Notice tone="alert" role="alert">
          Não foi possível carregar os responsáveis. {responsiblesError}
          <div className={styles.actions}>
            <Button size="sm" onClick={onRetryResponsibles}>
              Tentar novamente
            </Button>
          </div>
        </Notice>
      ) : !responsibles ? (
        <Text size="sm" tone="secondary" role="status">
          Carregando responsáveis…
        </Text>
      ) : (
        !responsibles.length && (
          <Notice tone="warning">
            Nenhum responsável ativo. Cadastre um em{' '}
            <Link to="/app/administracao/funcionarios">Funcionários</Link> para cancelar reservas.
          </Notice>
        )
      )}
      {apiError && (
        <Notice tone="alert" role="alert">
          {apiError}
        </Notice>
      )}
      <div className={styles.actions}>
        <Button type="submit" variant="alert" disabled={!responsibles?.length}>
          Continuar
        </Button>
        <Button variant="secondary" onClick={onClose}>
          Voltar
        </Button>
      </div>
    </form>
  )
}
