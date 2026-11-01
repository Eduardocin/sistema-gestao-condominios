import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link, Navigate } from 'react-router'
import { Button, ButtonLink, Card, Heading, Notice, Page, PublicHeader, Select, Text } from '../../components'
import { useAuth } from './context'
import { homePath, profileLabels } from './navigation'
import { accessMessage } from './session'
import styles from './Auth.module.css'

export function SessionStatus() {
  const { snapshot, client } = useAuth()
  return <><PublicHeader /><Page id="conteudo" tabIndex={-1} className={styles.access}>
    <Card><Heading level={1} size="md">{snapshot.status === 'loading' ? 'Validando seu acesso…' : 'Não foi possível validar seu acesso'}</Heading>
      {snapshot.status === 'loading' ? <Text role="status">Aguarde enquanto consultamos sua sessão.</Text> : <>
        <Notice tone="alert" role="alert">{snapshot.message}</Notice>
        <div className={styles.actions}><Button onClick={() => { void client.restore() }}>Tentar novamente</Button><Button variant="secondary" onClick={() => client.logout()}>Voltar ao login</Button></div>
      </>}
    </Card>
  </Page></>
}

export function RequireSession({ children }: { children: ReactNode }) {
  const { snapshot } = useAuth()
  if (snapshot.status === 'loading' || snapshot.status === 'error') return <SessionStatus />
  if (snapshot.status !== 'authenticated' || !snapshot.identity) return <Navigate to="/login" replace />
  return children
}

export function AppEntry() {
  const { snapshot } = useAuth()
  return <RequireSession>{snapshot.identity && <Navigate to={homePath(snapshot.identity, snapshot.condominiums)} replace />}</RequireSession>
}

export function AccessDenied() {
  return <Page className={styles.access}><Notice tone="alert" title="Acesso negado" role="alert">Seu perfil não permite abrir esta área. Escolha a área disponível para sua conta.</Notice><ButtonLink to="/app">Ir para minha área</ButtonLink></Page>
}

export function SelectCondominiumPage() {
  const { snapshot, client } = useAuth()
  const [selected, setSelected] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  if (snapshot.status !== 'authenticated' || !snapshot.identity) return <RequireSession>{null}</RequireSession>
  if (done || snapshot.condominiums.length < 2) return <Navigate to={homePath(snapshot.identity, snapshot.condominiums)} replace />

  async function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending) return
    setPending(true)
    setError(null)
    try { await client.selectCondominium(selected); setDone(true) }
    catch (cause) { setError(accessMessage(cause)) }
    finally { setPending(false) }
  }

  return <><PublicHeader /><Page id="conteudo" tabIndex={-1} className={styles.access}>
    <Heading level={1}>Escolha seu condomínio</Heading>
    <Text tone="secondary">Olá, {snapshot.identity.usuario.nome}. Escolha o condomínio que deseja acessar agora.</Text>
    <Card><form onSubmit={submit} className={styles.form}>
      <Select label="Condomínio" required value={selected} onChange={(event) => setSelected(event.target.value)} disabled={pending}
        options={snapshot.condominiums.map((item) => ({ value: item.id, label: `${item.nome} · ${profileLabels[item.perfil]}${item.status === 'desativado' ? ' · Indisponível' : ''}` }))} />
      {error && <Notice tone="alert" role="alert">{error}</Notice>}
      <Button type="submit" loading={pending} disabled={!selected}>Acessar condomínio</Button>
    </form></Card>
    <div className={styles.actions}>{snapshot.identity.condominio && <Link to="/app">Voltar à minha área</Link>}<Button variant="secondary" onClick={() => client.logout()}>Sair da conta</Button></div>
  </Page></>
}
