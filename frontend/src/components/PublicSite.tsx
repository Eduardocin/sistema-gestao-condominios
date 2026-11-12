import { Link } from 'react-router'
import type { ReactNode } from 'react'
import { Badge } from './Badge'
import { ButtonLink } from './ButtonLink'
import { Card } from './Card'
import { Heading } from './Heading'
import { Text } from './Text'
import styles from './PublicSite.module.css'

export type FeatureIconName = 'building' | 'package' | 'visitors' | 'calendar' | 'message' | 'bell'

const paths: Record<FeatureIconName, ReactNode> = {
  building: <><path d="M4 21V5l8-3v19M12 8h8v13M2 21h20M8 7v1m0 3v1m0 3v1m8-4v1m0 3v1" /></>,
  package: <><path d="m3 7 9-5 9 5v10l-9 5-9-5V7Zm0 0 9 5 9-5M12 12v10M7.5 4.5l9 5" /></>,
  visitors: <><circle cx="9" cy="7" r="3" /><path d="M3 21v-3a6 6 0 0 1 12 0v3M17 4a3 3 0 0 1 0 6m2 4a5 5 0 0 1 3 4v3" /></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4m10-4v4M3 11h18m-13 4h1m6 0h1m-8 3h1" /></>,
  message: <path d="M21 15a3 3 0 0 1-3 3H8l-5 4V5a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3v10ZM7 7h10M7 12h6" />,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></>,
}

function FeatureIcon({ name }: { name: FeatureIconName }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={styles.icon} aria-hidden="true">{paths[name]}</svg>
}

export function SiteBrand() {
  return (
    <Link to="/" className={styles.brand} aria-label="Gestão de Condomínios — início">
      <span className={styles.brandIcon}><FeatureIcon name="building" /></span>
      <span>Gestão de<br />Condomínios</span>
    </Link>
  )
}

export function PublicHeader() {
  return (
    <>
      <a className={styles.skipLink} href="#conteudo">Pular para o conteúdo</a>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <SiteBrand />
          <nav aria-label="Navegação principal" className={styles.navigation}>
            <a href="/#funcionalidades">Funcionalidades</a>
            <a href="/#para-quem">Para quem é</a>
            <a href="/#como-funciona">Como funciona</a>
          </nav>
          <ButtonLink to="/login" variant="secondary">Entrar <span aria-hidden="true">↗</span></ButtonLink>
        </div>
      </header>
    </>
  )
}

export function PublicFooter() {
  return (
    <footer className={styles.footer}>
      <div className={styles.footerInner}>
        <div><SiteBrand /><Text size="sm" tone="secondary" className={styles.footerNote}>Tecnologia para uma rotina mais próxima.</Text></div>
        <div className={styles.footerMeta}>
          <nav aria-label="Links do rodapé"><Link to="/login">Entrar</Link><Link to="/cadastro">Criar conta</Link></nav>
          <Text size="xs" tone="secondary">Gestão de Condomínios · Conectando pessoas e rotinas.</Text>
        </div>
      </div>
    </footer>
  )
}

export function FeatureCard({ icon, title, children }: { icon: FeatureIconName; title: string; children: ReactNode }) {
  return (
    <Card className={styles.featureCard}>
      <span className={styles.featureIcon}><FeatureIcon name={icon} /></span>
      <Heading level={3} size="sm">{title}</Heading>
      <Text size="sm" tone="secondary">{children}</Text>
    </Card>
  )
}

/** Ilustração decorativa, sem dados de moradores ou indicadores fictícios. */
export function CommunityVisual() {
  return (
    <div className={styles.visual}>
      <Badge variant="primary">Pessoas, espaços e rotinas</Badge>
      <svg viewBox="0 0 480 340" className={styles.buildings} aria-hidden="true">
        <circle cx="378" cy="67" r="34" className={styles.softShape} />
        <path d="M38 290h404" className={styles.outline} />
        <path d="M72 288V118l111-38v208M184 288V42l124 25v221M309 288V143l91 24v121" className={styles.tower} />
        <path d="M184 42v246M309 67v221" className={styles.outline} />
        {[0, 1, 2, 3].map((row) => <g key={row} className={styles.window}>
          <rect x="96" y={141 + row * 33} width="15" height="15" rx="2" />
          <rect x="135" y={128 + row * 33} width="15" height="15" rx="2" />
          <rect x="211" y={101 + row * 36} width="17" height="18" rx="2" />
          <rect x="263" y={111 + row * 36} width="17" height="18" rx="2" />
        </g>)}
        <g className={styles.window}><rect x="335" y="188" width="14" height="17" rx="2" /><rect x="372" y="198" width="14" height="17" rx="2" /><rect x="335" y="232" width="14" height="17" rx="2" /><rect x="372" y="242" width="14" height="17" rx="2" /></g>
        <path d="M225 288v-41h35v41" className={styles.door} />
        <path d="M48 290v-35m378 35v-35" className={styles.outline} />
        <circle cx="48" cy="238" r="23" className={styles.tree} /><circle cx="426" cy="238" r="23" className={styles.tree} />
        <path d="M48 226v40m378-40v40" className={styles.outline} />
      </svg>
      <div className={styles.visualCaption}><span className={styles.captionMark} aria-hidden="true">↗</span><Text>Uma visão mais simples<br /><strong>da vida em condomínio.</strong></Text></div>
    </div>
  )
}

export function PublicCallToAction() {
  return (
    <div className={styles.callToAction}>
      <div><Text size="sm" className={styles.calloutEyebrow}>MAIS PROXIMIDADE. MENOS COMPLICAÇÃO.</Text><Heading level={2}>Um novo jeito de cuidar do seu condomínio.</Heading><Text tone="secondary">Mais praticidade para moradores e mais clareza para quem cuida do condomínio.</Text></div>
      <ButtonLink to="/cadastro">Criar conta <span aria-hidden="true">→</span></ButtonLink>
    </div>
  )
}
