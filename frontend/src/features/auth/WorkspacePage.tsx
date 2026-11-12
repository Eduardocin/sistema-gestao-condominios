import { Link } from 'react-router'
import { Badge, Button, ButtonLink, Card, Heading, Notice, OperationsLayout, Text } from '../../components'
import { useAuth } from './context'
import { condominiumNotice, homePath, profileLabels } from './navigation'
import { AccessDenied, RequireSession } from './SessionPages'
import styles from './Auth.module.css'

const modules: Record<string, string[]> = {
  morador: ['Encomendas', 'Visitantes', 'Reservas', 'Ocorrências'],
  portaria: ['Recebimento e retirada de encomendas', 'Entrada e saída de visitantes'],
  administracao: ['Unidades e moradores', 'Funcionários', 'Aprovações'],
  plataforma: ['Condomínios', 'Administração da plataforma'],
  'sem-condominio': [],
}

export function WorkspacePage({ area }: { area: string }) {
  const { snapshot, client } = useAuth()
  const identity = snapshot.identity
  if (!identity || snapshot.status !== 'authenticated') return <RequireSession>{null}</RequireSession>
  const destination = homePath(identity, snapshot.condominiums)
  if (destination !== `/app/${area}`) return <AccessDenied />
  const profile = identity.administrador_plataforma ? 'Plataforma' : identity.condominio ? profileLabels[identity.condominio.perfil] : 'Minha conta'
  const name = identity.condominio?.nome ?? (identity.administrador_plataforma ? 'Gestão da plataforma' : 'Minha conta')
  const notice = condominiumNotice(identity.condominio?.status)
  const tools = <div className={styles.actions}>
    {snapshot.condominiums.length > 1 && <Link to="/selecionar-condominio">Trocar condomínio</Link>}
    <Button variant="secondary" size="sm" onClick={() => client.logout()}>Sair</Button>
  </div>
  return <OperationsLayout activeKey="overview" navigation={[{ key: 'overview', label: 'Visão geral', to: destination, symbol: '⌂' }, ...(area === 'administracao' ? [{ key: 'employees', label: 'Funcionários', to: '/app/administracao/funcionarios', symbol: '♙' }] : [])]} workspace={{ name, profile, tools }}>
    <div className={styles.content}>
      <div><Badge variant="primary">{profile}</Badge><Heading level={1}>Olá, {identity.usuario.nome}.</Heading><Text tone="secondary">{area === 'sem-condominio' ? 'Acompanhe as informações da sua conta.' : `Bem-vindo à sua área em ${name}.`}</Text></div>
      {area === 'sem-condominio' && <Notice tone="warning" title={notice.title}>{notice.message}</Notice>}
      <Card><Heading level={2} size="md">Seu acesso</Heading><dl className={styles.details}>
        <div><dt>Nome</dt><dd>{identity.usuario.nome}</dd></div>
        <div><dt>E-mail</dt><dd>{identity.usuario.email}</dd></div>
        <div><dt>Perfil</dt><dd>{profile}</dd></div>
        {identity.condominio && <div><dt>Condomínio</dt><dd>{identity.condominio.nome}</dd></div>}
        {identity.unidades.length > 0 && <div><dt>Unidades vinculadas</dt><dd>{identity.unidades.map((unit) => unit.identificacao).join(', ')}</dd></div>}
      </dl></Card>
      {modules[area]?.length > 0 && <section aria-labelledby="modulos-titulo"><Heading id="modulos-titulo" level={2} size="md">Serviços da sua área</Heading>
        <Text tone="secondary">Escolha um serviço disponível para sua área.</Text>
        <div className={styles.modules}>{modules[area].map((label) => <Card key={label} className={styles.module}><Heading level={3} size="sm">{label}</Heading>{area === 'administracao' && label === 'Funcionários' ? <><Badge variant="success">Disponível</Badge><ButtonLink to="/app/administracao/funcionarios">Gerenciar funcionários</ButtonLink></> : <><Badge variant="neutral">Em breve</Badge><Button variant="secondary" disabled>Indisponível</Button></>}</Card>)}</div>
      </section>}
    </div>
  </OperationsLayout>
}
