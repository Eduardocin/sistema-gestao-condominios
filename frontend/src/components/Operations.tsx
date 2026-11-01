import type { ComponentProps, ReactNode } from 'react'
import { Link } from 'react-router'
import { Badge } from './Badge'
import { Heading } from './Heading'
import { SiteBrand } from './PublicSite'
import { Text } from './Text'
import { cx } from '../utils/cx'
import styles from './Operations.module.css'

interface NavigationItem { key: string; label: string; to: string; symbol: string }
interface WorkspaceContext { name: string; profile: string; tools?: ReactNode }
export function OperationsLayout({ children, navigation, activeKey, tools, workspace }: { children: ReactNode; navigation: NavigationItem[]; activeKey: string; tools?: ReactNode; workspace?: WorkspaceContext }) {
  return (
    <div className={styles.shell}>
      <a href="#conteudo" className={styles.skipLink}>Pular para o conteúdo</a>
      <aside className={styles.sidebar}>
        <SiteBrand />
        <div className={styles.workspace}><Text size="xs" tone="secondary">{workspace ? 'ÁREA DE ACESSO' : 'CONDOMÍNIO DE EXEMPLO'}</Text><Text><strong>{workspace?.name ?? 'Jardim das Palmeiras'}</strong></Text><Badge variant="primary">{workspace?.profile ?? 'Portaria'}</Badge></div>
        <nav className={styles.navigation} aria-label={workspace ? 'Navegação da sua área' : 'Navegação do protótipo'}>
          {navigation.map((item) => <Link key={item.key} to={item.to} className={cx(styles.navItem, activeKey === item.key && styles.active)} aria-current={activeKey === item.key ? 'page' : undefined}><span className={styles.navSymbol} aria-hidden="true">{item.symbol}</span>{item.label}</Link>)}
        </nav>
        <div className={styles.sidebarFooter}><Text size="sm" tone="secondary">Tudo em seu lugar.<br />Uma rotina mais tranquila.</Text><Link to="/" className={styles.homeLink}>← Página inicial</Link></div>
      </aside>
      <div className={styles.workspaceMain}>
        <header className={styles.topbar}><Text size="sm" tone="secondary">{workspace?.name ?? 'Gestão do condomínio'} <span aria-hidden="true">/</span> <strong>{workspace?.profile ?? 'Portaria'}</strong></Text>{workspace ? workspace.tools : <Badge variant="neutral">Prévia navegável</Badge>}</header>
        {!workspace && <div className={styles.demoBar}><Text size="sm"><strong>Ambiente de demonstração.</strong> Dados fictícios; alterações e fotos ficam apenas nesta aba e são perdidas ao recarregar.</Text>{tools}</div>}
        <main id="conteudo" tabIndex={-1} className={styles.main}>{children}</main>
      </div>
    </div>
  )
}

export function MetricCard({ label, value, description, tone = 'primary' }: { label: string; value: number; description: string; tone?: 'primary' | 'warning' | 'success' }) {
  return <div className={cx(styles.metric, styles[tone])}><Text size="sm" tone="secondary">{label}</Text><Text className={styles.metricValue}>{value.toString().padStart(2, '0')}</Text><Text size="xs" tone="secondary">{description}</Text></div>
}

export function Notice({ children, tone = 'primary', title, ...props }: ComponentProps<'div'> & { tone?: 'primary' | 'warning' | 'alert' | 'success'; title?: string }) {
  return <div className={cx(styles.notice, styles[tone])} {...props}>{title && <Heading level={3} size="sm">{title}</Heading>}<Text as="div" size="sm">{children}</Text></div>
}

export function CheckField({ children, ...props }: Omit<ComponentProps<'input'>, 'type'>) {
  return <label className={styles.check}><input type="checkbox" {...props} /><span>{children}</span></label>
}

export function RecordPhoto({ src, alt }: { src?: string; alt: string }) {
  return src ? <img className={styles.photo} src={src} alt={alt} /> : <div className={styles.photoPlaceholder}><svg viewBox="0 0 80 80" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="m15 27 25-14 25 14v29L40 70 15 56V27Zm0 0 25 14 25-14M40 41v29M28 20l25 14" /></svg><Text size="xs" tone="secondary">Imagem ilustrativa do exemplo</Text></div>
}
