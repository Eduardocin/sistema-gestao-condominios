import { useEffect, useRef, useState } from 'react'
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
import styles from '../resident/ResidentWorkspace.module.css'

type Item = {
  id: string
  nome: string
  cnpj: string | null
  status: string
  administracao: { nome: string; email: string } | null
  estrutura: { blocos: number; andares: number; unidades: number }
}
type Detail = Item & {
  blocos: {
    id: string
    nome: string
    andares: { id: string; nome: string; unidades: { id: string; identificacao: string }[] }[]
  }[]
  motivo_rejeicao: string | null
}
type Page = { items: Item[]; page: number; page_size: number; total: number }

export function ApprovalPage() {
  const { snapshot, client } = useAuth()
  const [status, setStatus] = useState('pendente')
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [list, setList] = useState<Page>()
  const [detail, setDetail] = useState<Detail>()
  const [detailLoading, setDetailLoading] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const submitting = useRef(false)

  useEffect(() => {
    if (!snapshot.identity?.administrador_plataforma) return
    const controller = new AbortController()
    client.http
      .get<Page>('/plataforma/condominios', {
        params: { status, busca: query || undefined, page, page_size: 20 },
        signal: controller.signal,
      })
      .then(({ data }) => setList(data))
      .catch(() => {
        if (!controller.signal.aborted) setError('Não foi possível carregar os condomínios.')
      })
    return () => controller.abort()
  }, [client, status, query, page, revision, snapshot.identity?.administrador_plataforma])

  if (!snapshot.identity?.administrador_plataforma) return <AccessDenied />

  async function open(id: string) {
    setError('')
    setSuccess('')
    setDetail(undefined)
    setReason('')
    setDetailLoading(true)
    try {
      const { data } = await client.http.get<Detail>(
        `/plataforma/condominios/${encodeURIComponent(id)}`,
      )
      setDetail(data)
    } catch {
      setError('Não foi possível carregar os detalhes do condomínio.')
    } finally {
      setDetailLoading(false)
    }
  }

  async function decide(action: 'aprovacao' | 'rejeicao') {
    if (!detail || submitting.current || (action === 'rejeicao' && !reason.trim())) return
    submitting.current = true
    setBusy(true)
    setError('')
    try {
      await client.http.post(
        `/plataforma/condominios/${encodeURIComponent(detail.id)}/${action}`,
        action === 'rejeicao' ? { motivo: reason.trim() } : {},
      )
      setDetail(undefined)
      setSuccess(action === 'aprovacao' ? 'Condomínio aprovado.' : 'Cadastro rejeitado.')
      setRevision((value) => value + 1)
    } catch {
      setError('Não foi possível concluir a análise. Atualize os dados e tente novamente.')
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }

  return (
    <OperationsLayout
      activeKey="approvals"
      navigation={[
        { key: 'overview', label: 'Visão geral', to: '/app/plataforma', symbol: '⌂' },
        { key: 'approvals', label: 'Condomínios', to: '/app/plataforma/condominios', symbol: '▦' },
      ]}
      workspace={{
        name: 'Plataforma',
        profile: 'Administrador',
        tools: <Link to="/app/plataforma">Voltar</Link>,
      }}
    >
      <section className={styles.content}>
        <Heading level={1}>Análise de condomínios</Heading>
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
        <Card className={styles.content}>
          <form
            className={styles.filters}
            onSubmit={(event) => {
              event.preventDefault()
              setPage(1)
              setQuery(search)
              setRevision((value) => value + 1)
            }}
          >
            <Input
              label="Buscar condomínio"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <Select
              label="Situação"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value)
                setPage(1)
                setList(undefined)
              }}
              options={[
                { value: 'pendente', label: 'Pendente' },
                { value: 'ativo', label: 'Ativo' },
                { value: 'rejeitado', label: 'Rejeitado' },
                { value: 'desativado', label: 'Desativado' },
              ]}
            />
            <Button type="submit">Buscar</Button>
          </form>
          {!list && !error && <Text>Carregando condomínios…</Text>}
          {list?.items.length === 0 && <Text>Nenhum condomínio encontrado.</Text>}
          {list?.items.map((item) => (
            <article className={styles.listItem} key={item.id}>
              <Heading level={2} size="sm">
                {item.nome}
              </Heading>
              <Text>
                CNPJ {item.cnpj ?? 'Não informado'} · {item.estrutura.unidades} unidades
              </Text>
              <div>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={detailLoading || busy}
                  onClick={() => void open(item.id)}
                >
                  Ver detalhes
                </Button>
              </div>
            </article>
          ))}
          {list && list.total > list.page_size && (
            <div className={styles.pagination}>
              <Button variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                Anterior
              </Button>
              <Text>
                Página {page} de {Math.ceil(list.total / list.page_size)}
              </Text>
              <Button
                variant="secondary"
                disabled={page * list.page_size >= list.total}
                onClick={() => setPage(page + 1)}
              >
                Próxima
              </Button>
            </div>
          )}
        </Card>
        {detail && (
          <Card className={styles.content}>
            <Heading level={2}>{detail.nome}</Heading>
            <Text>
              CNPJ {detail.cnpj ?? 'Não informado'} · Situação {detail.status}
            </Text>
            {detail.administracao && (
              <Text>
                Administração {detail.administracao.nome} · {detail.administracao.email}
              </Text>
            )}
            {detail.blocos.map((block) => (
              <div key={block.id}>
                <Heading level={3} size="sm">
                  {block.nome}
                </Heading>
                {block.andares.map((floor) => (
                  <Text key={floor.id}>
                    {floor.nome} · {floor.unidades.map((unit) => unit.identificacao).join(', ')}
                  </Text>
                ))}
              </div>
            ))}
            {detail.motivo_rejeicao && (
              <Notice tone="warning">Motivo da rejeição: {detail.motivo_rejeicao}</Notice>
            )}
            {detail.status === 'pendente' && (
              <>
                <Input
                  label="Motivo da rejeição"
                  value={reason}
                  maxLength={500}
                  disabled={busy}
                  onChange={(event) => setReason(event.target.value)}
                />
                <div className={styles.actions}>
                  <Button disabled={busy} onClick={() => void decide('aprovacao')}>
                    Aprovar condomínio
                  </Button>
                  <Button
                    variant="alert"
                    disabled={busy || !reason.trim()}
                    onClick={() => void decide('rejeicao')}
                  >
                    Rejeitar cadastro
                  </Button>
                </div>
              </>
            )}
          </Card>
        )}
      </section>
    </OperationsLayout>
  )
}
