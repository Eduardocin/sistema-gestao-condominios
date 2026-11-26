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
  type ResponsibleRecord,
  type SharedEmployeeAccount,
} from './condominium-admin-api'
import styles from './CondominiumSettingsPage.module.css'

export function SharedAccountPage() {
  const { client, snapshot } = useAuth()
  const identity = snapshot.identity
  const api = useMemo(() => createCondominiumAdminApi(client.http), [client])
  const [account, setAccount] = useState<SharedEmployeeAccount>()
  const [login, setLogin] = useState('')
  const [password, setPassword] = useState('')
  const [responsibles, setResponsibles] = useState<ResponsibleRecord[]>([])
  const [responsibleId, setResponsibleId] = useState('')
  const [newName, setNewName] = useState('')
  const [editing, setEditing] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      const list = await api.responsibles(signal)
      setResponsibles(list)
      setResponsibleId((current) =>
        list.some((item) => item.id === current) ? current : (list[0]?.id ?? ''),
      )
      try {
        const existing = await api.sharedAccount(signal)
        setAccount(existing)
        setLogin(existing.login)
      } catch (cause) {
        if ((cause as { response?: { status?: number } }).response?.status !== 404) throw cause
        setAccount(undefined)
      }
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
        const list = await api.responsibles(controller.signal)
        if (controller.signal.aborted) return
        setResponsibles(list)
        setResponsibleId((current) =>
          list.some((item) => item.id === current) ? current : (list[0]?.id ?? ''),
        )
        try {
          const existing = await api.sharedAccount(controller.signal)
          if (controller.signal.aborted) return
          setAccount(existing)
          setLogin(existing.login)
        } catch (cause) {
          if ((cause as { response?: { status?: number } }).response?.status !== 404) throw cause
          if (!controller.signal.aborted) setAccount(undefined)
        }
      } catch {
        if (!controller.signal.aborted)
          setError('Não foi possível carregar a conta e os responsáveis.')
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

  async function perform(action: () => Promise<unknown>, message: string) {
    if (busy) return
    setBusy(true)
    setError('')
    setSuccess('')
    try {
      await action()
      await refresh()
      setSuccess(message)
    } catch (cause) {
      setError(
        condominiumAdminError(
          cause,
          'Não foi possível concluir. Confira os dados e tente novamente.',
        ),
      )
    } finally {
      setBusy(false)
    }
  }

  async function saveAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!responsibleId) {
      setError('Cadastre um responsável ativo antes de salvar as credenciais.')
      return
    }
    if (!password) {
      setError('Informe uma senha para criar ou atualizar as credenciais.')
      return
    }
    await perform(
      async () => {
        await api.saveSharedAccount({ login, senha: password, responsavel_id: responsibleId })
        setPassword('')
      },
      account ? 'Credenciais atualizadas.' : 'Conta compartilhada criada.',
    )
  }

  async function addResponsible(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await perform(async () => {
      const created = await api.createResponsible(newName.trim())
      setNewName('')
      setResponsibleId(created.id)
    }, 'Responsável adicionado.')
  }

  const name = identity.condominio?.nome ?? 'Condomínio'
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
      activeKey="shared"
      navigation={nav}
      workspace={{
        name,
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
        <Heading level={1}>Conta de funcionários e responsáveis</Heading>
        <Text tone="secondary">
          A conta compartilhada dá acesso aos funcionários deste condomínio. A senha nunca é exibida
          depois de salva.
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
        {loading && <Text>Carregando informações…</Text>}
        <Card className={styles.card}>
          <Heading level={2} size="md">
            Acesso compartilhado
          </Heading>
          {account && (
            <Notice tone="primary">
              Conta configurada: {account.login}. Última atualização:{' '}
              {account.atualizada_em
                ? new Date(account.atualizada_em).toLocaleString('pt-BR')
                : 'não informada'}
              .
            </Notice>
          )}
          {!account && !loading && (
            <Notice tone="warning">Ainda não há conta compartilhada cadastrada.</Notice>
          )}
          <form className={styles.form} onSubmit={(event) => void saveAccount(event)}>
            <Input
              label="E-mail de acesso"
              type="email"
              required
              value={login}
              onChange={(event) => setLogin(event.target.value)}
              disabled={busy}
            />
            <Input
              label="Nova senha"
              type="password"
              required
              hint="De 8 a 128 caracteres, com pelo menos uma letra e um número. Informe novamente para trocar a senha."
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              disabled={busy}
              autoComplete="new-password"
            />
            <ResponsibleSelect
              responsibles={responsibles}
              value={responsibleId}
              disabled={busy}
              onChange={setResponsibleId}
            />
            <Button type="submit" loading={busy} disabled={!responsibleId}>
              {account ? 'Atualizar acesso' : 'Criar acesso'}
            </Button>
          </form>
        </Card>
        <Card className={styles.card}>
          <Heading level={2} size="md">
            Responsáveis por alterações
          </Heading>
          <Text>
            As alterações administrativas exigem que um responsável ativo fique registrado na
            auditoria.
          </Text>
          {responsibles.length === 0 && !loading && (
            <Notice tone="warning">Nenhum responsável ativo cadastrado.</Notice>
          )}
          {responsibles.map((item) => (
            <form
              key={item.id}
              className={styles.row}
              onSubmit={(event: FormEvent<HTMLFormElement>) => {
                event.preventDefault()
                void perform(
                  () => api.updateResponsible(item.id, editing[item.id] ?? item.nome),
                  'Responsável atualizado.',
                )
              }}
            >
              <Input
                label="Nome do responsável"
                required
                value={editing[item.id] ?? item.nome}
                onChange={(event) =>
                  setEditing((items) => ({ ...items, [item.id]: event.target.value }))
                }
                disabled={busy}
              />
              <Button size="sm" variant="secondary" type="submit" loading={busy}>
                Salvar nome
              </Button>
              <Button
                size="sm"
                variant="alert"
                type="button"
                disabled={busy || responsibles.length < 2}
                onClick={() =>
                  window.confirm(
                    `Desativar ${item.nome}? Esta ação fica registrada no histórico.`,
                  ) &&
                  void perform(() => api.deactivateResponsible(item.id), 'Responsável desativado.')
                }
              >
                Desativar
              </Button>
            </form>
          ))}
          {responsibles.length === 1 && (
            <Text size="sm" tone="secondary">
              O único responsável ativo não pode ser desativado. Cadastre outro primeiro.
            </Text>
          )}
          <form
            className={styles.row}
            onSubmit={(event: FormEvent<HTMLFormElement>) => void addResponsible(event)}
          >
            <Input
              label="Novo responsável"
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              required
              disabled={busy}
            />
            <Button type="submit" loading={busy}>
              Adicionar responsável
            </Button>
          </form>
        </Card>
      </main>
    </OperationsLayout>
  )
}

function ResponsibleSelect({
  responsibles,
  value,
  disabled,
  onChange,
}: {
  responsibles: ResponsibleRecord[]
  value: string
  disabled: boolean
  onChange: (id: string) => void
}) {
  return (
    <Select
      label="Responsável pela alteração"
      value={value}
      required
      disabled={disabled || responsibles.length === 0}
      onChange={(event) => onChange(event.target.value)}
      options={responsibles.map((item) => ({ value: item.id, label: item.nome }))}
    />
  )
}
