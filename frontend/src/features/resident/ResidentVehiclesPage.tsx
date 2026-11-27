import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Button, Card, Heading, Input, Modal, Notice, Select, Table, Text } from '../../components'
import { useAuth } from '../auth/context'
import type { Identity } from '../auth/types'
import { ResidentWorkspace } from './ResidentWorkspace'
import styles from './ResidentWorkspace.module.css'
import {
  VEHICLES_PER_UNIT,
  createResidentVehiclesClient,
  prepareVehicle,
  vehicleFailureMessage,
} from './resident-vehicles-api'
import type { ResidentVehicle, VehicleFieldErrors, VehicleFields } from './resident-vehicles-api'

type Unit = Identity['unidades'][number]
type VehiclesApi = ReturnType<typeof createResidentVehiclesClient>
type VehiclePage = Awaited<ReturnType<VehiclesApi['list']>>
type ListState = { result: VehiclePage } | { error: string } | null
type VehicleAction =
  | { kind: 'create' }
  | { kind: 'edit'; vehicle: ResidentVehicle }
  | { kind: 'remove'; vehicle: ResidentVehicle }

const pageSize = 20
const emptyFields: VehicleFields = { placa: '', marca: '', modelo: '', cor: '' }
const fields = [
  { name: 'placa', label: 'Placa' },
  { name: 'marca', label: 'Marca' },
  { name: 'modelo', label: 'Modelo' },
  { name: 'cor', label: 'Cor' },
] as const

export function ResidentVehiclesPage() {
  return (
    <ResidentWorkspace activeKey="vehicles">
      <ResidentVehicles />
    </ResidentWorkspace>
  )
}

function ResidentVehicles() {
  const { snapshot, client } = useAuth()
  const api = useMemo(() => createResidentVehiclesClient(client.http), [client])
  const units = (snapshot.identity?.unidades ?? []).filter((unit) =>
    unit.abas?.includes('veiculos'),
  )
  const [unitId, setUnitId] = useState('')
  const unit = units.find(({ id }) => id === unitId) ?? units[0]

  return (
    <section className={styles.content} aria-labelledby="resident-vehicles-title">
      <div>
        <Heading level={1} id="resident-vehicles-title">
          Meus veículos
        </Heading>
        <Text tone="secondary">
          Você pode cadastrar até {VEHICLES_PER_UNIT} veículos ativos por unidade.
        </Text>
      </div>
      {unit ? (
        <Card className={styles.form}>
          <Select
            label="Unidade"
            options={units.map(({ id, identificacao }) => ({ value: id, label: identificacao }))}
            value={unit.id}
            onChange={(event) => setUnitId(event.target.value)}
            disabled={units.length === 1}
          />
          <UnitVehicles key={unit.id} unit={unit} api={api} />
        </Card>
      ) : (
        <Notice tone="warning">
          Sua conta ainda não tem uma unidade vinculada neste condomínio.
        </Notice>
      )}
    </section>
  )
}

function UnitVehicles({ unit, api }: { unit: Unit; api: VehiclesApi }) {
  const [searchInput, setSearchInput] = useState('')
  const [query, setQuery] = useState({ search: '', page: 1 })
  const [list, setList] = useState<ListState>(null)
  const [action, setAction] = useState<VehicleAction | null>(null)
  const [pending, setPending] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  useEffect(() => {
    const abort = new AbortController()
    api.list(unit.id, query.search, query.page, pageSize, abort.signal).then(
      (result) => {
        if (abort.signal.aborted) return
        const lastPage = Math.max(1, Math.ceil(result.total / result.page_size))
        if (query.page > lastPage) {
          setQuery({ search: query.search, page: lastPage })
          return
        }
        setList({ result })
      },
      (error: unknown) => {
        if (!abort.signal.aborted) setList({ error: vehicleFailureMessage(error) })
      },
    )
    return () => abort.abort()
  }, [api, unit.id, query])

  function load(search: string, page: number) {
    setList(null)
    setQuery({ search, page })
  }

  function openAction(nextAction: VehicleAction) {
    setSuccess(null)
    setActionError(null)
    setAction(nextAction)
  }

  function closeAction() {
    if (!pending) setAction(null)
  }

  async function mutate(operation: () => Promise<ResidentVehicle>, message: string, page: number) {
    if (pending) return
    setPending(true)
    setActionError(null)
    try {
      await operation()
      setSuccess(message)
      setAction(null)
      load(query.search, page)
    } catch (error) {
      setActionError(vehicleFailureMessage(error))
    } finally {
      setPending(false)
    }
  }

  const result = list && 'result' in list ? list.result : null
  const lastPage = result ? Math.max(1, Math.ceil(result.total / result.page_size)) : 1
  const cancel = (
    <Button variant="secondary" disabled={pending} onClick={closeAction}>
      Cancelar
    </Button>
  )
  const formError = actionError && (
    <Notice tone="alert" role="alert">
      {actionError}
    </Notice>
  )
  const actionTitle =
    action?.kind === 'remove'
      ? 'Remover veículo'
      : action?.kind === 'edit'
        ? 'Editar veículo'
        : 'Cadastrar veículo'

  return (
    <>
      <form
        className={styles.filters}
        role="search"
        aria-label="Busca de veículos da unidade"
        onSubmit={(event) => {
          event.preventDefault()
          setSuccess(null)
          load(searchInput.trim(), 1)
        }}
      >
        <Input
          label="Buscar por placa, marca ou modelo"
          type="search"
          maxLength={80}
          value={searchInput}
          onChange={(event) => setSearchInput(event.target.value)}
        />
        <div className={styles.actions}>
          <Button type="submit" variant="secondary">
            Buscar
          </Button>
          {query.search && (
            <Button
              variant="secondary"
              onClick={() => {
                setSearchInput('')
                setSuccess(null)
                load('', 1)
              }}
            >
              Limpar busca
            </Button>
          )}
        </div>
      </form>

      <div className={styles.actions}>
        <Button disabled={!result} onClick={() => openAction({ kind: 'create' })}>
          Cadastrar veículo
        </Button>
      </div>
      {success && (
        <Notice tone="success" role="status">
          {success}
        </Notice>
      )}
      {list === null && <Text role="status">Carregando veículos…</Text>}
      {list && 'error' in list && (
        <div className={styles.form}>
          <Notice tone="alert" role="alert">
            {list.error}
          </Notice>
          <div className={styles.actions}>
            <Button variant="secondary" size="sm" onClick={() => load(query.search, query.page)}>
              Tentar novamente
            </Button>
          </div>
        </div>
      )}
      {result && (
        <>
          <Table
            caption="Veículos ativos da unidade"
            headers={['Veículo', 'Ações']}
            emptyMessage={
              query.search
                ? 'Nenhum veículo encontrado para esta busca.'
                : 'Nenhum veículo cadastrado nesta unidade.'
            }
            rows={result.items.map((vehicle) => [
              <div key="vehicle">
                <Text>
                  <strong>{vehicle.placa}</strong>
                </Text>
                <Text size="sm" tone="secondary">
                  {vehicle.marca} {vehicle.modelo} · {vehicle.cor}
                </Text>
              </div>,
              <div className={styles.actions} key="actions">
                <Button
                  size="sm"
                  variant="secondary"
                  aria-label={`Editar veículo ${vehicle.placa}`}
                  onClick={() => openAction({ kind: 'edit', vehicle })}
                >
                  Editar
                </Button>
                <Button
                  size="sm"
                  variant="alert"
                  aria-label={`Remover veículo ${vehicle.placa}`}
                  onClick={() => openAction({ kind: 'remove', vehicle })}
                >
                  Remover
                </Button>
              </div>,
            ])}
          />
          {lastPage > 1 && (
            <nav className={styles.pagination} aria-label="Paginação de veículos">
              <Text size="sm" tone="secondary" role="status">
                Página {result.page} de {lastPage}
              </Text>
              <div>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={result.page <= 1}
                  onClick={() => load(query.search, result.page - 1)}
                >
                  Anterior
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={result.page >= lastPage}
                  onClick={() => load(query.search, result.page + 1)}
                >
                  Próxima
                </Button>
              </div>
            </nav>
          )}
        </>
      )}

      <Modal isOpen={action !== null} onClose={closeAction} title={actionTitle}>
        {action && (
          <div className={styles.form}>
            <Text tone="secondary">Unidade {unit.identificacao}</Text>
            {action.kind === 'create' && (
              <VehicleForm
                initial={emptyFields}
                pending={pending}
                error={actionError}
                submitLabel="Cadastrar veículo"
                onCancel={closeAction}
                onSubmit={(values) =>
                  void mutate(() => api.create(unit.id, values), 'Veículo cadastrado.', 1)
                }
              />
            )}
            {action.kind === 'edit' && (
              <VehicleEditForm
                api={api}
                id={action.vehicle.id}
                pending={pending}
                error={actionError}
                onCancel={closeAction}
                onSubmit={(values) =>
                  void mutate(
                    () => api.update(action.vehicle.id, values),
                    'Veículo atualizado.',
                    query.page,
                  )
                }
              />
            )}
            {action.kind === 'remove' && (
              <>
                <Text>
                  Deseja remover o veículo de placa <strong>{action.vehicle.placa}</strong> desta
                  unidade?
                </Text>
                {formError}
                <div className={styles.actions}>
                  {cancel}
                  <Button
                    variant="alert"
                    loading={pending}
                    onClick={() =>
                      void mutate(
                        () => api.remove(action.vehicle.id),
                        'Veículo removido.',
                        query.page,
                      )
                    }
                  >
                    Confirmar remoção
                  </Button>
                </div>
              </>
            )}
          </div>
        )}
      </Modal>
    </>
  )
}

interface VehicleFormProps {
  pending: boolean
  error: string | null
  onSubmit: (values: VehicleFields) => void
  onCancel: () => void
}

function VehicleEditForm({
  api,
  id,
  ...formProps
}: VehicleFormProps & { api: VehiclesApi; id: string }) {
  const [detail, setDetail] = useState<{ vehicle: ResidentVehicle } | { error: string } | null>(
    null,
  )
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    const abort = new AbortController()
    api.detail(id, abort.signal).then(
      (vehicle) => {
        if (!abort.signal.aborted) setDetail({ vehicle })
      },
      (error: unknown) => {
        if (!abort.signal.aborted) setDetail({ error: vehicleFailureMessage(error) })
      },
    )
    return () => abort.abort()
  }, [api, id, revision])

  if (!detail) return <Text role="status">Carregando dados do veículo…</Text>
  if ('error' in detail) {
    return (
      <div className={styles.form}>
        <Notice tone="alert" role="alert">
          {detail.error}
        </Notice>
        <div className={styles.actions}>
          <Button variant="secondary" onClick={formProps.onCancel}>
            Cancelar
          </Button>
          <Button
            variant="secondary"
            onClick={() => {
              setDetail(null)
              setRevision((value) => value + 1)
            }}
          >
            Tentar novamente
          </Button>
        </div>
      </div>
    )
  }
  return <VehicleForm {...formProps} initial={detail.vehicle} submitLabel="Salvar alterações" />
}

function VehicleForm({
  initial,
  pending,
  error,
  submitLabel,
  onSubmit,
  onCancel,
}: VehicleFormProps & { initial: VehicleFields; submitLabel: string }) {
  const [values, setValues] = useState(initial)
  const [errors, setErrors] = useState<VehicleFieldErrors>({})

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const prepared = prepareVehicle(values)
    if (prepared.errors) {
      setErrors(prepared.errors)
      const firstInvalid = Object.keys(prepared.errors)[0]
      const field = event.currentTarget.elements.namedItem(firstInvalid)
      if (field instanceof HTMLInputElement) field.focus()
      return
    }
    onSubmit(prepared.data)
  }

  return (
    <form className={styles.form} onSubmit={submit} noValidate>
      {fields.map(({ name, label }) => (
        <Input
          key={name}
          name={name}
          label={label}
          required
          disabled={pending}
          autoComplete="off"
          autoCapitalize={name === 'placa' ? 'characters' : 'words'}
          spellCheck={name === 'placa' ? false : undefined}
          hint={name === 'placa' ? 'Ex.: ABC-1234 ou ABC1D23' : undefined}
          maxLength={name === 'placa' ? 20 : undefined}
          value={values[name]}
          error={errors[name]}
          onChange={(event) => {
            const value = event.target.value
            setValues((current) => ({ ...current, [name]: value }))
            setErrors((current) => ({ ...current, [name]: undefined }))
          }}
        />
      ))}
      {Object.values(errors).some(Boolean) && (
        <Notice tone="alert" role="alert">
          Confira os campos indicados antes de salvar.
        </Notice>
      )}
      {error && (
        <Notice tone="alert" role="alert">
          {error}
        </Notice>
      )}
      <div className={styles.actions}>
        <Button variant="secondary" disabled={pending} onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" loading={pending}>
          {submitLabel}
        </Button>
      </div>
    </form>
  )
}
