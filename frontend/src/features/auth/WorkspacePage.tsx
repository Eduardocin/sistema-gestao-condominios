import { Link } from 'react-router'
import {
  Badge,
  Button,
  ButtonLink,
  Card,
  Heading,
  Notice,
  OperationsLayout,
  Text,
} from '../../components'
import { useAuth } from './context'
import { condominiumNotice, homePath, profileLabels } from './navigation'
import { AccessDenied, RequireSession } from './SessionPages'
import { residentTabPermissions, visibleResidentNavigation } from '../resident/resident-navigation'
import { MyCondominiums } from '../condominiums/MyCondominiums'
import { ResidentNotices } from '../condominiums/ResidentNotices'
import { adminNavigation, platformNavigation, portariaNavigation } from './area-navigation'
import styles from './Auth.module.css'

const modules: Record<string, string[]> = {
  morador: [
    'Encomendas',
    'Visitantes',
    'Veículos',
    'Reservar área',
    'Minhas reservas',
    'Ocorrências',
  ],
  portaria: ['Recebimento e retirada de encomendas', 'Entrada e saída de visitantes'],
  administracao: [
    'Condomínio e estrutura',
    'Conta de funcionários',
    'Unidades e moradores',
    'Funcionários',
    'Avisos',
    'Áreas comuns',
    'Reservas',
    'Ocorrências',
    'Relatório de encomendas',
    'Suporte',
    'Comunicados',
  ],
  plataforma: ['Condomínios', 'Fila de suporte', 'Comunicados', 'Auditoria'],
  'sem-condominio': [],
}

function availableModule(area: string, label: string) {
  if (area === 'administracao' && label === 'Condomínio e estrutura') {
    return { to: '/app/administracao/condominio', action: 'Editar condomínio e estrutura' }
  }
  if (area === 'administracao' && label === 'Conta de funcionários') {
    return { to: '/app/administracao/conta-funcionarios', action: 'Gerenciar conta compartilhada' }
  }
  if (area === 'administracao' && label === 'Avisos') {
    return { to: '/app/administracao/avisos', action: 'Gerenciar avisos' }
  }
  if (area === 'administracao' && label === 'Unidades e moradores') {
    return { to: '/app/administracao/chaves', action: 'Gerenciar chaves' }
  }
  if (area === 'administracao' && label === 'Relatório de encomendas') {
    return { to: '/app/administracao/encomendas/relatorio', action: 'Ver relatório' }
  }
  if (area === 'administracao' && label === 'Suporte') {
    return { to: '/app/administracao/suporte', action: 'Abrir ou acompanhar chamados' }
  }
  if (area === 'administracao' && label === 'Comunicados') {
    return { to: '/app/administracao/comunicados', action: 'Ler comunicados' }
  }
  if (area === 'plataforma' && label === 'Fila de suporte') {
    return { to: '/app/plataforma/suporte', action: 'Atender chamados' }
  }
  if (area === 'plataforma' && label === 'Comunicados') {
    return { to: '/app/plataforma/comunicados', action: 'Enviar comunicados' }
  }
  if (area === 'plataforma' && label === 'Auditoria') {
    return { to: '/app/plataforma/auditoria', action: 'Consultar auditoria' }
  }
  if (area === 'plataforma' && label === 'Condomínios') {
    return { to: '/app/plataforma/condominios', action: 'Analisar condomínios' }
  }
  if (area === 'administracao' && label === 'Funcionários') {
    return { to: '/app/administracao/funcionarios', action: 'Gerenciar funcionários' }
  }
  if (area === 'administracao' && label === 'Áreas comuns') {
    return { to: '/app/administracao/areas-comuns', action: 'Gerenciar áreas comuns' }
  }
  if (area === 'administracao' && label === 'Reservas') {
    return { to: '/app/administracao/reservas', action: 'Gerenciar reservas' }
  }
  if (area === 'administracao' && label === 'Ocorrências') {
    return { to: '/app/administracao/ocorrencias', action: 'Tratar ocorrências' }
  }
  if (area === 'portaria' && label === 'Recebimento e retirada de encomendas') {
    return { to: '/app/portaria/encomendas', action: 'Acessar encomendas' }
  }
  if (area === 'portaria' && label === 'Entrada e saída de visitantes') {
    return { to: '/app/portaria/visitantes', action: 'Acessar visitantes' }
  }
  if (area === 'morador' && label === 'Encomendas') {
    return { to: '/app/morador/encomendas', action: 'Acompanhar encomendas' }
  }
  if (area === 'morador' && label === 'Visitantes') {
    return { to: '/app/morador/visitantes', action: 'Gerenciar visitantes' }
  }
  if (area === 'morador' && label === 'Veículos') {
    return { to: '/app/morador/veiculos', action: 'Gerenciar veículos' }
  }
  if (area === 'morador' && label === 'Reservar área') {
    return { to: '/app/morador/areas-comuns', action: 'Consultar áreas e horários' }
  }
  if (area === 'morador' && label === 'Minhas reservas') {
    return { to: '/app/morador/reservas', action: 'Acompanhar reservas' }
  }
  if (area === 'morador' && label === 'Ocorrências') {
    return { to: '/app/morador/ocorrencias', action: 'Acompanhar ocorrências' }
  }
  return null
}

export function WorkspacePage({ area }: { area: string }) {
  const { snapshot, client } = useAuth()
  const identity = snapshot.identity
  if (!identity || snapshot.status !== 'authenticated')
    return <RequireSession>{null}</RequireSession>
  const destination = homePath(identity, snapshot.condominiums)
  if (destination !== `/app/${area}`) return <AccessDenied />
  const profile = identity.administrador_plataforma
    ? 'Plataforma'
    : identity.condominio
      ? profileLabels[identity.condominio.perfil]
      : 'Minha conta'
  const name =
    identity.condominio?.nome ??
    (identity.administrador_plataforma ? 'Gestão da plataforma' : 'Minha conta')
  const notice = condominiumNotice(identity.condominio?.status)
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
  const navigation =
    area === 'administracao'
      ? adminNavigation
      : area === 'plataforma'
        ? platformNavigation
        : area === 'portaria'
          ? portariaNavigation
          : area === 'morador'
            ? visibleResidentNavigation(identity.unidades)
            : [{ key: 'overview', label: 'Visão geral', to: destination, symbol: '⌂' }]

  return (
    <OperationsLayout
      activeKey="overview"
      navigation={navigation}
      workspace={{ name, profile, tools }}
    >
      <div className={styles.content}>
        <div>
          <Badge variant="primary">{profile}</Badge>
          <Heading level={1}>Olá, {identity.usuario.nome}.</Heading>
          <Text tone="secondary">
            {area === 'sem-condominio'
              ? 'Acompanhe as informações da sua conta.'
              : `Bem-vindo à sua área em ${name}.`}
          </Text>
        </div>
        {area === 'sem-condominio' && (
          <Notice tone="warning" title={notice.title}>
            {notice.message}
          </Notice>
        )}
        {(area === 'sem-condominio' || area === 'administracao') && <MyCondominiums />}
        {area === 'morador' && <ResidentNotices />}
        {(area === 'sem-condominio' || area === 'morador') && (
          <div>
            <ButtonLink to="/app/vincular-unidade" variant="secondary">
              Vincular unidade
            </ButtonLink>
          </div>
        )}
        {!identity.administrador_plataforma && (
          <div>
            <ButtonLink to="/app/perfil" variant="secondary">
              Editar perfil
            </ButtonLink>
          </div>
        )}
        {area === 'morador' &&
          identity.unidades.some((unit) => unit.abas?.includes('usuarios')) && (
            <div>
              <ButtonLink to="/app/morador/permissoes" variant="secondary">
                Permissões dos moradores
              </ButtonLink>
            </div>
          )}
        <Card>
          <Heading level={2} size="md">
            Seu acesso
          </Heading>
          <dl className={styles.details}>
            <div>
              <dt>Nome</dt>
              <dd>{identity.usuario.nome}</dd>
            </div>
            <div>
              <dt>E-mail</dt>
              <dd>{identity.usuario.email}</dd>
            </div>
            <div>
              <dt>Perfil</dt>
              <dd>{profile}</dd>
            </div>
            {identity.condominio && (
              <div>
                <dt>Condomínio</dt>
                <dd>{identity.condominio.nome}</dd>
              </div>
            )}
            {identity.unidades.length > 0 && (
              <div>
                <dt>Unidades vinculadas</dt>
                <dd>{identity.unidades.map((unit) => unit.identificacao).join(', ')}</dd>
              </div>
            )}
          </dl>
        </Card>
        {modules[area]?.length > 0 && (
          <section aria-labelledby="modulos-titulo">
            <Heading id="modulos-titulo" level={2} size="md">
              Serviços da sua área
            </Heading>
            <Text tone="secondary">Escolha um serviço disponível para sua área.</Text>
            <div className={styles.modules}>
              {modules[area]
                .filter((label) => {
                  if (area !== 'morador') return true
                  const tab = (
                    {
                      Encomendas: 'packages',
                      Visitantes: 'visitors',
                      Veículos: 'vehicles',
                      'Reservar área': 'reserve',
                      'Minhas reservas': 'reservations',
                      Ocorrências: 'occurrences',
                    } as Record<string, string>
                  )[label]
                  return (
                    !tab ||
                    identity.unidades.some((unit) =>
                      unit.abas?.includes(residentTabPermissions[tab]),
                    )
                  )
                })
                .map((label) => {
                  const target = availableModule(area, label)
                  return (
                    <Card key={label} className={styles.module}>
                      <Heading level={3} size="sm">
                        {label}
                      </Heading>
                      {target ? (
                        <>
                          <Badge variant="success">Disponível</Badge>
                          <ButtonLink to={target.to}>{target.action}</ButtonLink>
                        </>
                      ) : (
                        <>
                          <Badge variant="neutral">Em breve</Badge>
                          <Button variant="secondary" disabled>
                            Indisponível
                          </Button>
                        </>
                      )}
                    </Card>
                  )
                })}
            </div>
          </section>
        )}
      </div>
    </OperationsLayout>
  )
}
