import { SupportShell } from './SupportShell'
import { TicketsView } from './Tickets'
import { ReceivedAnnouncements, SentAnnouncements } from './Announcements'
import { PackageReportView } from './PackageReport'

export function AdminSupportPage() {
  return (
    <SupportShell area="administracao" activeKey="support" title="Suporte da plataforma">
      {(api) => <TicketsView scope="administracao" api={api} />}
    </SupportShell>
  )
}

export function PlatformSupportPage() {
  return (
    <SupportShell area="plataforma" activeKey="support" title="Fila de suporte">
      {(api) => <TicketsView scope="plataforma" api={api} />}
    </SupportShell>
  )
}

export function PlatformAnnouncementsPage() {
  return (
    <SupportShell area="plataforma" activeKey="announcements" title="Comunicados às Administrações">
      {(api) => <SentAnnouncements api={api} />}
    </SupportShell>
  )
}

export function AdminAnnouncementsPage() {
  return (
    <SupportShell area="administracao" activeKey="announcements" title="Comunicados da plataforma">
      {(api) => <ReceivedAnnouncements api={api} />}
    </SupportShell>
  )
}

export function PackageReportPage() {
  return (
    <SupportShell area="administracao" activeKey="packageReport" title="Relatório de encomendas">
      {(api) => <PackageReportView api={api} />}
    </SupportShell>
  )
}
