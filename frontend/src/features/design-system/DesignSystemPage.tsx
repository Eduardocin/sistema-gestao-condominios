import { useState } from 'react'
import type { ReactNode } from 'react'
import {
  Badge,
  Button,
  ButtonLink,
  Calendar,
  Card,
  CheckField,
  CommunityVisual,
  FeatureCard,
  Heading,
  Input,
  Modal,
  MetricCard,
  Notice,
  Page,
  PublicCallToAction,
  PublicFooter,
  PublicHeader,
  RecordPhoto,
  Select,
  Table,
  Text,
  TimeGrid,
  Toast,
  Upload,
} from '../../components'
import type { SlotStatus, TimeSlotData, ToastVariant } from '../../components'
import styles from './DesignSystemPage.module.css'

const unitOptions = [
  { value: '101', label: 'Apartamento 101' },
  { value: '102', label: 'Apartamento 102' },
  { value: '201', label: 'Apartamento 201' },
]

const colorTokens = [
  { name: '--color-primary', label: 'Azul Safira' },
  { name: '--color-primary-soft', label: 'Azul suave' },
  { name: '--color-success-strong', label: 'Verde' },
  { name: '--color-success-soft', label: 'Verde suave' },
  { name: '--color-alert-strong', label: 'Vermelho' },
  { name: '--color-alert-soft', label: 'Vermelho suave' },
  { name: '--color-warning', label: 'Laranja' },
  { name: '--color-warning-soft', label: 'Laranja suave' },
  { name: '--color-text-main', label: 'Texto principal' },
  { name: '--color-text-secondary', label: 'Texto secundário' },
  { name: '--color-border-strong', label: 'Borda de campo' },
  { name: '--color-border', label: 'Borda decorativa' },
]

const fontSizes = [
  { name: '--font-size-display', sample: 'Apresentação pública' },
  { name: '--font-size-3xl', sample: 'Título da página' },
  { name: '--font-size-2xl', sample: 'Título de seção' },
  { name: '--font-size-xl', sample: 'Subtítulo' },
  { name: '--font-size-lg', sample: 'Texto de destaque' },
  { name: '--font-size-md', sample: 'Texto padrão do sistema' },
  { name: '--font-size-sm', sample: 'Texto auxiliar' },
  { name: '--font-size-xs', sample: 'Legenda' },
]

const spaces = ['--space-1', '--space-2', '--space-3', '--space-4', '--space-5', '--space-6', '--space-7', '--space-8', '--space-9']
const radii = ['--radius-sm', '--radius-md', '--radius-lg', '--radius-pill']

const initialSlots: TimeSlotData[] = [
  { time: '08:00', status: 'other' },
  { time: '09:00', status: 'other' },
  { time: '10:00', status: 'free' },
  { time: '11:00', status: 'free' },
  { time: '12:00', status: 'free' },
  { time: '13:00', status: 'own' },
  { time: '14:00', status: 'own' },
  { time: '15:00', status: 'free' },
  { time: '16:00', status: 'other' },
]

interface SectionProps {
  title: string
  description?: string
  children: ReactNode
}

function Section({ title, description, children }: SectionProps) {
  return (
    <section className={styles.section}>
      <Heading level={2}>{title}</Heading>
      {description && <Text tone="secondary">{description}</Text>}
      {children}
    </section>
  )
}

function Example({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={styles.example}>
      <Text as="span" size="xs" tone="secondary" className={styles.exampleLabel}>
        {label}
      </Text>
      {children}
    </div>
  )
}

export function DesignSystemPage() {
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [toast, setToast] = useState<{ message: string; variant: ToastVariant } | null>(null)
  const [date, setDate] = useState<Date | null>(null)
  const [slots, setSlots] = useState(initialSlots)
  const [loading, setLoading] = useState(false)

  function showToast(message: string, variant: ToastVariant) {
    setToast({ message, variant })
  }

  function handleSlotClick(time: string, status: SlotStatus) {
    if (status === 'other') return
    const next: SlotStatus = status === 'free' ? 'own' : 'free'
    setSlots((current) => current.map((slot) => (slot.time === time ? { ...slot, status: next } : slot)))
    showToast(next === 'own' ? `Horário das ${time} reservado.` : `Reserva das ${time} cancelada.`, next === 'own' ? 'success' : 'warning')
  }

  function simulateSave() {
    setLoading(true)
    setTimeout(() => {
      setLoading(false)
      showToast('Alterações salvas com sucesso.', 'success')
    }, 1500)
  }

  return (
    <Page id="conteudo" className={styles.page}>
      <Heading level={1}>Design System</Heading>
      <Text tone="secondary">
        Tokens e componentes base do Gestão de Condomínios. As telas devem usar somente estas peças,
        sem criar estilo próprio.
      </Text>

      <Section title="Cores" description="Variáveis de src/styles/tokens.css. Verde, vermelho e laranja indicam status.">
        <ul className={styles.swatches}>
          {colorTokens.map((token) => (
            <li key={token.name} className={styles.swatch}>
              <span className={styles.swatchColor} style={{ background: `var(${token.name})` }} />
              <span className={styles.swatchName}>{token.label}</span>
              <code className={styles.code}>{token.name}</code>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Tipografia, espaçamentos e raios">
        <Card>
          {fontSizes.map((font) => (
            <p key={font.name} className={styles.typeRow} style={{ fontSize: `var(${font.name})` }}>
              {font.sample} <code className={styles.code}>{font.name}</code>
            </p>
          ))}
        </Card>
        <div className={styles.tokenRow}>
          {spaces.map((space) => (
            <div key={space} className={styles.spaceItem}>
              <span className={styles.spaceBar} style={{ width: `var(${space})` }} />
              <code className={styles.code}>{space}</code>
            </div>
          ))}
        </div>
        <div className={styles.tokenRow}>
          {radii.map((radius) => (
            <div key={radius} className={styles.radiusItem}>
              <span className={styles.radiusBox} style={{ borderRadius: `var(${radius})` }} />
              <code className={styles.code}>{radius}</code>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Botões" description="Primário para a ação principal da tela; secundário para ações de apoio.">
        <div className={styles.row}>
          <Example label="Variantes">
            <div className={styles.row}>
              <Button>Ação principal</Button>
              <Button variant="secondary">Secundário</Button>
              <Button variant="success">Salvar</Button>
              <Button variant="alert">Excluir</Button>
              <Button variant="warning">Atenção</Button>
            </div>
          </Example>
          <Example label="Tamanho pequeno">
            <Button size="sm">Pequeno</Button>
          </Example>
          <Example label="Desabilitado">
            <Button disabled>Indisponível</Button>
          </Example>
          <Example label="Carregando">
            <Button loading={loading} onClick={simulateSave}>
              {loading ? 'Salvando…' : 'Salvar (simular)'}
            </Button>
          </Example>
        </div>
      </Section>

      <Section title="Campos de texto e select" description="Todo campo tem rótulo visível. Erros aparecem em texto, não só em cor.">
        <div className={styles.grid}>
          <Input label="E-mail" type="email" placeholder="nome@exemplo.com" />
          <Input label="Senha" type="password" hint="Use ao menos 8 caracteres." required />
          <Input label="CPF" defaultValue="123" error="CPF incompleto. Informe os 11 dígitos." />
          <Input label="Unidade" defaultValue="Apartamento 101" disabled />
          <Select label="Unidade de destino" options={unitOptions} hint="Escolha o apartamento do morador." />
          <Select label="Tipo de ocorrência" options={unitOptions} error="Selecione uma opção." />
        </div>
      </Section>

      <Section title="Badges de status">
        <div className={styles.row}>
          <Badge variant="success">Resolvida</Badge>
          <Badge variant="alert">Em aberto</Badge>
          <Badge variant="warning">Pendente</Badge>
          <Badge variant="primary">Em análise</Badge>
          <Badge variant="neutral">Arquivada</Badge>
          <Badge variant="warning" wrap>Entregue, aguardando confirmação</Badge>
        </div>
      </Section>

      <Section title="Tabela">
        <Table
          caption="Ocorrências recentes"
          headers={['Morador', 'Unidade', 'Status', 'Ação']}
          rows={[
            ['Maria Souza', '101', <Badge key="a" variant="success">Resolvida</Badge>, <Button key="b" size="sm">Ver</Button>],
            ['João Lima', '204', <Badge key="c" variant="alert">Em aberto</Badge>, <Button key="d" size="sm">Ver</Button>],
          ]}
        />
        <div className={styles.spacer} />
        <Table caption="Sem registros" headers={['Morador', 'Unidade', 'Status']} rows={[]} />
      </Section>

      <Section title="Card">
        <Card className={styles.narrow}>
          <Heading level={3} size="sm">Registro de encomenda</Heading>
          <Text size="sm" tone="secondary">Preencha os dados da encomenda recebida na portaria.</Text>
          <Select label="Unidade de destino" options={unitOptions} />
          <Button variant="success">Registrar</Button>
        </Card>
      </Section>

      <Section title="Modal e aviso (toast)" description="O modal prende o foco, fecha com Esc e devolve o foco ao botão que o abriu.">
        <div className={styles.row}>
          <Button onClick={() => setIsModalOpen(true)}>Abrir modal</Button>
          <Button variant="success" onClick={() => showToast('Encomenda registrada com sucesso!', 'success')}>Aviso de sucesso</Button>
          <Button variant="alert" onClick={() => showToast('Não foi possível salvar. Tente novamente.', 'alert')}>Aviso de erro</Button>
          <Button variant="warning" onClick={() => showToast('Reserva expira em 10 minutos.', 'warning')}>Aviso de atenção</Button>
          <Button variant="secondary" onClick={() => showToast('Nova versão disponível.', 'primary')}>Aviso informativo</Button>
        </div>
        <Modal title="Confirmar exclusão" isOpen={isModalOpen} onClose={() => setIsModalOpen(false)}>
          <Text tone="secondary">Tem certeza de que deseja excluir o registro deste visitante? Essa ação não pode ser desfeita.</Text>
          <div className={styles.modalActions}>
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>Cancelar</Button>
            <Button variant="alert" onClick={() => setIsModalOpen(false)}>Sim, excluir</Button>
          </div>
        </Modal>
        <Toast
          message={toast?.message ?? ''}
          variant={toast?.variant}
          isVisible={toast !== null}
          onClose={() => setToast(null)}
        />
      </Section>

      <Section title="Páginas públicas" description="Componentes da landing page e das prévias de acesso. Links mantêm a semântica de navegação.">
        <div className={styles.publicExamples}>
          <div className={styles.row}><ButtonLink to="/login">Entrar</ButtonLink><ButtonLink to="/cadastro" variant="secondary" size="sm">Conhecer o cadastro</ButtonLink></div>
          <Heading level={3} size="display">Mais vida em condomínio.</Heading>
          <PublicHeader />
          <FeatureCard icon="package" title="Encomendas organizadas">Do recebimento à confirmação de retirada.</FeatureCard>
          <div className={styles.narrow}><CommunityVisual /></div>
          <PublicCallToAction />
          <PublicFooter />
        </div>
      </Section>

      <Section title="Upload de arquivo">
        <div className={styles.narrow}>
          <Upload label="Anexar nota fiscal" accept="image/png, image/jpeg" />
        </div>
      </Section>

      <Section title="Telas operacionais" description="Estrutura, indicadores, avisos e confirmação de ações usados na portaria.">
        <ButtonLink to="/prototipos/portaria" variant="secondary">Abrir prévia da portaria</ButtonLink>
        <div className={styles.grid}>
          <MetricCard label="Aguardando retirada" value={3} description="Exemplo de indicador" />
          <MetricCard label="Confirmações pendentes" value={1} description="Exemplo de atenção" tone="warning" />
          <MetricCard label="Retiradas confirmadas" value={2} description="Exemplo de conclusão" tone="success" />
          <RecordPhoto alt="Imagem ilustrativa de encomenda" />
        </div>
        <Notice>Informação de apoio à operação.</Notice>
        <Notice tone="warning" title="Aguardando confirmação">A confirmação continua pendente até a ação do morador.</Notice>
        <Notice tone="alert">Não foi possível ler a foto. Os campos foram mantidos.</Notice>
        <Notice tone="success">Recebimento registrado.</Notice>
        <CheckField>Conferi os dados antes de registrar.</CheckField>
        <CheckField disabled>Confirmação indisponível</CheckField>
      </Section>

      <Section title="Calendário e grade de horários" description="Use as setas, Home, End, PageUp e PageDown no calendário. Clique num horário livre para reservar.">
        <Card>
          <div className={styles.booking}>
            <Calendar value={date} onChange={setDate} min={new Date()} />
            <div>
              <Heading level={3} size="sm">Quadra poliesportiva</Heading>
              <Text size="sm" tone="secondary">
                {date ? new Intl.DateTimeFormat('pt-BR', { dateStyle: 'full' }).format(date) : 'Escolha uma data para ver os horários.'}
              </Text>
              {date && <TimeGrid label="Horários da quadra poliesportiva" slots={slots} onSlotClick={handleSlotClick} />}
            </div>
          </div>
        </Card>
      </Section>
    </Page>
  )
}
