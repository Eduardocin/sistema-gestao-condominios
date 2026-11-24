import { useEffect, useState } from 'react'
import type { ComponentType, FormEvent } from 'react'
import {
  Button,
  Card,
  CheckField,
  Heading,
  Input,
  Modal,
  Notice,
  Select,
  Text,
} from '../../components'
import type { ResidentOption } from './encomendas-api'
import type { Canal, createVisitantesClient, Pagina, Veiculo } from './visitantes-api'
import styles from './PackagesWorkspacePage.module.css'

type Opcao = { value: string; label: string }
interface ApoioPortaria {
  api: ReturnType<typeof createVisitantesClient>
  unidades: Opcao[]
  mensagem: (error: unknown) => string
}

export function CadastroAvulso(
  props: ApoioPortaria & { funcionarios: Opcao[]; onEntrada: () => void },
) {
  const [aberto, setAberto] = useState(false)
  const [salvando, setSalvando] = useState(false)
  return (
    <div className={styles.actions}>
      <Button variant="secondary" onClick={() => setAberto(true)}>
        Registrar visitante avulso
      </Button>
      <Modal
        isOpen={aberto}
        onClose={() => !salvando && setAberto(false)}
        title="Registrar visitante avulso"
      >
        {aberto && (
          <FormularioAvulso
            {...props}
            salvando={salvando}
            onSalvando={setSalvando}
            onEntrada={() => {
              setAberto(false)
              props.onEntrada()
            }}
          />
        )}
      </Modal>
    </div>
  )
}

function FormularioAvulso({
  api,
  unidades,
  funcionarios,
  mensagem,
  onEntrada,
  salvando,
  onSalvando,
}: ApoioPortaria & {
  funcionarios: Opcao[]
  onEntrada: () => void
  salvando: boolean
  onSalvando: (valor: boolean) => void
}) {
  const [unidade, setUnidade] = useState('')
  const [nome, setNome] = useState('')
  const [cpf, setCpf] = useState('')
  const [funcionario, setFuncionario] = useState('')
  const [morador, setMorador] = useState('')
  const [canal, setCanal] = useState<Canal>('interfone')
  const [autorizado, setAutorizado] = useState(false)
  const [moradores, setMoradores] = useState<ResidentOption[]>([])
  const [carregandoMoradores, setCarregandoMoradores] = useState(false)
  const [erroMoradores, setErroMoradores] = useState('')
  const [recarregar, setRecarregar] = useState(0)
  const [erro, setErro] = useState('')

  useEffect(() => {
    if (!unidade) return
    let ativo = true
    api
      .residents(unidade)
      .then(
        (items) => {
          if (ativo) setMoradores(items)
        },
        (error: unknown) => {
          if (ativo) setErroMoradores(mensagem(error))
        },
      )
      .finally(() => {
        if (ativo) setCarregandoMoradores(false)
      })
    return () => {
      ativo = false
    }
  }, [api, mensagem, unidade, recarregar])

  async function enviar(event: FormEvent) {
    event.preventDefault()
    if (salvando || !autorizado || !morador) return
    setErro('')
    onSalvando(true)
    try {
      await api.registrarAvulso({
        unidade_id: unidade,
        nome: nome.trim(),
        cpf: cpf.replace(/\D/g, ''),
        funcionario_id: funcionario,
        contato: { morador_id: morador, canal, resposta: 'autorizou' },
      })
      onEntrada()
    } catch (error) {
      setErro(mensagem(error))
    } finally {
      onSalvando(false)
    }
  }

  return (
    <form className={styles.form} onSubmit={(event) => void enviar(event)}>
      <Select
        label="Unidade de destino"
        required
        value={unidade}
        options={unidades}
        disabled={salvando}
        onChange={(event) => {
          setUnidade(event.target.value)
          setMorador('')
          setMoradores([])
          setAutorizado(false)
          setErroMoradores('')
          setCarregandoMoradores(true)
        }}
      />
      <Input
        label="Nome do visitante avulso"
        required
        maxLength={120}
        value={nome}
        disabled={salvando}
        onChange={(event) => {
          setNome(event.target.value)
          setAutorizado(false)
        }}
      />
      <Input
        label="CPF do visitante avulso"
        required
        minLength={11}
        maxLength={14}
        inputMode="numeric"
        autoComplete="off"
        value={cpf}
        disabled={salvando}
        onChange={(event) => {
          setCpf(event.target.value.replace(/[^0-9.\- ]/g, ''))
          setAutorizado(false)
        }}
      />
      <Select
        label="Funcionário responsável"
        required
        value={funcionario}
        options={funcionarios}
        disabled={salvando}
        onChange={(event) => {
          setFuncionario(event.target.value)
          setAutorizado(false)
        }}
      />
      <Select
        label="Morador que autorizou"
        required
        value={morador}
        options={moradores.map((item) => ({ value: item.id, label: item.nome }))}
        disabled={salvando || !unidade || carregandoMoradores}
        onChange={(event) => {
          setMorador(event.target.value)
          setAutorizado(false)
        }}
      />
      {carregandoMoradores && <Text role="status">Carregando moradores…</Text>}
      {unidade && !carregandoMoradores && !erroMoradores && moradores.length === 0 && (
        <Notice>Nenhum morador ativo foi encontrado nesta unidade.</Notice>
      )}
      {erroMoradores && (
        <Notice tone="alert" role="alert">
          {erroMoradores}
          <div className={styles.retry}>
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setErroMoradores('')
                setCarregandoMoradores(true)
                setRecarregar((n) => n + 1)
              }}
            >
              Recarregar moradores
            </Button>
          </div>
        </Notice>
      )}
      <Select
        label="Canal de contato"
        value={canal}
        disabled={salvando}
        options={[
          { value: 'interfone', label: 'Interfone' },
          { value: 'telefone', label: 'Telefone' },
        ]}
        onChange={(event) => {
          setCanal(event.target.value as Canal)
          setAutorizado(false)
        }}
      />
      <CheckField
        checked={autorizado}
        disabled={salvando || !morador}
        onChange={(event) => setAutorizado(event.target.checked)}
      >
        Conferi o documento e recebi autorização do morador por este canal.
      </CheckField>
      {erro && (
        <Notice tone="alert" role="alert">
          {erro}
        </Notice>
      )}
      <div className={styles.actions}>
        <Button type="submit" loading={salvando} disabled={!autorizado}>
          Registrar entrada avulsa
        </Button>
      </div>
    </form>
  )
}

export function ConsultaVeiculos({
  api,
  unidades,
  mensagem,
  paginacao: Paginacao,
}: ApoioPortaria & {
  paginacao: ComponentType<{ page: number; total: number; onPage: (page: number) => void }>
}) {
  const [unidade, setUnidade] = useState('')
  const [placa, setPlaca] = useState('')
  const [filtro, setFiltro] = useState({ unidade: '', placa: '' })
  const [resultado, setResultado] = useState<Pagina<Veiculo> | null>(null)
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState('')

  async function consultar(filtros: typeof filtro, page: number) {
    setCarregando(true)
    setResultado(null)
    setErro('')
    try {
      setResultado(await api.veiculos(filtros.unidade, filtros.placa, page))
    } catch (error) {
      setErro(mensagem(error))
    } finally {
      setCarregando(false)
    }
  }

  return (
    <Card className={styles.content}>
      <Heading level={2}>Consultar veículos</Heading>
      <form
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault()
          if (carregando) return
          const filtros = { unidade, placa }
          setFiltro(filtros)
          void consultar(filtros, 1)
        }}
      >
        <Input
          label="Placa do veículo"
          value={placa}
          maxLength={20}
          autoComplete="off"
          disabled={carregando}
          onChange={(event) => setPlaca(event.target.value)}
        />
        <Select
          label="Unidade do veículo"
          value={unidade || 'todas'}
          options={[{ value: 'todas', label: 'Todas as unidades' }, ...unidades]}
          disabled={carregando}
          onChange={(event) => setUnidade(event.target.value === 'todas' ? '' : event.target.value)}
        />
        <div className={styles.actions}>
          <Button type="submit" loading={carregando}>
            Buscar veículos
          </Button>
        </div>
      </form>
      {erro && (
        <Notice tone="alert" role="alert">
          {erro}
        </Notice>
      )}
      {resultado?.total === 0 && <Notice>Nenhum veículo ativo foi encontrado.</Notice>}
      {resultado && resultado.items.length > 0 && (
        <ul className={styles.results} aria-label="Veículos encontrados">
          {resultado.items.map((item) => (
            <li key={item.id} className={styles.history}>
              <Heading level={3}>{item.placa}</Heading>
              <Text>
                {item.marca} {item.modelo} · {item.cor} · {item.unidade.nome}
              </Text>
            </li>
          ))}
        </ul>
      )}
      {resultado && (
        <Paginacao
          page={resultado.page}
          total={resultado.total}
          onPage={(page) => void consultar(filtro, page)}
        />
      )}
    </Card>
  )
}
