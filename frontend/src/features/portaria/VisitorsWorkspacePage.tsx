import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import axios from 'axios'
import { Link } from 'react-router'
import {
  Button,
  Card,
  CheckField,
  Heading,
  Input,
  Modal,
  Notice,
  OperationsLayout,
  Select,
  Text,
} from '../../components'
import { useAuth } from '../auth/context'
import { AccessDenied } from '../auth/SessionPages'
import { CadastroAvulso, ConsultaVeiculos } from './PortariaComplementos'
import type { EmployeeOption, ResidentOption, UnitOption } from './encomendas-api'
import { createVisitantesClient } from './visitantes-api'
import type {
  Autorizacao,
  Busca,
  Canal,
  Contato,
  Pagina,
  RespostaContato,
  Visita,
  Visitante,
} from './visitantes-api'
import styles from './PackagesWorkspacePage.module.css'
import { portariaNavigation } from '../auth/area-navigation'
const canalNome = { interfone: 'Interfone', telefone: 'Telefone' }
const respostaNome = { negou: 'Entrada negada', sem_resposta: 'Sem resposta' }
const vazio: Busca = { unidade: '', termo: '', por: 'nome' }

function horario(valor: string) {
  return new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'short',
    timeZone: 'America/Sao_Paulo',
  }).format(new Date(valor))
}

function dataPrevista(valor: string) {
  return valor.split('-').reverse().join('/')
}

function mensagem(error: unknown) {
  if (axios.isAxiosError<{ error?: { message?: string } }>(error)) {
    return error.response?.data?.error?.message ?? 'Não foi possível conectar. Tente novamente.'
  }
  return 'Não foi possível concluir a operação. Tente novamente.'
}

function Paginacao({
  page,
  total,
  onPage,
}: {
  page: number
  total: number
  onPage: (page: number) => void
}) {
  const paginas = Math.max(1, Math.ceil(total / 20))
  if (paginas === 1 && page === 1) return null
  return (
    <div className={styles.pagination}>
      <Text size="sm">
        Página {page} de {paginas}
      </Text>
      <div>
        <Button variant="secondary" disabled={page === 1} onClick={() => onPage(page - 1)}>
          Anterior
        </Button>
        <Button variant="secondary" disabled={page >= paginas} onClick={() => onPage(page + 1)}>
          Próxima
        </Button>
      </div>
    </div>
  )
}

export function VisitorsWorkspacePage() {
  const { snapshot } = useAuth()
  const condominio = snapshot.identity?.condominio
  if (
    !condominio ||
    condominio.perfil !== 'funcionario' ||
    condominio.status !== 'ativo' ||
    snapshot.identity?.administrador_plataforma
  )
    return <AccessDenied />
  return <VisitorsWorkspace key={condominio.id} name={condominio.nome} />
}

function VisitorsWorkspace({ name }: { name: string }) {
  const { client, snapshot } = useAuth()
  const api = useMemo(() => createVisitantesClient(client.http), [client])
  const [busca, setBusca] = useState<Busca>(vazio)
  const [filtro, setFiltro] = useState<Busca | null>(null)
  const [buscaPage, setBuscaPage] = useState(1)
  const [resultados, setResultados] = useState<Pagina<Visitante> | null>(null)
  const [buscando, setBuscando] = useState(false)
  const [buscaErro, setBuscaErro] = useState('')
  const [selecionado, setSelecionado] = useState<Visitante | null>(null)
  const [autorizacao, setAutorizacao] = useState<Autorizacao | null>(null)
  const [moradores, setMoradores] = useState<ResidentOption[]>([])
  const [autorizando, setAutorizando] = useState(false)
  const [autorizacaoErro, setAutorizacaoErro] = useState('')
  const [autorizacaoRev, setAutorizacaoRev] = useState(0)
  const [unidades, setUnidades] = useState<UnitOption[]>([])
  const [funcionarios, setFuncionarios] = useState<EmployeeOption[]>([])
  const [opcoesErro, setOpcoesErro] = useState('')
  const [opcoesRev, setOpcoesRev] = useState(0)
  const [carregandoOpcoes, setCarregandoOpcoes] = useState(true)
  const [funcionario, setFuncionario] = useState('')
  const [morador, setMorador] = useState('')
  const [canal, setCanal] = useState<Canal>('interfone')
  const [resposta, setResposta] = useState<RespostaContato | ''>('')
  const [identidadeConferida, setIdentidadeConferida] = useState(false)
  const [visao, setVisao] = useState<'em_andamento' | 'encerrada' | 'contatos'>('em_andamento')
  const [visitaBusca, setVisitaBusca] = useState('')
  const [visitaFiltro, setVisitaFiltro] = useState('')
  const [historicoPage, setHistoricoPage] = useState(1)
  const [historico, setHistorico] = useState<Pagina<Visita | Contato> | null>(null)
  const [historicoRev, setHistoricoRev] = useState(0)
  const [carregandoHistorico, setCarregandoHistorico] = useState(true)
  const [historicoErro, setHistoricoErro] = useState('')
  const [detalhe, setDetalhe] = useState<Visita | null>(null)
  const [funcionarioSaida, setFuncionarioSaida] = useState('')
  const [pendente, setPendente] = useState(false)
  const [acaoErro, setAcaoErro] = useState('')
  const [sucesso, setSucesso] = useState('')

  useEffect(() => {
    let ativo = true
    Promise.all([api.units(), api.employees()])
      .then(([units, staff]) => {
        if (ativo) {
          setUnidades(units)
          setFuncionarios(staff)
          setOpcoesErro('')
        }
      })
      .catch((error: unknown) => {
        if (ativo) setOpcoesErro(mensagem(error))
      })
      .finally(() => {
        if (ativo) setCarregandoOpcoes(false)
      })
    return () => {
      ativo = false
    }
  }, [api, opcoesRev])

  useEffect(() => {
    if (!filtro) return
    let ativo = true
    api
      .buscar(filtro, buscaPage)
      .then((data) => {
        if (ativo) setResultados(data)
      })
      .catch((error: unknown) => {
        if (ativo) setBuscaErro(mensagem(error))
      })
      .finally(() => {
        if (ativo) setBuscando(false)
      })
    return () => {
      ativo = false
    }
  }, [api, filtro, buscaPage])

  useEffect(() => {
    if (!selecionado) return
    let ativo = true
    api
      .autorizacao(selecionado)
      .then(async (data) => {
        if (!ativo) return
        setAutorizacao(data)
        if (!data) {
          const opcoes = await api.residents(selecionado.unidade.id)
          if (ativo) setMoradores(opcoes)
        }
      })
      .catch((error: unknown) => {
        if (ativo) setAutorizacaoErro(mensagem(error))
      })
      .finally(() => {
        if (ativo) setAutorizando(false)
      })
    return () => {
      ativo = false
    }
  }, [api, selecionado, autorizacaoRev])

  useEffect(() => {
    let ativo = true
    const req =
      visao === 'contatos'
        ? api.contatos(historicoPage)
        : api.visitas(visao, historicoPage, visitaFiltro)
    req
      .then((data) => {
        if (ativo) setHistorico(data)
      })
      .catch((error: unknown) => {
        if (ativo) setHistoricoErro(mensagem(error))
      })
      .finally(() => {
        if (ativo) setCarregandoHistorico(false)
      })
    return () => {
      ativo = false
    }
  }, [api, historicoPage, historicoRev, visao, visitaFiltro])

  function prepararBusca() {
    setResultados(null)
    setBuscaErro('')
    setBuscando(true)
  }

  function buscar(event: FormEvent) {
    event.preventDefault()
    const documento = /^\d{11}$/.test(busca.termo.replace(/[.\-\s]/g, ''))
    if (busca.por === 'nome' && documento) {
      const proxima: Busca = { ...busca, por: 'cpf' }
      setBusca(proxima)
      if (!proxima.unidade) {
        setBuscaErro('Escolha a unidade para buscar pelo CPF.')
        return
      }
      prepararBusca()
      setBuscaPage(1)
      setFiltro(proxima)
      return
    }
    if (busca.por === 'nome' && !busca.unidade && !busca.termo.trim()) {
      setBuscaErro('Informe um nome ou selecione uma unidade.')
      return
    }
    if (busca.por === 'cpf' && (!busca.unidade || !documento)) {
      setBuscaErro('Escolha uma unidade e informe os 11 dígitos do CPF.')
      return
    }
    prepararBusca()
    setBuscaPage(1)
    setFiltro({ ...busca })
  }

  function revalidarAutorizacao() {
    setAutorizando(true)
    setAutorizacao(null)
    setAutorizacaoErro('')
    setMoradores([])
    setMorador('')
    setResposta('')
    setCanal('interfone')
    setAutorizacaoRev((n) => n + 1)
  }

  function escolher(visitante: Visitante) {
    setIdentidadeConferida(false)
    setFuncionario('')
    setAcaoErro('')
    setSucesso('')
    revalidarAutorizacao()
    setSelecionado(visitante)
  }

  function carregarHistorico() {
    setHistoricoErro('')
    setCarregandoHistorico(true)
    setHistoricoRev((n) => n + 1)
  }

  async function entrada(event: FormEvent) {
    event.preventDefault()
    if (
      !selecionado ||
      !identidadeConferida ||
      !funcionario ||
      pendente ||
      autorizando ||
      autorizacaoErro ||
      (!autorizacao && (!morador || !resposta))
    )
      return
    setPendente(true)
    setAcaoErro('')
    const destino = {
      visitante_id: selecionado.id,
      unidade_id: selecionado.unidade.id,
      funcionario_id: funcionario,
    }
    try {
      if (autorizacao) {
        await api.entrar({ ...destino, autorizacao_id: autorizacao.id })
        setSucesso('Entrada registrada.')
      } else if (resposta === 'autorizou') {
        await api.entrar({ ...destino, contato: { morador_id: morador, canal, resposta } })
        setSucesso('Entrada registrada.')
      } else if (resposta) {
        await api.registrarContato({ ...destino, morador_id: morador, canal, resposta })
        setSucesso('Contato registrado. Entrada não liberada.')
      }
      setSelecionado(null)
      carregarHistorico()
    } catch (error) {
      setAcaoErro(mensagem(error))
    } finally {
      setPendente(false)
    }
  }

  async function saida(event: FormEvent) {
    event.preventDefault()
    if (!detalhe || !funcionarioSaida || pendente) return
    setPendente(true)
    setAcaoErro('')
    try {
      await api.sair(detalhe.id, funcionarioSaida)
      setDetalhe(null)
      setSucesso('Saída registrada.')
      carregarHistorico()
    } catch (error) {
      setAcaoErro(mensagem(error))
    } finally {
      setPendente(false)
    }
  }

  const funcionarioOptions = funcionarios.map((item) => ({ value: item.id, label: item.nome }))
  const unidadeOptions = unidades.map((item) => ({
    value: item.id,
    label: [item.bloco, item.andar, item.identificacao].filter(Boolean).join(' / '),
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
  return (
    <OperationsLayout
      activeKey="visitors"
      navigation={portariaNavigation}
      workspace={{ name, profile: 'Portaria', tools }}
    >
      <section className={styles.content} aria-labelledby="visitantes-titulo">
        <Heading level={1} id="visitantes-titulo">
          Visitantes
        </Heading>
        {sucesso && (
          <Notice tone="success" role="status">
            {sucesso}
          </Notice>
        )}
        {opcoesErro && (
          <Notice tone="alert" role="alert">
            {opcoesErro}
            <div className={styles.retry}>
              <Button
                variant="secondary"
                onClick={() => {
                  setOpcoesErro('')
                  setCarregandoOpcoes(true)
                  setOpcoesRev((n) => n + 1)
                }}
              >
                Recarregar opções
              </Button>
            </div>
          </Notice>
        )}
        <Card className={styles.content}>
          <Heading level={2}>Registrar entrada</Heading>
          <form className={styles.form} onSubmit={buscar}>
            <Select
              label="Buscar por"
              value={busca.por}
              options={[
                { value: 'nome', label: 'Nome' },
                { value: 'cpf', label: 'CPF' },
              ]}
              onChange={(event) => {
                setBusca({ ...busca, termo: '', por: event.target.value as Busca['por'] })
                setBuscaErro('')
              }}
            />
            <Select
              label={busca.por === 'cpf' ? 'Unidade' : 'Unidade (opcional)'}
              value={busca.unidade || (busca.por === 'nome' ? 'todas' : '')}
              options={
                busca.por === 'nome'
                  ? [{ value: 'todas', label: 'Todas as unidades' }, ...unidadeOptions]
                  : unidadeOptions
              }
              disabled={carregandoOpcoes}
              required={busca.por === 'cpf'}
              onChange={(event) =>
                setBusca({
                  ...busca,
                  unidade: event.target.value === 'todas' ? '' : event.target.value,
                })
              }
            />
            <Input
              label={busca.por === 'cpf' ? 'CPF do visitante' : 'Nome do visitante'}
              value={busca.termo}
              inputMode={busca.por === 'cpf' ? 'numeric' : undefined}
              autoComplete="off"
              required={busca.por === 'cpf' || !busca.unidade}
              maxLength={busca.por === 'cpf' ? 14 : 120}
              onChange={(event) => setBusca({ ...busca, termo: event.target.value })}
            />
            <div className={styles.actions}>
              <Button type="submit" loading={buscando}>
                Buscar visitante
              </Button>
            </div>
          </form>
          {buscaErro && (
            <Notice tone="alert" role="alert">
              {buscaErro}
            </Notice>
          )}
          {resultados && resultados.items.length === 0 && (
            <Notice>
              Nenhum visitante cadastrado foi encontrado. Confira a unidade e os dados informados.
            </Notice>
          )}
          {resultados?.items.map((item) => {
            return (
              <div key={item.id} className={styles.history}>
                <Text>
                  <strong>
                    {item.nome} · {item.unidade.nome}
                  </strong>
                </Text>
                <Text size="sm">
                  {dataPrevista(item.entrada_prevista)} a {dataPrevista(item.saida_prevista)}
                  {item.cancelado && ' · Cadastro cancelado'}
                </Text>
                {item.ambigua ? (
                  <Notice tone="warning">
                    {filtro?.por === 'cpf'
                      ? 'O cadastro continua ambíguo. Peça ao morador para revisar os dados.'
                      : 'Cadastros iguais. Busque pelo CPF ou peça ao morador para revisar o cadastro.'}
                  </Notice>
                ) : (
                  <div>
                    <Button variant="secondary" onClick={() => escolher(item)}>
                      Selecionar visitante
                    </Button>
                  </div>
                )}
              </div>
            )
          })}
          {resultados && (
            <Paginacao
              page={buscaPage}
              total={resultados.total}
              onPage={(page) => {
                prepararBusca()
                setBuscaPage(page)
              }}
            />
          )}
        </Card>
        <CadastroAvulso
          api={api}
          unidades={unidadeOptions}
          funcionarios={funcionarioOptions}
          mensagem={mensagem}
          onEntrada={() => {
            setSucesso('Entrada de visitante avulso registrada.')
            setVisao('em_andamento')
            setHistoricoPage(1)
            carregarHistorico()
          }}
        />
        <ConsultaVeiculos
          api={api}
          unidades={unidadeOptions}
          mensagem={mensagem}
          paginacao={Paginacao}
        />
        <Card className={styles.content}>
          <Heading level={2}>
            {visao === 'em_andamento'
              ? 'Visitantes no prédio'
              : visao === 'encerrada'
                ? 'Visitas encerradas'
                : 'Contatos sem entrada'}
          </Heading>
          <div className={styles.tools}>
            {(
              [
                ['em_andamento', 'No prédio'],
                ['encerrada', 'Histórico'],
                ['contatos', 'Contatos'],
              ] as const
            ).map(([valor, label]) => (
              <Button
                key={valor}
                variant={visao === valor ? 'primary' : 'secondary'}
                aria-pressed={visao === valor}
                onClick={() => {
                  // Clicar na aba já aberta também recarrega a lista.
                  carregarHistorico()
                  if (visao !== valor) {
                    setHistorico(null)
                    setHistoricoPage(1)
                    setVisao(valor)
                  }
                }}
              >
                {label}
              </Button>
            ))}
          </div>
          {visao !== 'contatos' && (
            <form
              className={styles.tools}
              onSubmit={(event) => {
                event.preventDefault()
                carregarHistorico()
                setHistoricoPage(1)
                setVisitaFiltro(visitaBusca.trim())
              }}
            >
              <Input
                label="Filtrar visitas"
                value={visitaBusca}
                onChange={(event) => setVisitaBusca(event.target.value)}
                placeholder="Visitante ou unidade"
              />
              <Button type="submit" variant="secondary" disabled={carregandoHistorico}>
                Filtrar
              </Button>
            </form>
          )}
          {carregandoHistorico && <Text role="status">Carregando registros…</Text>}
          {historicoErro && (
            <Notice tone="alert" role="alert">
              {historicoErro}
            </Notice>
          )}
          {!carregandoHistorico && !historicoErro && historico?.items.length === 0 && (
            <Notice>Nenhum registro nesta lista.</Notice>
          )}
          {!carregandoHistorico &&
            historico?.items.map((item) => (
              <div key={item.id} className={styles.history}>
                <Text>
                  <strong>
                    {item.visitante.nome} · {item.unidade.nome}
                  </strong>
                </Text>
                {'entrada' in item ? (
                  <>
                    <Text size="sm">
                      Entrada {horario(item.entrada.em)} · {item.entrada.funcionario.nome}
                    </Text>
                    {item.saida && (
                      <Text size="sm">
                        Saída {horario(item.saida.em)} · {item.saida.funcionario.nome}
                      </Text>
                    )}
                    <div>
                      <Button
                        variant="secondary"
                        onClick={() => {
                          setDetalhe(item)
                          setFuncionarioSaida('')
                          setAcaoErro('')
                          setSucesso('')
                        }}
                      >
                        {item.saida ? 'Ver detalhes' : 'Registrar saída'}
                      </Button>
                    </div>
                  </>
                ) : (
                  <Text size="sm">
                    {respostaNome[item.resposta]} · {canalNome[item.canal]} ·{' '}
                    {horario(item.registrado_em)} · {item.funcionario.nome}
                  </Text>
                )}
              </div>
            ))}
          {historico && (
            <Paginacao
              page={historicoPage}
              total={historico.total}
              onPage={(page) => {
                carregarHistorico()
                setHistoricoPage(page)
              }}
            />
          )}
        </Card>
      </section>
      <Modal
        isOpen={selecionado !== null}
        onClose={() => {
          if (!pendente) setSelecionado(null)
        }}
        title="Registrar entrada"
      >
        {selecionado && (
          <form className={styles.form} onSubmit={(event) => void entrada(event)}>
            <Text>
              {selecionado.nome} · {selecionado.unidade.nome}
            </Text>
            <CheckField
              checked={identidadeConferida}
              onChange={(event) => setIdentidadeConferida(event.target.checked)}
            >
              Conferi a identidade e a unidade de destino.
            </CheckField>
            <Select
              label="Funcionário responsável"
              value={funcionario}
              required
              options={funcionarioOptions}
              disabled={carregandoOpcoes || pendente}
              onChange={(event) => setFuncionario(event.target.value)}
            />
            {carregandoOpcoes && <Text role="status">Carregando funcionários…</Text>}
            {!carregandoOpcoes && !opcoesErro && funcionarios.length === 0 && (
              <Notice>Nenhum funcionário ativo foi encontrado.</Notice>
            )}
            {autorizando && <Text role="status">Consultando autorização…</Text>}
            {autorizacaoErro && (
              <Notice tone="alert" role="alert">
                {autorizacaoErro}
              </Notice>
            )}
            {!autorizando && (
              <div>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={pendente}
                  onClick={revalidarAutorizacao}
                >
                  Consultar autorização novamente
                </Button>
              </div>
            )}
            {autorizacao && !autorizando && (
              <Notice tone="success">
                Autorização prévia vigente · {autorizacao.autorizado_por.nome}
              </Notice>
            )}
            {!autorizacao && !autorizando && !autorizacaoErro && (
              <>
                <Notice tone="warning">
                  Sem autorização prévia vigente. Consulte o morador por interfone ou telefone.
                </Notice>
                <Select
                  label="Morador consultado"
                  value={morador}
                  required
                  options={moradores.map((item) => ({ value: item.id, label: item.nome }))}
                  disabled={pendente}
                  onChange={(event) => {
                    setMorador(event.target.value)
                    setResposta('')
                  }}
                />
                <Select
                  label="Canal"
                  value={canal}
                  options={[
                    { value: 'interfone', label: 'Interfone' },
                    { value: 'telefone', label: 'Telefone' },
                  ]}
                  disabled={pendente}
                  onChange={(event) => {
                    setCanal(event.target.value as Canal)
                    setResposta('')
                  }}
                />
                <Select
                  label="Resposta"
                  value={resposta}
                  required
                  options={[
                    { value: 'autorizou', label: 'Autorizou' },
                    { value: 'negou', label: 'Negou' },
                    { value: 'sem_resposta', label: 'Sem resposta' },
                  ]}
                  disabled={pendente}
                  onChange={(event) => setResposta(event.target.value as RespostaContato | '')}
                />
              </>
            )}
            {acaoErro && (
              <Notice tone="alert" role="alert">
                {acaoErro}
              </Notice>
            )}
            <div className={styles.actions}>
              <Button
                type="submit"
                loading={pendente}
                disabled={
                  autorizando ||
                  carregandoOpcoes ||
                  !!opcoesErro ||
                  !!autorizacaoErro ||
                  !identidadeConferida ||
                  !funcionario ||
                  (!autorizacao && (!morador || !resposta))
                }
              >
                {resposta === 'negou' || resposta === 'sem_resposta'
                  ? 'Registrar contato sem entrada'
                  : 'Confirmar entrada'}
              </Button>
            </div>
          </form>
        )}
      </Modal>
      <Modal
        isOpen={detalhe !== null}
        onClose={() => {
          if (!pendente) setDetalhe(null)
        }}
        title={detalhe?.saida ? 'Detalhes da visita' : 'Registrar saída'}
      >
        {detalhe && (
          <form className={styles.form} onSubmit={(event) => void saida(event)}>
            <Text>
              {detalhe.visitante.nome} · {detalhe.unidade.nome}
            </Text>
            <Text>
              Entrada {horario(detalhe.entrada.em)} · {detalhe.entrada.funcionario.nome}
            </Text>
            {detalhe.autorizacao && (
              <Text>Autorização prévia de {detalhe.autorizacao.autorizado_por.nome}.</Text>
            )}
            {detalhe.contato && (
              <Text>Entrada autorizada por {canalNome[detalhe.contato.canal].toLowerCase()}.</Text>
            )}
            {detalhe.saida ? (
              <Text>
                Saída {horario(detalhe.saida.em)} · {detalhe.saida.funcionario.nome}
              </Text>
            ) : (
              <>
                <Select
                  label="Funcionário responsável"
                  value={funcionarioSaida}
                  required
                  options={funcionarioOptions}
                  disabled={pendente || carregandoOpcoes}
                  onChange={(event) => setFuncionarioSaida(event.target.value)}
                />
                {acaoErro && (
                  <Notice tone="alert" role="alert">
                    {acaoErro}
                  </Notice>
                )}
                <div className={styles.actions}>
                  <Button
                    type="submit"
                    disabled={!funcionarioSaida || carregandoOpcoes || !!opcoesErro}
                    loading={pendente}
                  >
                    Confirmar saída
                  </Button>
                </div>
              </>
            )}
          </form>
        )}
      </Modal>
    </OperationsLayout>
  )
}
