import { useEffect, useMemo, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import axios from 'axios'
import { Link } from 'react-router'
import {
  Badge,
  Button,
  Card,
  CheckField,
  Heading,
  Input,
  Modal,
  Notice,
  OperationsLayout,
  RecordPhoto,
  Select,
  Table,
  Text,
  Upload,
} from '../../components'
import { AccessDenied } from '../auth/SessionPages'
import { useAuth } from '../auth/context'
import { createEncomendasClient } from './encomendas-api'
import type {
  PackageRecord,
  PackageStatus,
  ResidentOption,
  UnitOption,
  EmployeeOption,
} from './encomendas-api'
import styles from './PackagesWorkspacePage.module.css'
import { portariaNavigation } from '../auth/area-navigation'

const statusLabels: Record<PackageStatus, string> = {
  aguardando_retirada: 'Aguardando retirada',
  entregue_aguardando_confirmacao: 'Aguardando confirmação',
  retirada_confirmada: 'Retirada confirmada',
}

function statusVariant(status: PackageStatus): 'primary' | 'warning' | 'success' {
  if (status === 'retirada_confirmada') return 'success'
  if (status === 'entregue_aguardando_confirmacao') return 'warning'
  return 'primary'
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'short',
    timeZone: 'America/Sao_Paulo',
  }).format(new Date(value))
}

/** Registro que mudou ou sumiu enquanto a tela estava aberta: a lista precisa ser recarregada. */
function isStale(error: unknown) {
  return axios.isAxiosError(error) && [404, 409].includes(error.response?.status ?? 0)
}

/** Erro de uma ação; quando o registro estava desatualizado, avisa que a lista foi recarregada. */
function actionFailure(error: unknown) {
  const message = apiError(error)
  return axios.isAxiosError(error) && error.response?.status === 404
    ? `${message} A lista foi atualizada.`
    : message
}

function apiError(error: unknown) {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 404)
      return 'Este registro não está mais disponível neste condomínio.'
    if (error.response?.status === 409)
      return 'A situação da encomenda mudou. A lista foi atualizada; confira e tente novamente.'
    if (error.response?.status === 413 || error.response?.status === 422)
      return 'Confira os dados e a foto. Use uma imagem JPG, PNG ou WebP de até 5 MB.'
    if (error.response?.status === 503)
      return 'O armazenamento de fotos está indisponível. Seus dados continuam no formulário; tente novamente.'
    if (error.response?.status === 403) return 'Seu perfil não tem permissão para esta operação.'
    if (error.response?.status === 429)
      return 'Muitas tentativas. Aguarde um pouco e tente novamente.'
  }
  return 'Não foi possível concluir a operação. Verifique a conexão e tente novamente.'
}

export function PackagesWorkspacePage() {
  const { snapshot } = useAuth()
  const condominium = snapshot.identity?.condominio
  if (
    !condominium ||
    condominium.perfil !== 'funcionario' ||
    condominium.status !== 'ativo' ||
    snapshot.identity?.administrador_plataforma
  )
    return <AccessDenied />
  return <PackagesWorkspace name={condominium.nome} />
}

function PackagesWorkspace({ name }: { name: string }) {
  const { client, snapshot } = useAuth()
  const api = useMemo(() => createEncomendasClient(client.http), [client])
  const [items, setItems] = useState<PackageRecord[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [searchDraft, setSearchDraft] = useState('')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<PackageStatus | ''>('')
  const [unitFilter, setUnitFilter] = useState('')
  const [revision, setRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [registerOpen, setRegisterOpen] = useState(false)
  const [selected, setSelected] = useState<PackageRecord | null>(null)
  const [units, setUnits] = useState<UnitOption[]>([])
  const [employees, setEmployees] = useState<EmployeeOption[]>([])
  const [residents, setResidents] = useState<ResidentOption[]>([])
  const [residentsLoading, setResidentsLoading] = useState(false)
  const [lookupsLoading, setLookupsLoading] = useState(true)
  const [lookupRevision, setLookupRevision] = useState(0)
  const [residentsRevision, setResidentsRevision] = useState(0)
  const [lookupError, setLookupError] = useState<string | null>(null)
  const [unitsLoadFailed, setUnitsLoadFailed] = useState(false)
  const [residentsError, setResidentsError] = useState<string | null>(null)
  const optionsError = lookupError ?? residentsError
  const [unitId, setUnitId] = useState('')
  const [residentId, setResidentId] = useState('')
  const [employeeId, setEmployeeId] = useState('')
  const [description, setDescription] = useState('')
  const [carrier, setCarrier] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [photoError, setPhotoError] = useState<string | null>(null)
  const [photoRecord, setPhotoRecord] = useState<{ fileId: string; url: string } | null>(null)
  const [deliveryReceiver, setDeliveryReceiver] = useState('')
  const [deliveryEmployee, setDeliveryEmployee] = useState('')
  const [deliveryChecked, setDeliveryChecked] = useState(false)

  useEffect(() => {
    let current = true
    api
      .list({ search, status, unitId: unitFilter, page })
      .then((result) => {
        if (!current) return
        setItems(result.items)
        setTotal(result.total)
        setLoadError(null)
      })
      .catch((error: unknown) => {
        if (current) setLoadError(apiError(error))
      })
      .finally(() => {
        if (current) setLoading(false)
      })
    return () => {
      current = false
    }
  }, [api, page, revision, search, status, unitFilter])

  useEffect(() => {
    let current = true
    void Promise.allSettled([api.units(), api.employees()]).then(([unitResult, employeeResult]) => {
      if (!current) return
      if (unitResult.status === 'fulfilled') setUnits(unitResult.value)
      if (employeeResult.status === 'fulfilled') setEmployees(employeeResult.value)
      setUnitsLoadFailed(unitResult.status === 'rejected')
      const failedLookup = [unitResult, employeeResult].find(
        (result) => result.status === 'rejected',
      )
      setLookupError(failedLookup ? apiError(failedLookup.reason) : null)
      setLookupsLoading(false)
    })
    return () => {
      current = false
    }
  }, [api, lookupRevision])

  const residentsUnitId = registerOpen
    ? unitId
    : selected?.status === 'aguardando_retirada'
      ? selected.unidade.id
      : ''
  const residentsAreReceivers = !registerOpen && selected?.status === 'aguardando_retirada'
  useEffect(() => {
    if (!residentsUnitId) return
    let current = true
    api
      .residents(residentsUnitId, residentsAreReceivers)
      .then((result) => {
        if (current) setResidents(result)
      })
      .catch((error: unknown) => {
        if (current) setResidentsError(apiError(error))
      })
      .finally(() => {
        if (current) setResidentsLoading(false)
      })
    return () => {
      current = false
    }
  }, [api, residentsAreReceivers, residentsRevision, residentsUnitId])

  useEffect(() => {
    let current = true
    if (!selected) return
    api
      .photoUrl(selected.foto_arquivo_id)
      .then((url) => {
        if (current) setPhotoRecord({ fileId: selected.foto_arquivo_id, url })
      })
      .catch(() => {
        if (current) setPhotoRecord({ fileId: selected.foto_arquivo_id, url: '' })
      })
    return () => {
      current = false
    }
  }, [api, selected])

  const photoPreview = useMemo(() => (photo ? URL.createObjectURL(photo) : ''), [photo])
  useEffect(
    () => () => {
      if (photoPreview) URL.revokeObjectURL(photoPreview)
    },
    [photoPreview],
  )

  function reload() {
    setLoading(true)
    setLoadError(null)
    setRevision((value) => value + 1)
  }

  function openRegister() {
    setSuccess(null)
    setActionError(null)
    setUnitId('')
    setResidentId('')
    setEmployeeId('')
    setDescription('')
    setCarrier('')
    setPhoto(null)
    setPhotoError(null)
    setResidents([])
    setResidentsLoading(false)
    setResidentsError(null)
    setRegisterOpen(true)
  }

  function closeRegister() {
    if (pending) return
    setRegisterOpen(false)
    setResidentsError(null)
    setResidents([])
    setResidentsLoading(false)
  }

  function changeUnit(value: string) {
    setUnitId(value)
    setResidentId('')
    setResidents([])
    setResidentsLoading(Boolean(value))
    setResidentsError(null)
  }

  function retryLookups() {
    setLookupError(null)
    setUnitsLoadFailed(false)
    setResidentsError(null)
    setLookupsLoading(true)
    setLookupRevision((value) => value + 1)
    if (residentsUnitId) {
      setResidentsLoading(true)
      setResidentsRevision((value) => value + 1)
    }
  }

  function openDetails(item: PackageRecord) {
    setActionError(null)
    setSuccess(null)
    setDeliveryReceiver('')
    setDeliveryEmployee('')
    setDeliveryChecked(false)
    setResidents([])
    setResidentsLoading(item.status === 'aguardando_retirada')
    setResidentsError(null)
    setSelected(item)
  }

  function closeDetails() {
    if (pending) return
    setSelected(null)
    setResidents([])
    setResidentsLoading(false)
    setResidentsError(null)
  }

  function choosePhoto(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null
    setPhotoError(null)
    if (!file) {
      setPhoto(null)
      return
    }
    if (
      !['image/jpeg', 'image/png', 'image/webp'].includes(file.type) ||
      file.size > 5 * 1024 * 1024
    ) {
      setPhoto(null)
      setPhotoError('Selecione uma imagem JPG, PNG ou WebP de até 5 MB.')
      event.target.value = ''
      return
    }
    setPhoto(file)
  }

  async function submitRegistration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setActionError(null)
    setSuccess(null)
    if (!photo) {
      setPhotoError('Anexe uma foto para registrar o recebimento.')
      return
    }
    if (pending) return
    setPending(true)
    try {
      await api.register({
        unidade_id: unitId,
        destinatario_morador_unidade_id: residentId,
        descricao: description,
        transportadora: carrier,
        recebido_por_funcionario_id: employeeId,
        foto: photo,
      })
      setRegisterOpen(false)
      setResidents([])
      setResidentsLoading(false)
      setSuccess('Encomenda recebida e registrada.')
      setSearch('')
      setSearchDraft('')
      setStatus('')
      setUnitFilter('')
      setPage(1)
      reload()
    } catch (error) {
      setActionError(actionFailure(error))
      if (isStale(error)) reload()
    } finally {
      setPending(false)
    }
  }

  async function submitDelivery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selected) return
    setActionError(null)
    setSuccess(null)
    if (!deliveryChecked) {
      setActionError('Confirme que conferiu a identidade e entregou fisicamente a encomenda.')
      return
    }
    if (pending) return
    setPending(true)
    try {
      const updated = await api.deliver(selected.id, {
        recebedor_morador_unidade_id: deliveryReceiver,
        entregue_por_funcionario_id: deliveryEmployee,
      })
      setResidents([])
      setResidentsLoading(false)
      setSelected(updated)
      setSuccess('Entrega registrada. A confirmação ficará pendente para o morador que recebeu.')
      reload()
    } catch (error) {
      setActionError(actionFailure(error))
      if (isStale(error)) reload()
    } finally {
      setPending(false)
    }
  }
  const selectedPhotoUrl =
    selected && photoRecord?.fileId === selected.foto_arquivo_id ? photoRecord.url : null
  const unitOptions = units.map((unit) => ({
    value: unit.id,
    label: [unit.bloco, unit.andar, unit.identificacao].filter(Boolean).join(' / '),
  }))
  const tools = (
    <div className={styles.tools}>
      {snapshot.condominiums.length > 1 && (
        <Link to="/selecionar-condominio">Trocar condomínio</Link>
      )}
      <Button variant="secondary" size="sm" onClick={() => client.logout()}>
        Sair
      </Button>
    </div>
  )
  const rows = items.map((item) => [
    <div key="package">
      <Text size="sm">
        <strong>{item.descricao}</strong>
      </Text>
      <Text size="xs" tone="secondary">
        {item.id.slice(0, 8)}
      </Text>
    </div>,
    <div key="destination">
      <Text size="sm">{item.unidade.identificacao}</Text>
      <Text size="xs" tone="secondary">
        {item.destinatario.nome}
      </Text>
    </div>,
    <Text key="received" size="sm">
      {formatDate(item.recebimento.em)}
      <br />
      {item.recebimento.funcionario_nome}
    </Text>,
    <Badge key="status" variant={statusVariant(item.status)} wrap>
      {statusLabels[item.status]}
    </Badge>,
    <Button
      key="details"
      variant="secondary"
      size="sm"
      onClick={() => openDetails(item)}
      aria-label={`Ver detalhes de ${item.descricao}`}
    >
      {item.status === 'aguardando_retirada' ? 'Registrar entrega' : 'Ver detalhes'}
    </Button>,
  ])

  return (
    <OperationsLayout
      activeKey="packages"
      navigation={portariaNavigation}
      workspace={{ name, profile: 'Portaria', tools }}
    >
      <section className={styles.content} aria-labelledby="packages-title">
        <div className={styles.header}>
          <div>
            <Badge variant="primary">Portaria</Badge>
            <Heading level={1} id="packages-title">
              Encomendas
            </Heading>
            <Text tone="secondary">
              Registre recebimentos e acompanhe a retirada até a confirmação do morador.
            </Text>
          </div>
          <Button onClick={openRegister}>Receber encomenda</Button>
        </div>
        {success && (
          <Notice tone="success" role="status">
            {success}
          </Notice>
        )}
        {actionError && !selected && (
          <Notice tone="alert" role="alert">
            {actionError}
          </Notice>
        )}
        <Card>
          <div className={styles.header}>
            <div>
              <Heading level={2} size="md">
                Controle de encomendas
              </Heading>
              <Text size="sm" tone="secondary">
                {loading ? 'Atualizando registros…' : `${total} registro(s)`}
              </Text>
            </div>
          </div>
          <form
            className={styles.filters}
            onSubmit={(event) => {
              event.preventDefault()
              setPage(1)
              setSearch(searchDraft.trim())
              setLoading(true)
              setLoadError(null)
              setRevision((value) => value + 1)
            }}
          >
            <Input
              label="Buscar encomenda"
              type="search"
              placeholder="Descrição, morador ou unidade"
              value={searchDraft}
              onChange={(event) => setSearchDraft(event.target.value)}
              disabled={loading}
            />
            <Select
              label="Status"
              value={status || 'todos'}
              onChange={(event) => {
                setStatus(
                  event.target.value === 'todos' ? '' : (event.target.value as PackageStatus),
                )
                setPage(1)
                setLoading(true)
                setLoadError(null)
              }}
              options={[
                { value: 'todos', label: 'Todos os status' },
                { value: 'aguardando_retirada', label: statusLabels.aguardando_retirada },
                {
                  value: 'entregue_aguardando_confirmacao',
                  label: statusLabels.entregue_aguardando_confirmacao,
                },
                { value: 'retirada_confirmada', label: statusLabels.retirada_confirmada },
              ]}
              placeholder="Todos os status"
              disabled={loading}
            />
            <Select
              label="Unidade"
              value={unitFilter || 'todas'}
              onChange={(event) => {
                setUnitFilter(event.target.value === 'todas' ? '' : event.target.value)
                setPage(1)
                reload()
              }}
              options={[{ value: 'todas', label: 'Todas as unidades' }, ...unitOptions]}
              disabled={loading || lookupsLoading}
            />
            <Button type="submit" variant="secondary" disabled={loading}>
              Buscar
            </Button>
          </form>
          {unitsLoadFailed && (
            <Notice tone="alert" role="alert">
              Não foi possível carregar as unidades.
              <div className={styles.retry}>
                <Button variant="secondary" size="sm" onClick={retryLookups}>
                  Recarregar unidades
                </Button>
              </div>
            </Notice>
          )}
          {loadError ? (
            <Notice tone="alert" role="alert">
              {loadError}
              <div className={styles.retry}>
                <Button variant="secondary" size="sm" onClick={reload}>
                  Tentar novamente
                </Button>
              </div>
            </Notice>
          ) : loading ? (
            <Text role="status">Carregando encomendas…</Text>
          ) : (
            <>
              <Table
                caption="Encomendas deste condomínio"
                headers={['Encomenda', 'Destino', 'Recebimento', 'Status', 'Ação']}
                rows={rows}
                emptyMessage="Nenhuma encomenda encontrada. Ajuste os filtros ou registre um recebimento."
              />
              <div className={styles.pagination}>
                <Text size="sm" tone="secondary">
                  Página {page} de {Math.max(1, Math.ceil(total / 20))}
                </Text>
                <div>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => {
                      setLoading(true)
                      setLoadError(null)
                      setPage((value) => value - 1)
                    }}
                  >
                    Anterior
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={page * 20 >= total}
                    onClick={() => {
                      setLoading(true)
                      setLoadError(null)
                      setPage((value) => value + 1)
                    }}
                  >
                    Próxima
                  </Button>
                </div>
              </div>
            </>
          )}
        </Card>
        <Notice>
          Quando a portaria registra a entrega física, somente o morador que recebeu pode confirmar
          a retirada pela própria conta. A confirmação não acontece automaticamente.
        </Notice>
      </section>

      <Modal isOpen={registerOpen} onClose={closeRegister} title="Receber encomenda">
        <form
          className={styles.form}
          onSubmit={(event) => {
            void submitRegistration(event)
          }}
        >
          <Text tone="secondary">
            Informe a unidade e o destinatário. A foto é armazenada de forma protegida.
          </Text>
          {optionsError && (
            <Notice tone="alert" role="alert">
              {optionsError}
              <div className={styles.retry}>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={retryLookups}
                  disabled={lookupsLoading}
                >
                  Recarregar opções
                </Button>
              </div>
            </Notice>
          )}
          {lookupsLoading ? (
            <Text role="status">Carregando unidades e funcionários…</Text>
          ) : (
            <>
              <Select
                label="Unidade"
                required
                value={unitId}
                onChange={(event) => changeUnit(event.target.value)}
                options={unitOptions}
                disabled={pending}
                hint={
                  !units.length && !lookupsLoading && !lookupError
                    ? 'Nenhuma unidade ativa foi encontrada.'
                    : undefined
                }
              />
              <Select
                label="Destinatário"
                required
                value={residentId}
                onChange={(event) => setResidentId(event.target.value)}
                options={residents.map((resident) => ({
                  value: resident.id,
                  label: resident.nome,
                }))}
                disabled={!unitId || pending || residentsLoading}
                hint={
                  residentsLoading
                    ? 'Carregando moradores ativos…'
                    : unitId && residents.length === 0
                      ? 'Nenhum morador ativo foi encontrado nesta unidade.'
                      : undefined
                }
              />
              <Input
                label="Descrição"
                required
                maxLength={200}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Ex.: caixa de livros"
                disabled={pending}
              />
              <Input
                label="Transportadora (opcional)"
                maxLength={120}
                value={carrier}
                onChange={(event) => setCarrier(event.target.value)}
                disabled={pending}
              />
              <Select
                label="Funcionário que recebeu"
                required
                value={employeeId}
                onChange={(event) => setEmployeeId(event.target.value)}
                options={employees.map((employee) => ({
                  value: employee.id,
                  label: employee.nome,
                }))}
                disabled={pending}
                hint={!employees.length ? 'Nenhum funcionário ativo foi encontrado.' : undefined}
              />
              <div>
                <Text as="div" size="sm">
                  <strong>Foto da encomenda</strong> <Badge variant="warning">Obrigatória</Badge>
                </Text>
                <Text id="photo-help" size="sm" tone="secondary">
                  JPG, PNG ou WebP. Até 5 MB.
                </Text>
                <Upload
                  label="Selecionar foto"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={choosePhoto}
                  aria-describedby="photo-help photo-error"
                  disabled={pending}
                />
              </div>
              <div id="photo-error" aria-live="polite">
                {photoError && <Notice tone="alert">{photoError}</Notice>}
              </div>
              {photoPreview && <RecordPhoto src={photoPreview} alt="Prévia da foto da encomenda" />}
            </>
          )}
          {actionError && (
            <Notice tone="alert" role="alert">
              {actionError}
            </Notice>
          )}
          <div className={styles.actions}>
            <Button variant="secondary" onClick={closeRegister} disabled={pending}>
              Cancelar
            </Button>
            <Button
              type="submit"
              loading={pending}
              disabled={
                lookupsLoading || !!optionsError || residents.length === 0 || employees.length === 0
              }
            >
              Salvar recebimento
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        isOpen={!!selected}
        onClose={closeDetails}
        title={
          selected?.status === 'aguardando_retirada' ? 'Registrar entrega' : 'Detalhes da encomenda'
        }
      >
        {selected && (
          <div className={styles.form}>
            <div>
              <Heading level={3} size="sm">
                {selected.descricao}
              </Heading>
              <Text size="sm" tone="secondary">
                {selected.unidade.identificacao} · Destinatário: {selected.destinatario.nome}
              </Text>
              {selected.transportadora && (
                <Text size="sm" tone="secondary">
                  <strong>Transportadora</strong> · {selected.transportadora}
                </Text>
              )}
            </div>
            <Badge variant={statusVariant(selected.status)} wrap>
              {statusLabels[selected.status]}
            </Badge>
            {selectedPhotoUrl === null ? (
              <Text role="status">Carregando foto protegida…</Text>
            ) : selectedPhotoUrl ? (
              <RecordPhoto src={selectedPhotoUrl} alt={`Foto da encomenda ${selected.descricao}`} />
            ) : (
              <Notice tone="warning">
                Não foi possível carregar a foto. Feche os detalhes e tente novamente.
              </Notice>
            )}
            <div className={styles.history}>
              <Text size="sm">
                <strong>Recebida</strong> · {formatDate(selected.recebimento.em)}
                <br />
                Por {selected.recebimento.funcionario_nome}
              </Text>
              {selected.entrega && (
                <Text size="sm">
                  <strong>Entregue</strong> · {formatDate(selected.entrega.em)}
                  <br />
                  Por {selected.entrega.funcionario_nome} · Recebida por{' '}
                  {selected.entrega.recebedor_nome}
                </Text>
              )}
              {selected.confirmacao && (
                <Text size="sm">
                  <strong>Retirada confirmada</strong> · {formatDate(selected.confirmacao.em)}
                  <br />
                  Por {selected.confirmacao.morador_nome}
                </Text>
              )}
            </div>
            {selected.status === 'entregue_aguardando_confirmacao' && (
              <Notice tone="warning">
                A entrega está registrada. A portaria pode consultar o morador por telefone ou
                interfone; a encomenda permanece pendente até ele confirmar.
              </Notice>
            )}
            {selected.status === 'aguardando_retirada' && (
              <form
                className={styles.form}
                onSubmit={(event) => {
                  void submitDelivery(event)
                }}
              >
                {optionsError && (
                  <Notice tone="alert" role="alert">
                    {optionsError}
                    <div className={styles.retry}>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={retryLookups}
                        disabled={lookupsLoading}
                      >
                        Recarregar opções
                      </Button>
                    </div>
                  </Notice>
                )}
                <Select
                  label="Morador que recebeu fisicamente"
                  required
                  value={deliveryReceiver}
                  onChange={(event) => setDeliveryReceiver(event.target.value)}
                  options={residents.map((resident) => ({
                    value: resident.id,
                    label: resident.nome,
                  }))}
                  disabled={pending || residentsLoading || residents.length === 0}
                  hint={residentsLoading ? 'Carregando moradores ativos…' : undefined}
                />
                <Select
                  label="Funcionário que registrou a entrega"
                  required
                  value={deliveryEmployee}
                  onChange={(event) => setDeliveryEmployee(event.target.value)}
                  options={employees.map((employee) => ({
                    value: employee.id,
                    label: employee.nome,
                  }))}
                  disabled={pending || employees.length === 0}
                />
                <CheckField
                  checked={deliveryChecked}
                  onChange={(event) => setDeliveryChecked(event.target.checked)}
                  disabled={pending}
                >
                  Conferi a identidade e entreguei fisicamente a encomenda ao morador selecionado.
                </CheckField>
                {actionError && (
                  <Notice tone="alert" role="alert">
                    {actionError}
                  </Notice>
                )}
                <div className={styles.actions}>
                  <Button variant="secondary" onClick={closeDetails} disabled={pending}>
                    Fechar
                  </Button>
                  <Button
                    type="submit"
                    loading={pending}
                    disabled={
                      !deliveryReceiver || !deliveryEmployee || lookupsLoading || !!optionsError
                    }
                  >
                    Registrar entrega
                  </Button>
                </div>
              </form>
            )}
            {success && selected.status !== 'aguardando_retirada' && (
              <Notice tone="success" role="status">
                {success}
              </Notice>
            )}
            {selected.status !== 'aguardando_retirada' && (
              <div className={styles.actions}>
                <Button variant="secondary" onClick={closeDetails}>
                  Fechar detalhes
                </Button>
              </div>
            )}
          </div>
        )}
      </Modal>
    </OperationsLayout>
  )
}
