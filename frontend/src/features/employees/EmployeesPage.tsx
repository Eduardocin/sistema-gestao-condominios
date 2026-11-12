import { useEffect, useMemo, useState } from 'react'
import axios from 'axios'
import { Link } from 'react-router'
import {
  Badge,
  Button,
  Card,
  Heading,
  Input,
  Modal,
  Notice,
  OperationsLayout,
  Select,
  Table,
  Text,
} from '../../components'
import { useAuth } from '../auth/context'
import { AccessDenied } from '../auth/SessionPages'
import { createEmployeesClient } from './api'
import type { Employee, EmployeeList, Responsible } from './api'
import styles from './EmployeesPage.module.css'

function message(error: unknown) {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 409)
      return 'Este cadastro já existe ou o funcionário já foi desligado. Atualize a lista.'
    if (error.response?.status === 422) return 'Confira os dados e escolha um responsável ativo.'
    if (error.response?.status === 403)
      return 'Seu acesso não permite gerenciar funcionários neste condomínio.'
  }
  return 'Não foi possível concluir a operação. Tente novamente.'
}

export function EmployeesPage() {
  const { snapshot } = useAuth()
  const condominium = snapshot.identity?.condominio
  if (
    !condominium ||
    condominium.perfil !== 'administracao' ||
    condominium.status !== 'ativo' ||
    snapshot.identity?.administrador_plataforma
  )
    return <AccessDenied />
  return <EmployeesContent key={condominium.id} name={condominium.nome} />
}

function EmployeesContent({ name }: { name: string }) {
  const { client, snapshot } = useAuth()
  const api = useMemo(() => createEmployeesClient(client.http), [client])
  const [list, setList] = useState<EmployeeList | null>(null)
  const [responsibles, setResponsibles] = useState<Responsible[]>([])
  const [query, setQuery] = useState({ active: true, search: '', page: 1 })
  const [revision, setRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [dismissEmployee, setDismissEmployee] = useState<Employee | null>(null)

  useEffect(() => {
    let current = true
    Promise.all([api.list(query), api.responsibles()])
      .then(([employees, people]) => {
        if (!current) return
        setList(employees)
        setResponsibles(people.filter((person) => person.ativo))
        setLoadError(null)
      })
      .catch((cause: unknown) => {
        if (current) setLoadError(message(cause))
      })
      .finally(() => {
        if (current) setLoading(false)
      })
    return () => {
      current = false
    }
  }, [api, query, revision])

  function reload() {
    setLoading(true)
    setLoadError(null)
    setRevision((value) => value + 1)
  }

  async function mutate(action: () => Promise<unknown>, confirmation: string, after?: () => void) {
    if (pending) return
    setPending(true)
    setError(null)
    setSuccess(null)
    try {
      await action()
      after?.()
      setSuccess(confirmation)
      reload()
    } catch (cause) {
      setError(message(cause))
    } finally {
      setPending(false)
    }
  }

  function create(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    void mutate(
      () =>
        api.create({
          nome: String(data.get('nome')),
          funcao: data.get('funcao') as Employee['funcao'],
          telefone: String(data.get('telefone')),
          email: String(data.get('email')),
          responsavel_id: String(data.get('responsavel_id')),
        }),
      'Funcionário cadastrado.',
      () => setCreateOpen(false),
    )
  }

  const responsibleOptions = responsibles.map((person) => ({
    value: person.id,
    label: person.nome,
  }))
  const tools = (
    <div className={styles.actions}>
      {snapshot.condominiums.length > 1 && (
        <Link to="/selecionar-condominio">Trocar condomínio</Link>
      )}
      <Button variant="secondary" size="sm" onClick={() => client.logout()}>
        Sair
      </Button>
    </div>
  )
  return (
    <OperationsLayout
      activeKey="employees"
      navigation={[
        { key: 'overview', label: 'Visão geral', to: '/app/administracao', symbol: '⌂' },
        {
          key: 'employees',
          label: 'Funcionários',
          to: '/app/administracao/funcionarios',
          symbol: '♙',
        },
      ]}
      workspace={{ name, profile: 'Administração', tools }}
    >
      <div className={styles.content}>
        <div>
          <Badge variant="primary">Administração</Badge>
          <Heading level={1}>Funcionários</Heading>
          <Text tone="secondary">
            Gerencie os nomes que identificam os registros da portaria. O cadastro de funcionário
            não cria uma conta de acesso.
          </Text>
        </div>
        {success && (
          <Notice tone="success" role="status">
            {success}
          </Notice>
        )}
        {error && !createOpen && !dismissEmployee && (
          <Notice tone="alert" role="alert">
            {error}
          </Notice>
        )}
        <Card>
          <Heading level={2} size="md">
            Responsáveis da Administração
          </Heading>
          <Text tone="secondary">
            Cadastre ao menos um responsável para registrar quem autorizou cada cadastro ou
            desligamento.
          </Text>
          {!loading && !loadError && (
            <Text size="sm">
              {responsibles.length
                ? `Responsáveis ativos: ${responsibles.map((person) => person.nome).join(', ')}.`
                : 'Nenhum responsável cadastrado. Comece por este formulário.'}
            </Text>
          )}
          <form
            className={styles.responsibleForm}
            onSubmit={(event) => {
              event.preventDefault()
              const form = event.currentTarget
              const data = new FormData(form)
              void mutate(
                () => api.addResponsible(String(data.get('responsavel_nome'))),
                'Responsável cadastrado.',
                () => form.reset(),
              )
            }}
          >
            <Input
              label="Nome do responsável"
              name="responsavel_nome"
              required
              minLength={1}
              maxLength={100}
              disabled={pending || loading || !!loadError}
            />
            <Button type="submit" loading={pending} disabled={loading || !!loadError}>
              Adicionar responsável
            </Button>
          </form>
        </Card>
        <Card>
          <div className={styles.header}>
            <Heading level={2} size="md">
              Equipe do condomínio
            </Heading>
            <Button
              onClick={() => {
                setError(null)
                setCreateOpen(true)
              }}
              disabled={pending || loading || !!loadError || !responsibles.length}
            >
              Cadastrar funcionário
            </Button>
          </div>
          <form
            className={styles.filters}
            onSubmit={(event) => {
              event.preventDefault()
              const data = new FormData(event.currentTarget)
              setLoading(true)
              setQuery({
                active: data.get('ativo') === 'true',
                search: String(data.get('busca') ?? ''),
                page: 1,
              })
            }}
          >
            <Input
              label="Buscar por nome"
              name="busca"
              type="search"
              maxLength={120}
              disabled={pending || loading}
            />
            <Select
              label="Situação"
              name="ativo"
              defaultValue="true"
              options={[
                { value: 'true', label: 'Ativos' },
                { value: 'false', label: 'Desligados' },
              ]}
              disabled={pending || loading}
            />
            <Button type="submit" variant="secondary" disabled={pending || loading}>
              Filtrar
            </Button>
          </form>
          {loading ? (
            <Text role="status">Carregando funcionários e responsáveis…</Text>
          ) : loadError ? (
            <Notice tone="alert" role="alert">
              {loadError}
              <div className={styles.actions}>
                <Button onClick={reload}>Tentar novamente</Button>
              </div>
            </Notice>
          ) : (
            <>
              <Table
                caption="Funcionários do condomínio"
                headers={['Nome', 'Função', 'Contato', 'Situação', 'Ação']}
                emptyMessage={
                  query.active
                    ? 'Nenhum funcionário ativo encontrado.'
                    : 'Nenhum funcionário desligado encontrado.'
                }
                rows={(list?.items ?? []).map((employee) => [
                  employee.nome,
                  employee.funcao === 'porteiro' ? 'Porteiro' : 'Segurança',
                  <span>
                    {employee.email}
                    <br />
                    {employee.telefone}
                  </span>,
                  <Badge variant={employee.ativo ? 'success' : 'neutral'}>
                    {employee.ativo ? 'Ativo' : 'Desligado'}
                  </Badge>,
                  employee.ativo ? (
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={pending || !responsibles.length}
                      onClick={() => {
                        setError(null)
                        setDismissEmployee(employee)
                      }}
                      aria-label={`Desligar ${employee.nome}`}
                    >
                      Desligar
                    </Button>
                  ) : (
                    '—'
                  ),
                ])}
              />
              {list && list.total > 0 && (
                <div className={styles.pagination}>
                  <Text size="sm">
                    Página {list.page} · {list.total} funcionário(s)
                  </Text>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={pending || query.page <= 1}
                    onClick={() => {
                      setLoading(true)
                      setQuery({ ...query, page: query.page - 1 })
                    }}
                  >
                    Anterior
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={pending || list.page * list.page_size >= list.total}
                    onClick={() => {
                      setLoading(true)
                      setQuery({ ...query, page: query.page + 1 })
                    }}
                  >
                    Próxima
                  </Button>
                </div>
              )}
            </>
          )}
        </Card>
      </div>
      <Modal
        isOpen={createOpen}
        onClose={() => {
          if (!pending) setCreateOpen(false)
        }}
        title="Cadastrar funcionário"
      >
        <form className={styles.form} onSubmit={create}>
          <Input
            label="Nome"
            name="nome"
            required
            minLength={1}
            maxLength={120}
            disabled={pending}
          />
          <Select
            label="Função"
            name="funcao"
            required
            options={[
              { value: 'porteiro', label: 'Porteiro' },
              { value: 'seguranca', label: 'Segurança' },
            ]}
            disabled={pending}
          />
          <Input
            label="Telefone com DDD"
            name="telefone"
            type="tel"
            required
            pattern="[0-9]{10,11}"
            minLength={10}
            maxLength={11}
            hint="Somente números, incluindo o DDD."
            disabled={pending}
          />
          <Input
            label="E-mail"
            name="email"
            type="email"
            required
            maxLength={254}
            disabled={pending}
          />
          <Select
            label="Responsável pelo cadastro"
            name="responsavel_id"
            required
            options={responsibleOptions}
            disabled={pending}
          />
          {error && (
            <Notice tone="alert" role="alert">
              {error}
            </Notice>
          )}
          <div className={styles.actions}>
            <Button type="submit" loading={pending}>
              Cadastrar
            </Button>
            <Button variant="secondary" disabled={pending} onClick={() => setCreateOpen(false)}>
              Cancelar
            </Button>
          </div>
        </form>
      </Modal>
      <Modal
        isOpen={!!dismissEmployee}
        onClose={() => {
          if (!pending) setDismissEmployee(null)
        }}
        title="Desligar funcionário"
      >
        <form
          className={styles.form}
          onSubmit={(event) => {
            event.preventDefault()
            const data = new FormData(event.currentTarget)
            if (dismissEmployee)
              void mutate(
                () => api.dismiss(dismissEmployee.id, String(data.get('responsavel_id'))),
                'Funcionário desligado. Os registros anteriores foram preservados.',
                () => setDismissEmployee(null),
              )
          }}
        >
          <Text>
            Confirme o desligamento de <strong>{dismissEmployee?.nome}</strong>. O nome deixará de
            aparecer nas novas operações da portaria.
          </Text>
          <Select
            label="Responsável pelo desligamento"
            name="responsavel_id"
            required
            options={responsibleOptions}
            disabled={pending}
          />
          {error && (
            <Notice tone="alert" role="alert">
              {error}
            </Notice>
          )}
          <div className={styles.actions}>
            <Button type="submit" loading={pending}>
              Confirmar desligamento
            </Button>
            <Button variant="secondary" disabled={pending} onClick={() => setDismissEmployee(null)}>
              Cancelar
            </Button>
          </div>
        </form>
      </Modal>
    </OperationsLayout>
  )
}
