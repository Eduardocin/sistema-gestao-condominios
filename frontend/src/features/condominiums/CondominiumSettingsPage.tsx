import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router'
import {
  Button,
  Card,
  Heading,
  Input,
  Notice,
  OperationsLayout,
  Select,
  Text,
} from '../../components'
import { useAuth } from '../auth/context'
import { AccessDenied } from '../auth/SessionPages'
import {
  condominiumAdminError,
  createCondominiumAdminApi,
  type BlockRecord,
  type CondominiumAddress,
  type CondominiumRecord,
  type StructureRecord,
} from './condominium-admin-api'
import { canResendRegistration } from './condominium-admin-state'
import styles from './CondominiumSettingsPage.module.css'

const emptyAddress: CondominiumAddress = {
  cep: '',
  logradouro: '',
  numero: '',
  complemento: '',
  bairro: '',
  cidade: '',
  uf: '',
}

export function CondominiumSettingsPage() {
  const { client, snapshot } = useAuth()
  const identity = snapshot.identity
  const api = useMemo(() => createCondominiumAdminApi(client.http), [client])
  const [condominium, setCondominium] = useState<CondominiumRecord>()
  const [structure, setStructure] = useState<StructureRecord>()
  const [responsibles, setResponsibles] = useState<{ id: string; nome: string; ativo: boolean }[]>(
    [],
  )
  const [responsibleId, setResponsibleId] = useState('')
  const [name, setName] = useState('')
  const [cnpj, setCnpj] = useState('')
  const [address, setAddress] = useState<CondominiumAddress>(emptyAddress)
  const [newBlock, setNewBlock] = useState('')
  const [newFloor, setNewFloor] = useState('')
  const [newUnit, setNewUnit] = useState('')
  const [blockId, setBlockId] = useState('')
  const [floorId, setFloorId] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [detailsDirty, setDetailsDirty] = useState(false)
  const [structureDrafts, setStructureDrafts] = useState<Set<string>>(new Set())

  function markStructureDraft(id: string, pending: boolean) {
    setStructureDrafts((current) => {
      const next = new Set(current)
      if (pending) next.add(id)
      else next.delete(id)
      return next
    })
  }

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      const [current, tree, activeResponsibles] = await Promise.all([
        api.condominium(signal),
        api.structure(signal),
        api.responsibles(signal),
      ])
      setCondominium(current)
      setStructure(tree)
      setResponsibles(activeResponsibles)
      setName(current.nome)
      setCnpj(current.cnpj ?? '')
      setAddress(
        Object.fromEntries(
          Object.entries(current.endereco).map(([key, value]) => [key, value ?? '']),
        ) as CondominiumAddress,
      )
      setResponsibleId((selected) =>
        activeResponsibles.some((item) => item.id === selected)
          ? selected
          : (activeResponsibles[0]?.id ?? ''),
      )
    },
    [api],
  )

  useEffect(() => {
    if (
      !identity ||
      identity.administrador_plataforma ||
      identity.condominio?.perfil !== 'administracao'
    )
      return
    const controller = new AbortController()
    async function load() {
      try {
        const [current, tree, activeResponsibles] = await Promise.all([
          api.condominium(controller.signal),
          api.structure(controller.signal),
          api.responsibles(controller.signal),
        ])
        if (controller.signal.aborted) return
        setCondominium(current)
        setStructure(tree)
        setResponsibles(activeResponsibles)
        setName(current.nome)
        setCnpj(current.cnpj ?? '')
        setAddress(
          Object.fromEntries(
            Object.entries(current.endereco).map(([key, value]) => [key, value ?? '']),
          ) as CondominiumAddress,
        )
        setResponsibleId((selected) =>
          activeResponsibles.some((item) => item.id === selected)
            ? selected
            : (activeResponsibles[0]?.id ?? ''),
        )
      } catch {
        if (!controller.signal.aborted)
          setError('Não foi possível carregar os dados do condomínio.')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    void load()
    return () => controller.abort()
  }, [api, identity])

  if (
    !identity ||
    identity.administrador_plataforma ||
    identity.condominio?.perfil !== 'administracao'
  )
    return <AccessDenied />

  async function perform(action: () => Promise<unknown>, message: string, reload = true) {
    if (busy) return false
    setBusy(true)
    setError('')
    setSuccess('')
    try {
      await action()
      if (reload) await refresh()
      setSuccess(message)
      return true
    } catch (cause) {
      setError(
        condominiumAdminError(
          cause,
          'Não foi possível salvar. Confira os dados e tente novamente.',
        ),
      )
      return false
    } finally {
      setBusy(false)
    }
  }

  async function saveCondominium(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!responsibleId) {
      setError('Cadastre um responsável ativo antes de salvar.')
      return
    }
    const saved = await perform(
      () =>
        api.updateCondominium({
          nome: name,
          cnpj: cnpj.replace(/\D/g, ''),
          endereco: { ...address, cep: address.cep?.replace(/\D/g, '') || null },
          responsavel_id: responsibleId,
        }),
      'Dados do condomínio atualizados.',
    )
    if (saved) setDetailsDirty(false)
  }

  async function updateStructure(
    kind: 'blocos' | 'andares' | 'unidades',
    id: string,
    currentName: string,
    order: number,
    active: boolean,
    toggle = false,
  ) {
    if (!responsibleId) {
      setError('Cadastre um responsável ativo antes de editar a estrutura.')
      return
    }
    const accepted =
      toggle && active
        ? window.confirm('Desativar este item da estrutura? O histórico será preservado.')
        : true
    if (!accepted) return
    const save =
      kind === 'blocos'
        ? () => api.updateBlock(id, { nome: currentName, responsavel_id: responsibleId })
        : kind === 'andares'
          ? () =>
              api.updateFloor(id, {
                nome: currentName,
                ordem: order,
                responsavel_id: responsibleId,
              })
          : () => api.updateUnit(id, { identificacao: currentName, responsavel_id: responsibleId })
    const saved = await perform(
      () => (toggle ? api.setStructureStatus(kind, id, !active, responsibleId) : save()),
      toggle
        ? active
          ? 'Item desativado; os vínculos foram preservados.'
          : 'Item reativado.'
        : 'Alteração salva.',
    )
    if (saved) markStructureDraft(id, false)
  }

  async function addStructure(kind: 'block' | 'floor' | 'unit', event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!responsibleId) {
      setError('Cadastre um responsável ativo antes de adicionar itens.')
      return
    }
    let saved = false
    if (kind === 'block')
      saved = await perform(
        () => api.createBlock({ nome: newBlock, responsavel_id: responsibleId }),
        'Bloco adicionado.',
      )
    if (kind === 'floor' && blockId)
      saved = await perform(
        () =>
          api.createFloor(blockId, {
            nome: newFloor,
            ordem: newFloorOrder,
            responsavel_id: responsibleId,
          }),
        'Andar adicionado.',
      )
    if (kind === 'unit' && floorId)
      saved = await perform(
        () => api.createUnit(floorId, { identificacao: newUnit, responsavel_id: responsibleId }),
        'Unidade adicionada.',
      )
    if (!saved) return
    if (kind === 'block') setNewBlock('')
    if (kind === 'floor') setNewFloor('')
    if (kind === 'unit') setNewUnit('')
    markStructureDraft(`new-${kind}`, false)
  }

  const blocks = structure?.blocos ?? []
  const floors = blocks.flatMap((block) =>
    block.andares.map((floor) => ({ ...floor, blocoNome: block.nome })),
  )
  const newFloorOrder =
    Math.max(
      -1,
      ...(blocks.find((block) => block.id === blockId)?.andares.map((floor) => floor.ordem) ?? []),
    ) + 1
  const workspaceName = identity.condominio?.nome ?? 'Condomínio'
  const nav = [
    { key: 'overview', label: 'Visão geral', to: '/app/administracao', symbol: '⌂' },
    {
      key: 'settings',
      label: 'Condomínio e estrutura',
      to: '/app/administracao/condominio',
      symbol: '▦',
    },
    {
      key: 'shared',
      label: 'Conta de funcionários',
      to: '/app/administracao/conta-funcionarios',
      symbol: '♙',
    },
  ]

  return (
    <OperationsLayout
      activeKey="settings"
      navigation={nav}
      workspace={{
        name: workspaceName,
        profile: 'Administração',
        tools: (
          <div className={styles.tools}>
            {snapshot.condominiums.length > 1 && (
              <Link to="/selecionar-condominio">Trocar condomínio</Link>
            )}
            <Button variant="secondary" size="sm" onClick={() => client.logout()}>
              Sair
            </Button>
          </div>
        ),
      }}
    >
      <main className={styles.content}>
        <Heading level={1}>Condomínio e estrutura</Heading>
        <Text tone="secondary">
          Edite os dados e mantenha blocos, andares e unidades. Os registros desativados permanecem
          no histórico.
        </Text>
        {error && (
          <Notice tone="alert" role="alert">
            {error}
          </Notice>
        )}
        {success && (
          <Notice tone="success" role="status">
            {success}
          </Notice>
        )}
        {loading && <Text>Carregando dados…</Text>}
        {condominium?.status === 'rejeitado' && (
          <Notice tone="warning" title="Cadastro precisa de ajustes">
            <p>
              Motivo informado:{' '}
              {condominium.motivo_rejeicao || 'A equipe ainda não registrou um motivo específico.'}
            </p>
            {condominium.analises.map((analysis, index) => (
              <p key={`${analysis.em}-${index}`}>
                {new Date(analysis.em).toLocaleString('pt-BR')} · {analysis.evento}
                {analysis.motivo ? `: ${analysis.motivo}` : ''}
              </p>
            ))}
          </Notice>
        )}
        {!loading && condominium?.status === 'desativado' && (
          <Notice tone="alert">
            Este condomínio está desativado. A edição administrativa está bloqueada.
          </Notice>
        )}
        {condominium?.status !== 'desativado' && (
          <>
            <Card className={styles.card}>
              <Heading level={2} size="md">
                Dados do condomínio
              </Heading>
              <form className={styles.form} onSubmit={(event) => void saveCondominium(event)}>
                <Input
                  label="Nome do condomínio"
                  required
                  value={name}
                  onChange={(event) => {
                    setName(event.target.value)
                    setDetailsDirty(true)
                  }}
                  disabled={busy}
                />
                <Input
                  label="CNPJ"
                  required
                  inputMode="numeric"
                  value={cnpj}
                  onChange={(event) => {
                    setCnpj(event.target.value)
                    setDetailsDirty(true)
                  }}
                  disabled={busy}
                />
                <Input
                  label="CEP"
                  value={address.cep ?? ''}
                  onChange={(event) => {
                    setAddress({ ...address, cep: event.target.value })
                    setDetailsDirty(true)
                  }}
                  disabled={busy}
                />
                <Input
                  label="Logradouro"
                  value={address.logradouro ?? ''}
                  onChange={(event) => {
                    setAddress({ ...address, logradouro: event.target.value })
                    setDetailsDirty(true)
                  }}
                  disabled={busy}
                />
                <div className={styles.row}>
                  <Input
                    label="Número"
                    value={address.numero ?? ''}
                    onChange={(event) => {
                      setAddress({ ...address, numero: event.target.value })
                      setDetailsDirty(true)
                    }}
                    disabled={busy}
                  />
                  <Input
                    label="Complemento"
                    value={address.complemento ?? ''}
                    onChange={(event) => {
                      setAddress({ ...address, complemento: event.target.value })
                      setDetailsDirty(true)
                    }}
                    disabled={busy}
                  />
                </div>
                <Input
                  label="Bairro"
                  value={address.bairro ?? ''}
                  onChange={(event) => {
                    setAddress({ ...address, bairro: event.target.value })
                    setDetailsDirty(true)
                  }}
                  disabled={busy}
                />
                <div className={styles.row}>
                  <Input
                    label="Cidade"
                    value={address.cidade ?? ''}
                    onChange={(event) => {
                      setAddress({ ...address, cidade: event.target.value })
                      setDetailsDirty(true)
                    }}
                    disabled={busy}
                  />
                  <Input
                    label="UF"
                    maxLength={2}
                    value={address.uf ?? ''}
                    onChange={(event) => {
                      setAddress({ ...address, uf: event.target.value.toUpperCase() })
                      setDetailsDirty(true)
                    }}
                    disabled={busy}
                  />
                </div>
                <Select
                  label="Responsável pela alteração"
                  required
                  value={responsibleId}
                  options={responsibles.map((item) => ({ value: item.id, label: item.nome }))}
                  onChange={(event) => setResponsibleId(event.target.value)}
                  disabled={busy || !responsibles.length}
                />
                {!responsibles.length && (
                  <Notice tone="warning">
                    Cadastre um responsável na tela de conta de funcionários para autorizar
                    alterações.
                  </Notice>
                )}
                <Button type="submit" loading={busy} disabled={!responsibleId}>
                  Salvar dados
                </Button>
              </form>
            </Card>
            {condominium?.status === 'rejeitado' && (
              <Card className={styles.card}>
                <Heading level={2} size="md">
                  Reenviar para análise
                </Heading>
                <Text>Salve as correções acima antes de reenviar o cadastro.</Text>
                {(detailsDirty || structureDrafts.size > 0) && (
                  <Notice tone="warning">
                    Salve os dados e as alterações da estrutura antes de reenviar o cadastro.
                  </Notice>
                )}
                <Button
                  disabled={
                    !responsibleId ||
                    busy ||
                    !canResendRegistration(detailsDirty, structureDrafts.size > 0)
                  }
                  loading={busy}
                  onClick={() =>
                    void perform(
                      async () => {
                        const updated = await api.resendRegistration(responsibleId)
                        setCondominium(updated)
                        await client.restore()
                      },
                      'Cadastro reenviado para análise.',
                      false,
                    )
                  }
                >
                  Reenviar cadastro
                </Button>
              </Card>
            )}
            <Card className={styles.card}>
              <Heading level={2} size="md">
                Estrutura
              </Heading>
              <Select
                label="Responsável pelas alterações"
                required
                value={responsibleId}
                options={responsibles.map((item) => ({ value: item.id, label: item.nome }))}
                onChange={(event) => setResponsibleId(event.target.value)}
                disabled={busy || !responsibles.length}
              />
              {blocks.map((block) => (
                <BlockEditor
                  key={`${block.id}:${block.nome}:${block.ativo}`}
                  block={block}
                  busy={busy}
                  onDirty={markStructureDraft}
                  onSave={(id, value, active, toggle) =>
                    updateStructure('blocos', id, value, 0, active, toggle)
                  }
                  onSaveFloor={(id, value, order, active, toggle) =>
                    updateStructure('andares', id, value, order, active, toggle)
                  }
                  onSaveUnit={(id, value, active, toggle) =>
                    updateStructure('unidades', id, value, 0, active, toggle)
                  }
                />
              ))}
              {!blocks.length && <Text>Nenhum bloco cadastrado.</Text>}
              <form className={styles.row} onSubmit={(event) => void addStructure('block', event)}>
                <Input
                  label="Novo bloco"
                  value={newBlock}
                  onChange={(event) => {
                    setNewBlock(event.target.value)
                    markStructureDraft('new-block', Boolean(event.target.value.trim()))
                  }}
                  required
                  disabled={busy}
                />
                <Button type="submit" loading={busy}>
                  Adicionar bloco
                </Button>
              </form>
              <form className={styles.row} onSubmit={(event) => void addStructure('floor', event)}>
                <Select
                  label="Bloco do novo andar"
                  value={blockId}
                  options={blocks.map((block) => ({ value: block.id, label: block.nome }))}
                  onChange={(event) => setBlockId(event.target.value)}
                />
                <Input
                  label="Novo andar"
                  value={newFloor}
                  onChange={(event) => {
                    setNewFloor(event.target.value)
                    markStructureDraft('new-floor', Boolean(event.target.value.trim()))
                  }}
                  required
                  disabled={busy}
                />
                <Button type="submit" loading={busy} disabled={!blockId}>
                  Adicionar andar
                </Button>
              </form>
              <form className={styles.row} onSubmit={(event) => void addStructure('unit', event)}>
                <Select
                  label="Andar da nova unidade"
                  value={floorId}
                  options={floors.map((floor) => ({
                    value: floor.id,
                    label: `${floor.blocoNome} · ${floor.nome}`,
                  }))}
                  onChange={(event) => setFloorId(event.target.value)}
                />
                <Input
                  label="Identificação da unidade"
                  value={newUnit}
                  onChange={(event) => {
                    setNewUnit(event.target.value)
                    markStructureDraft('new-unit', Boolean(event.target.value.trim()))
                  }}
                  required
                  disabled={busy}
                />
                <Button type="submit" loading={busy} disabled={!floorId}>
                  Adicionar unidade
                </Button>
              </form>
            </Card>
          </>
        )}
      </main>
    </OperationsLayout>
  )
}

function BlockEditor({
  block,
  busy,
  onSave,
  onSaveFloor,
  onSaveUnit,
  onDirty,
}: {
  block: BlockRecord
  busy: boolean
  onSave: (id: string, value: string, active: boolean, toggle?: boolean) => void
  onSaveFloor: (id: string, value: string, order: number, active: boolean, toggle?: boolean) => void
  onSaveUnit: (id: string, value: string, active: boolean, toggle?: boolean) => void
  onDirty: (id: string, pending: boolean) => void
}) {
  const [blockName, setBlockName] = useState(block.nome)
  return (
    <section className={styles.structureItem}>
      <div className={styles.row}>
        <Input
          label="Bloco"
          value={blockName}
          onChange={(event) => {
            setBlockName(event.target.value)
            onDirty(block.id, event.target.value !== block.nome)
          }}
          disabled={busy || !block.ativo}
        />
        <Button
          size="sm"
          variant="secondary"
          disabled={busy || !block.ativo}
          onClick={() => onSave(block.id, blockName, true)}
        >
          Salvar
        </Button>
        <Button
          size="sm"
          variant={block.ativo ? 'alert' : 'success'}
          disabled={busy || blockName !== block.nome}
          onClick={() => onSave(block.id, blockName, block.ativo, true)}
        >
          {block.ativo ? 'Desativar' : 'Reativar'}
        </Button>
      </div>
      {!block.ativo && <Text tone="secondary">Bloco inativo; permanece no histórico.</Text>}
      {block.andares.map((floor) => (
        <FloorEditor
          key={`${floor.id}:${floor.nome}:${floor.ordem}:${floor.ativo}`}
          floor={floor}
          busy={busy}
          onDirty={onDirty}
          onSave={onSaveFloor}
          onSaveUnit={onSaveUnit}
        />
      ))}
    </section>
  )
}

function FloorEditor({
  floor,
  busy,
  onSave,
  onSaveUnit,
  onDirty,
}: {
  floor: BlockRecord['andares'][number]
  busy: boolean
  onSave: (id: string, value: string, order: number, active: boolean, toggle?: boolean) => void
  onSaveUnit: (id: string, value: string, active: boolean, toggle?: boolean) => void
  onDirty: (id: string, pending: boolean) => void
}) {
  const [name, setName] = useState(floor.nome)
  const [order, setOrder] = useState(floor.ordem)
  return (
    <div className={styles.nested}>
      <div className={styles.row}>
        <Input
          label="Andar"
          value={name}
          onChange={(event) => {
            setName(event.target.value)
            onDirty(floor.id, event.target.value !== floor.nome || order !== floor.ordem)
          }}
          disabled={busy || !floor.ativo}
        />
        <Input
          label="Ordem"
          type="number"
          min={0}
          max={200}
          value={order}
          onChange={(event) => {
            const nextOrder = Number(event.target.value)
            setOrder(nextOrder)
            onDirty(floor.id, name !== floor.nome || nextOrder !== floor.ordem)
          }}
          disabled={busy || !floor.ativo}
        />
        <Button
          size="sm"
          variant="secondary"
          disabled={busy || !floor.ativo}
          onClick={() => onSave(floor.id, name, order, true)}
        >
          Salvar
        </Button>
        <Button
          size="sm"
          variant={floor.ativo ? 'alert' : 'success'}
          disabled={busy || name !== floor.nome || order !== floor.ordem}
          onClick={() => onSave(floor.id, name, order, floor.ativo, true)}
        >
          {floor.ativo ? 'Desativar' : 'Reativar'}
        </Button>
      </div>
      {floor.unidades.map((unit) => (
        <UnitEditor
          key={`${unit.id}:${unit.identificacao}:${unit.ativo}`}
          unit={unit}
          busy={busy}
          onSave={onSaveUnit}
          onDirty={onDirty}
        />
      ))}
    </div>
  )
}

function UnitEditor({
  unit,
  busy,
  onSave,
  onDirty,
}: {
  unit: BlockRecord['andares'][number]['unidades'][number]
  busy: boolean
  onSave: (id: string, value: string, active: boolean, toggle?: boolean) => void
  onDirty: (id: string, pending: boolean) => void
}) {
  const [name, setName] = useState(unit.identificacao)
  return (
    <div className={styles.row}>
      <Input
        label="Unidade"
        value={name}
        onChange={(event) => {
          setName(event.target.value)
          onDirty(unit.id, event.target.value !== unit.identificacao)
        }}
        disabled={busy || !unit.ativo}
      />
      <Button
        size="sm"
        variant="secondary"
        disabled={busy || !unit.ativo}
        onClick={() => onSave(unit.id, name, true)}
      >
        Salvar
      </Button>
      <Button
        size="sm"
        variant={unit.ativo ? 'alert' : 'success'}
        disabled={busy || name !== unit.identificacao}
        onClick={() => onSave(unit.id, name, unit.ativo, true)}
      >
        {unit.ativo ? 'Desativar' : 'Reativar'}
      </Button>
    </div>
  )
}
