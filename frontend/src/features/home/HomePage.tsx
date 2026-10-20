import { Badge, ButtonLink, CommunityVisual, FeatureCard, Heading, Page, PublicCallToAction, PublicFooter, PublicHeader, Text } from '../../components'
import type { FeatureIconName } from '../../components'
import styles from './HomePage.module.css'

const features: Array<{ icon: FeatureIconName; title: string; description: string }> = [
  { icon: 'package', title: 'Encomendas organizadas', description: 'Do recebimento na portaria à confirmação de retirada, acompanhe cada entrega.' },
  { icon: 'visitors', title: 'Visitantes e acessos', description: 'Autorizações de visita e registros de entrada e saída em um só lugar.' },
  { icon: 'calendar', title: 'Reserva de espaços', description: 'Consulte a disponibilidade das áreas comuns e planeje seus próximos encontros.' },
  { icon: 'message', title: 'Ocorrências acompanhadas', description: 'Um canal para registrar situações, conversar com a administração e acompanhar o andamento.' },
  { icon: 'bell', title: 'Avisos que aproximam', description: 'Informações do condomínio organizadas para chegar a quem precisa.' },
  { icon: 'building', title: 'Pessoas e unidades', description: 'Conecte moradores, unidades e administração à rotina do condomínio.' },
]

const audiences = [
  { number: '01', title: 'Para quem mora', description: 'Mais praticidade para acompanhar encomendas, autorizar visitas e participar da vida em condomínio.' },
  { number: '02', title: 'Para quem administra', description: 'Uma visão organizada das informações, solicitações e espaços sob sua responsabilidade.' },
  { number: '03', title: 'Para quem está na portaria', description: 'Fluxos claros para receber encomendas e registrar a movimentação de visitantes.' },
]

export function HomePage() {
  return (
    <>
      <PublicHeader />
      <Page id="conteudo" tabIndex={-1} className={styles.page}>
        <section className={styles.hero} aria-labelledby="apresentacao">
          <div className={styles.heroCopy}>
            <Badge variant="primary">Mais conexão no dia a dia</Badge>
            <Heading level={1} size="display" id="apresentacao">Menos tarefas soltas. Mais vida em condomínio.</Heading>
            <Text tone="secondary">Moradores, administração e portaria mais próximos. Uma plataforma para organizar as rotinas e dar espaço ao que importa: viver bem.</Text>
            <div className={styles.actions}>
              <ButtonLink to="/cadastro">Conhecer o cadastro <span aria-hidden="true">→</span></ButtonLink>
              <ButtonLink to="/login" variant="secondary">Já tenho acesso</ButtonLink>
            </div>
            <Text size="xs" tone="secondary">Acesso e cadastro disponíveis em breve.</Text>
          </div>
          <CommunityVisual />
        </section>

        <section id="funcionalidades" className={styles.section} aria-labelledby="funcionalidades-titulo">
          <div className={styles.sectionIntro}>
            <Badge variant="neutral">Soluções para o seu condomínio</Badge>
            <Heading level={2} id="funcionalidades-titulo">Uma rotina conectada, do portão à sua porta.</Heading>
            <Text tone="secondary">Recursos pensados para reunir o essencial da gestão do condomínio, com um lugar certo para cada assunto.</Text>
          </div>
          <div className={styles.featureGrid}>
            {features.map((feature) => <FeatureCard key={feature.title} icon={feature.icon} title={feature.title}>{feature.description}</FeatureCard>)}
          </div>
        </section>

        <section id="para-quem" className={styles.section} aria-labelledby="publicos-titulo">
          <div className={styles.sectionIntro}>
            <Heading level={2} id="publicos-titulo">Um condomínio. Diferentes rotinas. O mesmo cuidado.</Heading>
            <Text tone="secondary">Uma experiência pensada para cada papel, com os acessos correspondentes às suas responsabilidades.</Text>
          </div>
          <div className={styles.audienceGrid}>
            {audiences.map((audience) => (
              <div key={audience.number} className={styles.audience}>
                <Badge variant="primary">{audience.number}</Badge>
                <Heading level={3} size="sm">{audience.title}</Heading>
                <Text size="sm" tone="secondary">{audience.description}</Text>
              </div>
            ))}
          </div>
        </section>

        <section id="como-funciona" className={styles.section} aria-labelledby="como-funciona-titulo">
          <div className={styles.sectionIntro}>
            <Heading level={2} id="como-funciona-titulo">Como funciona</Heading>
            <Text tone="secondary">Da organização inicial às pequenas tarefas do dia a dia.</Text>
          </div>
          <ol className={styles.steps}>
            <li><Heading level={3} size="sm">Cadastre o condomínio</Heading><Text size="sm" tone="secondary">A administração inicia o cadastro e informa os dados necessários para análise.</Text></li>
            <li><Heading level={3} size="sm">Conecte as pessoas</Heading><Text size="sm" tone="secondary">Organize as unidades e os vínculos de moradores e funcionários.</Text></li>
            <li><Heading level={3} size="sm">Acompanhe a rotina</Heading><Text size="sm" tone="secondary">Encomendas, visitas, reservas e solicitações passam a ter um fluxo organizado.</Text></li>
          </ol>
        </section>
        <section className={styles.section} aria-label="Conheça a plataforma"><PublicCallToAction /></section>
      </Page>
      <PublicFooter />
    </>
  )
}
