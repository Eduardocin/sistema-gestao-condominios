import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
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
} from '../../components'
import { useAuth } from '../auth/context'
import type { Identity } from '../auth/types'
import { ResidentWorkspace } from './ResidentWorkspace'
import styles from './ResidentWorkspace.module.css'
import {
  createResidentVisitorsClient,
  residentVisitorError,
  visitorNameSearchError,
} from './resident-visitors-api'
import type {
  ResidentVisitor,
  ResidentVisitorData,
  ResidentVisitorQuery,
  ResidentVisitorsResult,
  ResidentVisitorStatus,
} from './resident-visitors-api'

type Unit = Identity['unidades'][number]
type Filters = Omit<ResidentVisitorQuery, 'unidade_id'>
type ListResponse = { request: Filters } & (
  | { state: 'ready'; data: ResidentVisitorsResult }
  | { state: 'error'; message: string }
)

type VisitorDialog =
  | { view: 'create' }
  | { view: 'loading'; id: string }
  | { view: 'error'; id: string; message: string }
  | { view: 'details' | 'edit' | 'cancel'; item: ResidentVisitor }

const statusOptions = [
  { value: 'todos', label: 'Todas as situações' },
  { value: 'vigentes', label: 'Vigentes' },
  { value: 'futuros', label: 'Futuros' },
  { value: 'encerrados', label: 'Encerrados' },
  { value: 'cancelados', label: 'Cancelados' },
]

const condoDate = new Intl.DateTimeFormat('sv-SE', { timeZone: 'America/Sao_Paulo' })

function formatDate(date: string) {
  return date.split('-').reverse().join('/')
}

function VisitorStatus({ item }: { item: ResidentVisitor }) {
  if (item.cancelado_em) return <Badge variant="alert">Cancelado</Badge>
  const today = condoDate.format(new Date())
  if (item.entrada_prevista > today) return <Badge variant="primary">Futuro</Badge>
  if (item.saida_prevista < today) return <Badge>Encerrado</Badge>
  return <Badge variant="success">Vigente</Badge>
}

export function ResidentVisitorsPage() {
  return (
    <ResidentWorkspace activeKey="visitors">
      <ResidentVisitors />
    </ResidentWorkspace>
  )
}

function ResidentVisitors() {
  const { snapshot } = useAuth()
  const units = (snapshot.identity?.unidades ?? []).filter((unit) => unit.abas?.includes('visitantes'))
  const [unitId, setUnitId] = useState('')
  const unit = units.find((item) => item.id === unitId) ?? units[0]

  return (
    <section className={styles.content} aria-labelledby="resident-visitors-title">
      <Heading level={1} id="resident-visitors-title">
        Meus visitantes
      </Heading>
      {units.length > 1 && (
        <div className={styles.filters}>
          <Select
            label="Unidade"
            value={unit?.id}
            options={units.map((item) => ({ value: item.id, label: item.identificacao }))}
            onChange={(event) => setUnitId(event.target.value)}
          />
        </div>
      )}
      {unit ? (
        <VisitorList key={unit.id} unit={unit} />
      ) : (
        <Notice>Nenhuma unidade está vinculada à sua conta neste condomínio.</Notice>
      )}
    </section>
  )
}

function VisitorList({ unit }: { unit: Unit }) {
  const { client } = useAuth()
  const api = useMemo(() => createResidentVisitorsClient(client.http), [client])
  const [filters, setFilters] = useState<Filters>({ page: 1 })
  const [response, setResponse] = useState<ListResponse | null>(null)
  const [searchError, setSearchError] = useState<string>()
  const [dialog, setDialog] = useState<VisitorDialog | null>(null)
  const [saving, setSaving] = useState(false)
  const [actionError, setActionError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    api.list({ ...filters, unidade_id: unit.id }, controller.signal).then(
      (data) => {
        if (controller.signal.aborted) return
        const lastPage = Math.max(1, Math.ceil(data.total / data.page_size))
        if (filters.page > lastPage) {
          setFilters((current) => (current === filters ? { ...current, page: lastPage } : current))
          return
        }
        setResponse({ request: filters, state: 'ready', data })
      },
      (error: unknown) => {
        if (controller.signal.aborted) return
        setResponse({
          request: filters,
          state: 'error',
          message: residentVisitorError(
            error,
            'Não foi possível carregar os visitantes. Tente novamente.',
          ),
        })
      },
    )
    return () => controller.abort()
  }, [api, filters, unit.id])

  const currentResponse = response?.request === filters ? response : null
  const result = currentResponse?.state === 'ready' ? currentResponse.data : null
  const lastPage = result ? Math.ceil(result.total / result.page_size) : 0

  function filterVisitors(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const fields = new FormData(event.currentTarget)
    const busca = String(fields.get('busca') ?? '').trim()
    const situacao = String(fields.get('situacao')) as ResidentVisitorStatus | 'todos'
    const error = visitorNameSearchError(busca)
    setSearchError(error)
    if (error) return
    setSuccess('')
    setFilters({ busca, situacao: situacao === 'todos' ? undefined : situacao, page: 1 })
  }

  async function openVisitor(id: string) {
    const loading: VisitorDialog = { view: 'loading', id }
    setActionError('')
    setDialog(loading)
    try {
      const item = await api.get(id)
      setDialog((current) => (current === loading ? { view: 'details', item } : current))
    } catch (error) {
      const message = residentVisitorError(
        error,
        'Não foi possível carregar o cadastro. Tente novamente.',
      )
      setDialog((current) => (current === loading ? { view: 'error', id, message } : current))
    }
  }

  function changeDialog(next: VisitorDialog) {
    setActionError('')
    setDialog(next)
  }

  async function mutate(request: () => Promise<ResidentVisitor>, message: string) {
    if (saving) return
    setSaving(true)
    setActionError('')
    try {
      await request()
      setDialog(null)
      setSuccess(message)
      setFilters((current) => ({ ...current }))
    } catch (error) {
      setActionError(
        residentVisitorError(error, 'Não foi possível concluir a ação. Tente novamente.'),
      )
    } finally {
      setSaving(false)
    }
  }

  const titles: Record<VisitorDialog['view'], string> = {
    create: 'Novo visitante',
    details: 'Detalhes do visitante',
    loading: 'Detalhes do visitante',
    error: 'Detalhes do visitante',
    edit: 'Editar visitante',
    cancel: 'Cancelar cadastro',
  }

  return (
    <>
      {success && (
        <Notice tone="success" role="status">
          {success}
        </Notice>
      )}
      <Card className={styles.content}>
        <div className={styles.pagination}>
          <Heading level={2} size="md">
            Unidade {unit.identificacao}
          </Heading>
          <Button disabled={!result} onClick={() => changeDialog({ view: 'create' })}>
            Novo visitante
          </Button>
        </div>
        <form className={styles.filters} aria-label="Filtrar visitantes" onSubmit={filterVisitors}>
          <Input
            label="Nome do visitante"
            name="busca"
            type="search"
            maxLength={120}
            error={searchError}
            onChange={() => setSearchError(undefined)}
          />
          <Select label="Situação" name="situacao" defaultValue="todos" options={statusOptions} />
          <div>
            <Button type="submit" variant="secondary">
              Filtrar
            </Button>
          </div>
        </form>
        {!currentResponse && <Text role="status">Carregando visitantes…</Text>}
        {currentResponse?.state === 'error' && (
          <Notice tone="alert" role="alert">
            {currentResponse.message}
            <div>
              <Button variant="secondary" onClick={() => setFilters((current) => ({ ...current }))}>
                Tentar novamente
              </Button>
            </div>
          </Notice>
        )}
        {result && (
          <>
            <Table
              caption="Visitantes da unidade"
              headers={['Visitante', 'Ação']}
              emptyMessage={
                filters.busca || filters.situacao
                  ? 'Nenhum visitante corresponde aos filtros.'
                  : 'Nenhum visitante foi cadastrado para esta unidade.'
              }
              rows={result.items.map((item) => [
                <div key="visitor">
                  <Text size="sm">
                    <strong>{item.nome}</strong>
                  </Text>
                  <Text size="xs" tone="secondary">
                    {formatDate(item.entrada_prevista)} a {formatDate(item.saida_prevista)}
                  </Text>
                  <div className={styles.actions}>
                    <VisitorStatus item={item} />
                    {item.avulso && <Badge>Avulso</Badge>}
                  </div>
                </div>,
                <Button
                  key="details"
                  size="sm"
                  variant="secondary"
                  aria-label={`Ver detalhes de ${item.nome}`}
                  onClick={() => void openVisitor(item.id)}
                >
                  Ver detalhes
                </Button>,
              ])}
            />
            {lastPage > 1 && (
              <div className={styles.pagination}>
                <Text size="sm" tone="secondary">
                  Página {result.page} de {lastPage}
                </Text>
                <div>
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={result.page <= 1}
                    onClick={() => setFilters({ ...filters, page: result.page - 1 })}
                  >
                    Anterior
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={result.page >= lastPage}
                    onClick={() => setFilters({ ...filters, page: result.page + 1 })}
                  >
                    Próxima
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </Card>

      <Modal
        isOpen={dialog !== null}
        title={dialog ? titles[dialog.view] : ''}
        onClose={() => {
          if (!saving) setDialog(null)
        }}
      >
        {dialog?.view === 'loading' && <Text role="status">Carregando cadastro…</Text>}
        {dialog?.view === 'error' && (
          <Notice tone="alert" role="alert">
            {dialog.message}
            <div>
              <Button variant="secondary" onClick={() => void openVisitor(dialog.id)}>
                Tentar novamente
              </Button>
            </div>
          </Notice>
        )}
        {dialog?.view === 'details' && (
          <div className={styles.form}>
            <div>
              <Heading level={3} size="sm">
                {dialog.item.nome}
              </Heading>
              <Text size="sm" tone="secondary">
                Unidade {unit.identificacao}
              </Text>
            </div>
            <div>
              <VisitorStatus item={dialog.item} />
            </div>
            <Text>Entrada prevista em {formatDate(dialog.item.entrada_prevista)}</Text>
            <Text>Saída prevista em {formatDate(dialog.item.saida_prevista)}</Text>
            {dialog.item.cpf && <Text>CPF {dialog.item.cpf}</Text>}
            {dialog.item.idade !== null && <Text>Idade de {dialog.item.idade} anos</Text>}
            {dialog.item.observacoes && (
              <div>
                <Text size="sm" tone="secondary">
                  Observações
                </Text>
                <Text>{dialog.item.observacoes}</Text>
              </div>
            )}
            {dialog.item.avulso && <Notice>Visita avulsa registrada pela portaria.</Notice>}
            {!dialog.item.avulso && !dialog.item.cancelado_em && (
              <div className={styles.actions}>
                <Button onClick={() => changeDialog({ view: 'edit', item: dialog.item })}>
                  Editar visitante
                </Button>
                <Button
                  variant="alert"
                  onClick={() => changeDialog({ view: 'cancel', item: dialog.item })}
                >
                  Cancelar cadastro
                </Button>
              </div>
            )}
          </div>
        )}
        {dialog?.view === 'create' && (
          <VisitorForm
            unit={unit}
            busy={saving}
            actionError={actionError}
            onSave={(data) =>
              void mutate(
                () => api.create({ ...data, unidade_id: unit.id }),
                'Visitante cadastrado.',
              )
            }
            onBack={() => setDialog(null)}
          />
        )}
        {dialog?.view === 'edit' && (
          <VisitorForm
            unit={unit}
            item={dialog.item}
            busy={saving}
            actionError={actionError}
            onSave={(data) =>
              void mutate(() => api.update(dialog.item.id, data), 'Cadastro atualizado.')
            }
            onBack={() => changeDialog({ view: 'details', item: dialog.item })}
          />
        )}
        {dialog?.view === 'cancel' && (
          <div className={styles.form}>
            <Text>
              Confirme o cancelamento do cadastro de <strong>{dialog.item.nome}</strong>. A
              autorização de entrada será encerrada.
            </Text>
            {actionError && (
              <Notice tone="alert" role="alert">
                {actionError}
              </Notice>
            )}
            <div className={styles.actions}>
              <Button
                variant="secondary"
                disabled={saving}
                onClick={() => changeDialog({ view: 'details', item: dialog.item })}
              >
                Voltar
              </Button>
              <Button
                variant="alert"
                loading={saving}
                onClick={() => void mutate(() => api.cancel(dialog.item.id), 'Cadastro cancelado.')}
              >
                Confirmar cancelamento
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}

interface VisitorFormProps {
  unit: Unit
  item?: ResidentVisitor
  busy: boolean
  actionError: string
  onSave: (data: ResidentVisitorData) => void
  onBack: () => void
}

function VisitorForm({ unit, item, busy, actionError, onSave, onBack }: VisitorFormProps) {
  const [validation, setValidation] = useState('')

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const fields = new FormData(event.currentTarget)
    const text = (name: keyof ResidentVisitorData) => String(fields.get(name) ?? '').trim()
    const nome = text('nome')
    const cpf = text('cpf').replace(/[.\s-]/g, '')
    const idade = text('idade')
    const entrada_prevista = text('entrada_prevista')
    const saida_prevista = text('saida_prevista')

    if (nome.length < 3) {
      setValidation('Informe um nome com pelo menos três caracteres.')
      return
    }
    if (cpf && !/^\d{11}$/.test(cpf)) {
      setValidation('Informe um CPF com 11 dígitos.')
      return
    }
    if (!entrada_prevista || !saida_prevista || saida_prevista < entrada_prevista) {
      setValidation('Informe uma data de saída igual ou posterior à data de entrada.')
      return
    }
    setValidation('')
    onSave({
      nome,
      cpf: cpf || null,
      idade: idade ? Number(idade) : null,
      observacoes: text('observacoes') || null,
      entrada_prevista,
      saida_prevista,
    })
  }

  return (
    <form className={styles.form} onSubmit={submit}>
      <Text size="sm" tone="secondary">
        Unidade {unit.identificacao}
      </Text>
      <Input
        label="Nome"
        name="nome"
        defaultValue={item?.nome}
        minLength={3}
        maxLength={120}
        required
        disabled={busy}
      />
      <Input
        label="CPF (opcional)"
        name="cpf"
        inputMode="numeric"
        maxLength={14}
        defaultValue={item?.cpf ?? ''}
        disabled={busy}
      />
      <Input
        label="Idade (opcional)"
        name="idade"
        type="number"
        min={0}
        max={120}
        defaultValue={item?.idade ?? ''}
        disabled={busy}
      />
      <Input
        label="Entrada prevista"
        name="entrada_prevista"
        type="date"
        max="9999-12-30"
        defaultValue={item?.entrada_prevista}
        required
        disabled={busy}
      />
      <Input
        label="Saída prevista"
        name="saida_prevista"
        type="date"
        max="9999-12-30"
        defaultValue={item?.saida_prevista}
        required
        disabled={busy}
      />
      <Input
        label="Observações (opcional)"
        name="observacoes"
        defaultValue={item?.observacoes ?? ''}
        maxLength={300}
        disabled={busy}
      />
      {(validation || actionError) && (
        <Notice tone="alert" role="alert">
          {validation || actionError}
        </Notice>
      )}
      <div className={styles.actions}>
        <Button variant="secondary" disabled={busy} onClick={onBack}>
          Voltar
        </Button>
        <Button type="submit" loading={busy}>
          {item ? 'Salvar alterações' : 'Cadastrar visitante'}
        </Button>
      </div>
    </form>
  )
}
