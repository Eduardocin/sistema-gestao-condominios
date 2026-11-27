import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { Button, Card, Heading, Notice, OperationsLayout, Select, Text } from '../../components'
import { useAuth } from '../auth/context'
import { AccessDenied } from '../auth/SessionPages'
import styles from '../resident/ResidentWorkspace.module.css'
import { adminNavigation } from '../auth/area-navigation'

type Unit = { id: string; identificacao: string; bloco: string | null; andar: string | null }
type Responsible = { id: string; nome: string; ativo: boolean }
type Detail = Unit & { chave: { codigo: string } | null }

export function AccessKeysPage() {
  const { snapshot, client } = useAuth()
  const [units, setUnits] = useState<Unit[]>([])
  const [responsibles, setResponsibles] = useState<Responsible[]>([])
  const [selected, setSelected] = useState('')
  const [responsible, setResponsible] = useState('')
  const [detail, setDetail] = useState<Detail>()
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [pending, setPending] = useState(false)
  const [confirm, setConfirm] = useState<'regeneracao' | 'revogacao'>()
  const allowed =
    snapshot.identity?.condominio?.perfil === 'administracao' &&
    snapshot.identity.condominio.status === 'ativo'

  useEffect(() => {
    if (!allowed) return
    const controller = new AbortController()
    Promise.all([
      client.http.get<{ items: Unit[]; total: number }>('/unidades', {
        params: { page, page_size: 20 },
        signal: controller.signal,
      }),
      client.http.get<Responsible[]>('/responsaveis-administracao', { signal: controller.signal }),
    ])
      .then(([unitResponse, responsibleResponse]) => {
        setUnits(unitResponse.data.items)
        setTotal(unitResponse.data.total)
        setResponsibles(responsibleResponse.data.filter((person) => person.ativo))
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError('Não foi possível consultar as unidades e responsáveis.')
      })
    return () => controller.abort()
  }, [client, allowed, page])

  useEffect(() => {
    if (!selected || !allowed) return
    const controller = new AbortController()
    client.http
      .get<Detail>(`/unidades/${encodeURIComponent(selected)}`, { signal: controller.signal })
      .then(({ data }) => setDetail(data))
      .catch(() => {
        if (!controller.signal.aborted) setError('Não foi possível consultar a unidade.')
      })
    return () => controller.abort()
  }, [client, allowed, selected])

  if (!allowed) return <AccessDenied />
  async function change(action: 'gerar' | 'regeneracao' | 'revogacao') {
    if (!selected || !responsible || pending) return
    setPending(true)
    setError('')
    try {
      const suffix = action === 'gerar' ? '' : `/${action}`
      await client.http.post(`/unidades/${encodeURIComponent(selected)}/chave${suffix}`, {
        responsavel_id: responsible,
      })
      const { data } = await client.http.get<Detail>(`/unidades/${encodeURIComponent(selected)}`)
      setDetail(data)
      setSuccess(action === 'revogacao' ? 'Chave revogada.' : 'Chave atualizada.')
      setConfirm(undefined)
    } catch {
      setError('Não foi possível alterar a chave. Confira o responsável e tente novamente.')
    } finally {
      setPending(false)
    }
  }

  return (
    <OperationsLayout
      activeKey="units"
      navigation={adminNavigation}
      workspace={{
        name: snapshot.identity?.condominio?.nome ?? 'Condomínio',
        profile: 'Administração',
        tools: <Link to="/app/administracao">Voltar</Link>,
      }}
    >
      <section className={styles.content}>
        <Heading level={1}>Chaves de acesso</Heading>
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
            label="Unidade"
            value={selected}
            options={units.map((unit) => ({
              value: unit.id,
              label: [unit.bloco, unit.andar, unit.identificacao].filter(Boolean).join(' / '),
            }))}
            onChange={(event) => {
              setSelected(event.target.value)
              setDetail(undefined)
              setSuccess('')
              setError('')
            }}
          />
          <div className={styles.pagination}>
            <Button
              variant="secondary"
              disabled={page === 1}
              onClick={() => {
                setPage(page - 1)
                setSelected('')
                setDetail(undefined)
              }}
            >
              Anterior
            </Button>
            <Text>Página {page}</Text>
            <Button
              variant="secondary"
              disabled={page * 20 >= total}
              onClick={() => {
                setPage(page + 1)
                setSelected('')
                setDetail(undefined)
              }}
            >
              Próxima
            </Button>
          </div>
          {detail && (
            <>
              <Text>
                {detail.chave
                  ? `Chave ativa: ${detail.chave.codigo}`
                  : 'Esta unidade não possui chave ativa.'}
              </Text>
              {detail.chave && (
                <div>
                  <Button
                    variant="secondary"
                    onClick={() =>
                      void navigator.clipboard
                        .writeText(detail.chave!.codigo)
                        .then(() => setSuccess('Chave copiada.'))
                        .catch(() => setError('Não foi possível copiar a chave.'))
                    }
                  >
                    Copiar chave
                  </Button>
                </div>
              )}
              <Select
                label="Responsável"
                value={responsible}
                options={responsibles.map((person) => ({ value: person.id, label: person.nome }))}
                onChange={(event) => setResponsible(event.target.value)}
              />
              {!responsibles.length && (
                <Notice tone="warning">Cadastre um responsável ativo para alterar chaves.</Notice>
              )}
              <div className={styles.actions}>
                {!detail.chave && (
                  <Button disabled={!responsible || pending} onClick={() => void change('gerar')}>
                    Gerar chave
                  </Button>
                )}
                {detail.chave && (
                  <>
                    <Button
                      variant="secondary"
                      disabled={!responsible || pending}
                      onClick={() => setConfirm('regeneracao')}
                    >
                      Regenerar
                    </Button>
                    <Button
                      variant="alert"
                      disabled={!responsible || pending}
                      onClick={() => setConfirm('revogacao')}
                    >
                      Revogar
                    </Button>
                  </>
                )}
              </div>
              {confirm && (
                <Notice tone="warning">
                  <Text>A chave atual deixará de funcionar. Confirma a alteração?</Text>
                  <div className={styles.actions}>
                    <Button
                      variant="secondary"
                      disabled={pending}
                      onClick={() => setConfirm(undefined)}
                    >
                      Voltar
                    </Button>
                    <Button loading={pending} onClick={() => void change(confirm)}>
                      Confirmar
                    </Button>
                  </div>
                </Notice>
              )}
            </>
          )}
        </Card>
      </section>
    </OperationsLayout>
  )
}
