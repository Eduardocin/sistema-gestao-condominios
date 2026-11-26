import { useEffect, useState } from 'react'
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
import styles from '../resident/ResidentWorkspace.module.css'
import { buildNoticePayload, localDate } from './notice-form'

type NoticeItem = {
  id: string
  titulo: string
  texto: string
  importante: boolean
  inicio_em: string
  fim_em: string
  situacao: string
  unidade: { id: string } | null
}
type Person = { id: string; nome: string; ativo: boolean }
type NoticePage = { items: NoticeItem[]; page: number; page_size: number; total: number }

export function NoticesPage() {
  const { snapshot, client } = useAuth()
  const [items, setItems] = useState<NoticePage>()
  const [people, setPeople] = useState<Person[]>([])
  const [status, setStatus] = useState('todos')
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [edit, setEdit] = useState<NoticeItem | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [busy, setBusy] = useState(false)
  const [responsible, setResponsible] = useState('')
  const [confirmId, setConfirmId] = useState('')
  const allowed =
    snapshot.identity?.condominio?.perfil === 'administracao' &&
    snapshot.identity.condominio.status === 'ativo'

  useEffect(() => {
    if (!allowed) return
    const controller = new AbortController()
    Promise.all([
      client.http.get<NoticePage>('/avisos', {
        params: { situacao: status, page, page_size: 20 },
        signal: controller.signal,
      }),
      client.http.get<Person[]>('/responsaveis-administracao', { signal: controller.signal }),
    ])
      .then(([notices, persons]) => {
        setItems(notices.data)
        setPeople(persons.data.filter((person) => person.ativo))
      })
      .catch(() => {
        if (!controller.signal.aborted) setError('Não foi possível carregar avisos e responsáveis.')
      })
    return () => controller.abort()
  }, [client, allowed, status, page, revision])

  if (!allowed) return <AccessDenied />

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const form = new FormData(event.currentTarget)
    const result = buildNoticePayload({
      titulo: String(form.get('titulo')),
      texto: String(form.get('texto')),
      inicio: String(form.get('inicio')),
      fim: String(form.get('fim')),
      importante: form.get('importante') === 'on',
      responsavelId: responsible,
    })
    if (!result.ok) {
      setError(result.message)
      return
    }
    const data = result.payload
    setBusy(true)
    setError('')
    setSuccess('')
    try {
      if (edit) await client.http.put(`/avisos/${encodeURIComponent(edit.id)}`, data)
      else await client.http.post('/avisos', data)
      setShowForm(false)
      setEdit(null)
      setSuccess('Aviso salvo.')
      setRevision((value) => value + 1)
    } catch {
      setError('Não foi possível salvar o aviso. Confira os dados e tente novamente.')
    } finally {
      setBusy(false)
    }
  }

  async function closeNotice() {
    if (!confirmId || !responsible || busy) return
    setBusy(true)
    setError('')
    try {
      await client.http.post(`/avisos/${encodeURIComponent(confirmId)}/encerramento`, {
        responsavel_id: responsible,
      })
      setConfirmId('')
      setSuccess('Aviso encerrado.')
      setRevision((value) => value + 1)
    } catch {
      setError('Não foi possível encerrar o aviso. Atualize a lista e tente novamente.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <OperationsLayout
      activeKey="notices"
      navigation={[
        { key: 'overview', label: 'Visão geral', to: '/app/administracao', symbol: '⌂' },
        { key: 'notices', label: 'Avisos', to: '/app/administracao/avisos', symbol: '◇' },
      ]}
      workspace={{
        name: snapshot.identity?.condominio?.nome ?? 'Condomínio',
        profile: 'Administração',
        tools: <Link to="/app/administracao">Voltar</Link>,
      }}
    >
      <section className={styles.content}>
        <Heading level={1}>Avisos do condomínio</Heading>
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
          <Select
            label="Responsável pela ação"
            value={responsible}
            options={people.map((person) => ({ value: person.id, label: person.nome }))}
            onChange={(event) => setResponsible(event.target.value)}
          />
          {!people.length && (
            <Notice tone="warning">Cadastre um responsável ativo para publicar avisos.</Notice>
          )}
          <Select
            label="Situação"
            value={status}
            options={[
              { value: 'todos', label: 'Todos' },
              { value: 'vigentes', label: 'Vigentes' },
              { value: 'agendados', label: 'Agendados' },
              { value: 'encerrados', label: 'Encerrados' },
            ]}
            onChange={(event) => {
              setStatus(event.target.value)
              setPage(1)
            }}
          />
          <div>
            <Button
              onClick={() => {
                setEdit(null)
                setShowForm(true)
                setError('')
                setSuccess('')
              }}
            >
              Novo aviso
            </Button>
          </div>
          {showForm && (
            <form
              key={edit?.id ?? 'new'}
              className={styles.form}
              onSubmit={(event) => void save(event)}
            >
              <Heading level={2}>{edit ? 'Editar aviso' : 'Novo aviso'}</Heading>
              <Input
                label="Título"
                name="titulo"
                required
                maxLength={120}
                defaultValue={edit?.titulo}
                disabled={busy}
              />
              <label>
                Texto{' '}
                <textarea
                  name="texto"
                  required
                  maxLength={2000}
                  rows={4}
                  defaultValue={edit?.texto}
                  disabled={busy}
                />
              </label>
              <Input
                label="Início"
                name="inicio"
                type="datetime-local"
                required
                defaultValue={edit ? localDate(edit.inicio_em) : ''}
                disabled={busy}
              />
              <Input
                label="Término"
                name="fim"
                type="datetime-local"
                required
                defaultValue={edit ? localDate(edit.fim_em) : ''}
                disabled={busy}
              />
              <label>
                <input
                  type="checkbox"
                  name="importante"
                  defaultChecked={edit?.importante}
                  disabled={busy}
                />{' '}
                Aviso importante
              </label>
              <div className={styles.actions}>
                <Button type="submit" loading={busy} disabled={!responsible}>
                  Salvar aviso
                </Button>
                <Button variant="secondary" disabled={busy} onClick={() => setShowForm(false)}>
                  Cancelar
                </Button>
              </div>
            </form>
          )}
          {items?.items.length === 0 && <Text>Nenhum aviso encontrado.</Text>}
          {items?.items.map((item) => (
            <article key={item.id} className={styles.listItem}>
              <Heading level={2} size="sm">
                {item.titulo}
              </Heading>
              <Text>{item.texto}</Text>
              <Text size="sm">
                {item.situacao} · {new Date(item.inicio_em).toLocaleString('pt-BR')} até{' '}
                {new Date(item.fim_em).toLocaleString('pt-BR')}
              </Text>
              {(item.situacao === 'vigente' || item.situacao === 'agendado') && (
                <div className={styles.actions}>
                  {!item.unidade && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => {
                        setEdit(item)
                        setShowForm(true)
                        setSuccess('')
                        setError('')
                      }}
                    >
                      Editar
                    </Button>
                  )}
                  <Button
                    variant="alert"
                    size="sm"
                    disabled={!responsible}
                    onClick={() => setConfirmId(item.id)}
                  >
                    Encerrar
                  </Button>
                </div>
              )}
              {confirmId === item.id && (
                <Notice tone="warning">
                  Encerrar este aviso agora?
                  <div className={styles.actions}>
                    <Button loading={busy} onClick={() => void closeNotice()}>
                      Confirmar
                    </Button>
                    <Button variant="secondary" disabled={busy} onClick={() => setConfirmId('')}>
                      Voltar
                    </Button>
                  </div>
                </Notice>
              )}
            </article>
          ))}
          {items && items.total > items.page_size && (
            <div className={styles.pagination}>
              <Button variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                Anterior
              </Button>
              <Text>Página {page}</Text>
              <Button
                variant="secondary"
                disabled={page * items.page_size >= items.total}
                onClick={() => setPage(page + 1)}
              >
                Próxima
              </Button>
            </div>
          )}
        </Card>
      </section>
    </OperationsLayout>
  )
}
