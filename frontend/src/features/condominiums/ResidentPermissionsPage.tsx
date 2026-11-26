import { useEffect, useState } from 'react'
import axios from 'axios'
import { Button, Card, Heading, Modal, Notice, Select, Text } from '../../components'
import { useAuth } from '../auth/context'
import {
  desvinculacaoErrorMessage,
  desvinculacaoPath,
  desvinculacaoSuccessMessage,
} from './desvinculacao'
import { ResidentWorkspace } from '../resident/ResidentWorkspace'
import styles from '../resident/ResidentWorkspace.module.css'

type Resident = { id: string; nome: string; eu: boolean; permissoes: Record<string, boolean> }
const labels: Record<string, string> = {
  unidades: 'Unidades',
  visitantes: 'Visitantes',
  veiculos: 'Veículos',
  reservas: 'Reservas',
  encomendas: 'Encomendas',
  ocorrencias: 'Ocorrências',
  usuarios: 'Usuários',
}

export function ResidentPermissionsPage() {
  return (
    <ResidentWorkspace activeKey="overview">
      <Permissions />
    </ResidentWorkspace>
  )
}

function Permissions() {
  const { snapshot, client } = useAuth()
  const units = (snapshot.identity?.unidades ?? []).filter((unit) => unit.abas?.includes('usuarios'))
  const [unitId, setUnitId] = useState('')
  const unit = units.find((item) => item.id === unitId) ?? units[0]
  const [residents, setResidents] = useState<Resident[]>([])
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [busy, setBusy] = useState(false)
  const [revision, setRevision] = useState(0)
  const [target, setTarget] = useState<Resident | null>(null)

  useEffect(() => {
    if (!unit) return
    const controller = new AbortController()
    client.http
      .get<{ items: Resident[] }>(`/unidades/${encodeURIComponent(unit.id)}/moradores`, {
        params: { page: 1, page_size: 100 },
        signal: controller.signal,
      })
      .then(({ data }) => setResidents(data.items))
      .catch(() => {
        if (!controller.signal.aborted)
          setError('Não foi possível consultar os moradores. Verifique seu acesso à aba Usuários.')
      })
    return () => controller.abort()
  }, [client, unit, revision])

  async function unlink(resident: Resident) {
    if (!unit || busy) return
    setBusy(true)
    setError('')
    setSuccess('')
    try {
      // Morador: o corpo é sempre vazio (responsavel_id é só da Administração).
      const { data } = await client.http.post<{ chave_revogada: boolean }>(
        desvinculacaoPath(unit.id, resident.id),
        {},
      )
      setSuccess(desvinculacaoSuccessMessage(resident.nome, data.chave_revogada))
      setTarget(null)
      setRevision((value) => value + 1)
      await client.restore()
    } catch (failure) {
      const response = axios.isAxiosError(failure) ? failure.response : undefined
      setError(
        desvinculacaoErrorMessage({
          status: response?.status,
          reason: response?.data?.error?.reason,
        }),
      )
      setTarget(null)
    } finally {
      setBusy(false)
    }
  }

  async function save(resident: Resident) {
    if (!unit || busy) return
    setBusy(true)
    setError('')
    setSuccess('')
    try {
      await client.http.put(
        `/unidades/${encodeURIComponent(unit.id)}/moradores/${encodeURIComponent(resident.id)}/permissoes`,
        { abas: resident.permissoes },
      )
      setSuccess('Permissões atualizadas.')
      setRevision((value) => value + 1)
      await client.restore()
    } catch {
      setError(
        'Não foi possível salvar. A unidade deve manter ao menos um morador com acesso a Usuários.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className={styles.content}>
      <Heading level={1}>Permissões dos moradores</Heading>
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
      {!unit ? (
        <Notice tone="warning">Sua conta ainda não tem unidade vinculada.</Notice>
      ) : (
        <Card className={styles.content}>
          <Select
            label="Unidade"
            value={unit.id}
            options={units.map((item) => ({ value: item.id, label: item.identificacao }))}
            onChange={(event) => {
              setUnitId(event.target.value)
              setResidents([])
              setError('')
              setSuccess('')
            }}
          />
          {residents.map((resident) => (
            <article className={styles.listItem} key={resident.id}>
              <Heading level={2} size="sm">
                {resident.nome}
                {resident.eu ? ' (você)' : ''}
              </Heading>
              {Object.entries(labels).map(([key, label]) => (
                <label key={key}>
                  <input
                    type="checkbox"
                    checked={resident.permissoes[key] ?? false}
                    disabled={busy}
                    onChange={(event) =>
                      setResidents((items) =>
                        items.map((item) =>
                          item.id === resident.id
                            ? {
                                ...item,
                                permissoes: { ...item.permissoes, [key]: event.target.checked },
                              }
                            : item,
                        ),
                      )
                    }
                  />{' '}
                  {label}
                </label>
              ))}
              <div>
                <Button disabled={busy} onClick={() => void save(resident)}>
                  Salvar permissões
                </Button>{' '}
                {!resident.eu && (
                  <Button variant="alert" disabled={busy} onClick={() => setTarget(resident)}>
                    Desvincular
                  </Button>
                )}
              </div>
            </article>
          ))}
        </Card>
      )}
      <Modal
        isOpen={target !== null}
        onClose={() => !busy && setTarget(null)}
        title="Desvincular morador"
      >
        <Text>
          {target?.nome} perderá o acesso a {unit?.identificacao}. O histórico é preservado e a
          chave de acesso atual da unidade será revogada.
        </Text>
        <div>
          <Button variant="secondary" disabled={busy} onClick={() => setTarget(null)}>
            Cancelar
          </Button>{' '}
          <Button variant="alert" disabled={busy} onClick={() => target && void unlink(target)}>
            Confirmar desvinculação
          </Button>
        </div>
      </Modal>
    </section>
  )
}
