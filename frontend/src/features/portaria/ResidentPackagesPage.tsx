import { useEffect, useMemo, useState } from 'react'
import axios from 'axios'
import {
  Badge,
  Button,
  Card,
  Heading,
  Modal,
  Notice,
  RecordPhoto,
  Select,
  Table,
  Text,
} from '../../components'
import { useAuth } from '../auth/context'
import { ResidentWorkspace } from '../resident/ResidentWorkspace'
import { createEncomendasClient } from './encomendas-api'
import type { PackageRecord, PackageStatus } from './encomendas-api'
import styles from './PackagesWorkspacePage.module.css'

const labels: Record<PackageStatus, string> = {
  aguardando_retirada: 'Aguardando retirada',
  entregue_aguardando_confirmacao: 'Aguardando confirmação',
  retirada_confirmada: 'Retirada confirmada',
}

function variant(status: PackageStatus): 'primary' | 'warning' | 'success' {
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

function failureMessage(error: unknown) {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 404)
      return 'Esta encomenda não está mais disponível para sua conta.'
    if (error.response?.status === 409)
      return 'A situação mudou. Atualize a lista antes de tentar novamente.'
    if (error.response?.status === 403) return 'Seu acesso não permite confirmar esta encomenda.'
    if (error.response?.status === 429)
      return 'Muitas tentativas. Aguarde um pouco e tente novamente.'
  }
  return 'Não foi possível concluir a operação. Verifique a conexão e tente novamente.'
}

export function ResidentPackagesPage() {
  return (
    <ResidentWorkspace activeKey="packages">
      <ResidentPackages />
    </ResidentWorkspace>
  )
}

function ResidentPackages() {
  const { client, snapshot } = useAuth()
  const api = useMemo(() => createEncomendasClient(client.http), [client])
  const units = (snapshot.identity?.unidades ?? []).filter((unit) => unit.abas?.includes('encomendas'))
  const [unitId, setUnitId] = useState(() => units[0]?.id ?? '')
  const activeUnit = units.some((unit) => unit.id === unitId) ? unitId : (units[0]?.id ?? '')
  const [loadedUnit, setLoadedUnit] = useState('')
  const [items, setItems] = useState<PackageRecord[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [opened, setSelected] = useState<PackageRecord | null>(null)
  const selected = opened?.unidade.id === activeUnit ? opened : null
  const [photoRecord, setPhotoRecord] = useState<{ fileId: string; url: string } | null>(null)

  useEffect(() => {
    if (!activeUnit) return
    let current = true
    api
      .list({ unitId: activeUnit, page })
      .then((result) => {
        if (!current) return
        setItems(result.items)
        setTotal(result.total)
        setLoadError(null)
      })
      .catch((error: unknown) => {
        if (current) setLoadError(failureMessage(error))
      })
      .finally(() => {
        if (current) {
          setLoadedUnit(activeUnit)
          setLoading(false)
        }
      })
    return () => {
      current = false
    }
  }, [activeUnit, api, page, revision])

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

  function reload() {
    setLoading(true)
    setLoadError(null)
    setRevision((value) => value + 1)
  }

  async function confirm() {
    if (!selected || !selected.pode_confirmar || pending) return
    setPending(true)
    setActionError(null)
    setSuccess(null)
    try {
      const updated = await api.confirm(selected.id)
      setSelected(updated)
      setItems((records) => records.map((record) => (record.id === updated.id ? updated : record)))
      setSuccess('Retirada confirmada. Obrigado por atualizar o registro.')
      reload()
    } catch (error) {
      setActionError(failureMessage(error))
    } finally {
      setPending(false)
    }
  }

  const isLoading = loading || loadedUnit !== activeUnit
  const selectedPhotoUrl =
    selected && photoRecord?.fileId === selected.foto_arquivo_id ? photoRecord.url : null
  const rows = items.map((item) => [
    <div key="description">
      <Text size="sm">
        <strong>{item.descricao}</strong>
      </Text>
      <Text size="xs" tone="secondary">
        Recebida em {formatDate(item.recebimento.em)}
      </Text>
    </div>,
    <Text key="unit" size="sm">
      {item.unidade.identificacao}
    </Text>,
    <Badge key="status" variant={variant(item.status)} wrap>
      {labels[item.status]}
    </Badge>,
    <Button
      key="details"
      size="sm"
      variant="secondary"
      onClick={() => {
        setActionError(null)
        setSuccess(null)
        setSelected(item)
      }}
      aria-label={`Ver foto e detalhes de ${item.descricao}`}
    >
      Ver foto e detalhes
    </Button>,
  ])

  return (
    <>
      <section className={styles.content} aria-labelledby="resident-packages-title">
        <div>
          <Heading level={1} id="resident-packages-title">
            Minhas encomendas
          </Heading>
          <Text tone="secondary">
            Acompanhe os recebimentos vinculados às suas unidades e confirme a retirada quando você
            for o morador que recebeu.
          </Text>
        </div>
        {success && !selected && (
          <Notice tone="success" role="status">
            {success}
          </Notice>
        )}
        {!activeUnit ? (
          <Notice>Você ainda não tem uma unidade vinculada para consultar encomendas.</Notice>
        ) : (
          <Card className={styles.content}>
            <Select
              label="Unidade"
              value={activeUnit}
              options={units.map((unit) => ({ value: unit.id, label: unit.identificacao }))}
              onChange={(event) => {
                setUnitId(event.target.value)
                setPage(1)
                setSelected(null)
                setPhotoRecord(null)
                setSuccess(null)
                reload()
              }}
            />
            <div className={styles.header}>
              <div>
                <Heading level={2} size="md">
                  Encomendas vinculadas
                </Heading>
                <Text size="sm" tone="secondary">
                  {isLoading ? 'Atualizando registros…' : `${total} registro(s)`}
                </Text>
              </div>
              <Button variant="secondary" size="sm" onClick={reload} disabled={isLoading}>
                Atualizar lista
              </Button>
            </div>
            {isLoading ? (
              <Text role="status">Carregando encomendas…</Text>
            ) : loadError ? (
              <Notice tone="alert" role="alert">
                {loadError}
                <div className={styles.retry}>
                  <Button variant="secondary" size="sm" onClick={reload}>
                    Tentar novamente
                  </Button>
                </div>
              </Notice>
            ) : (
              <>
                <Table
                  caption="Encomendas da unidade selecionada"
                  headers={['Encomenda e recebimento', 'Unidade', 'Situação', 'Ação']}
                  rows={rows}
                  emptyMessage="Nenhuma encomenda nesta unidade por enquanto."
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
        )}
        <Notice>
          Apenas o morador identificado no registro da entrega pode confirmar a retirada. A portaria
          não confirma em nome do morador.
        </Notice>
      </section>

      <Modal
        isOpen={!!selected}
        onClose={() => {
          if (!pending) setSelected(null)
        }}
        title="Detalhes da encomenda"
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
            </div>
            <Badge variant={variant(selected.status)} wrap>
              {labels[selected.status]}
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
                Na portaria, por {selected.recebimento.funcionario_nome}
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
            {selected.status === 'aguardando_retirada' && (
              <Notice>
                A encomenda está disponível para retirada na portaria. Após a entrega física, o
                funcionário registrará quem recebeu.
              </Notice>
            )}
            {selected.status === 'entregue_aguardando_confirmacao' &&
              (selected.pode_confirmar ? (
                <Notice tone="warning">
                  Você foi identificado como a pessoa que recebeu a encomenda. Confirme depois de
                  verificar que ela está com você.
                </Notice>
              ) : (
                <Notice tone="warning">
                  A entrega está aguardando confirmação do morador que recebeu. Esta confirmação não
                  está disponível para sua conta.
                </Notice>
              ))}
            {actionError && (
              <Notice tone="alert" role="alert">
                {actionError}
              </Notice>
            )}
            {success && (
              <Notice tone="success" role="status">
                {success}
              </Notice>
            )}
            {selected.pode_confirmar && (
              <div className={styles.actions}>
                <Button variant="secondary" onClick={() => setSelected(null)} disabled={pending}>
                  Fechar
                </Button>
                <Button
                  onClick={() => {
                    void confirm()
                  }}
                  loading={pending}
                >
                  Confirmar que recebi
                </Button>
              </div>
            )}
            {!selected.pode_confirmar && (
              <div className={styles.actions}>
                <Button variant="secondary" onClick={() => setSelected(null)}>
                  Fechar detalhes
                </Button>
              </div>
            )}
          </div>
        )}
      </Modal>
    </>
  )
}
