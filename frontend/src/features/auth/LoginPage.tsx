import { useState } from 'react'
import { Link, Navigate } from 'react-router'
import { Badge, Button, Card, Heading, Input, Notice, Page, PublicFooter, PublicHeader, Text } from '../../components'
import { useAuth } from './context'
import { homePath } from './navigation'
import { SessionStatus } from './SessionPages'
import styles from './Auth.module.css'

export function LoginPage() {
  const { snapshot, client } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (snapshot.status === 'loading' || snapshot.status === 'error') return <SessionStatus />
  if (snapshot.identity) return <Navigate to={homePath(snapshot.identity, snapshot.condominiums)} replace />

  async function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending) return
    setPending(true)
    setError(null)
    try { await client.login(email, password) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível entrar. Tente novamente.') }
    finally { setPassword(''); setPending(false) }
  }

  return <><PublicHeader /><Page id="conteudo" tabIndex={-1} className={styles.access}>
    <div><Badge variant="primary">Bem-vindo de volta</Badge><Heading level={1}>Seu condomínio mais perto.</Heading><Text tone="secondary">Acesse sua conta para acompanhar a rotina do seu condomínio.</Text></div>
    <Card><Heading level={2} size="md">Entrar na sua conta</Heading>
      <form onSubmit={submit} className={styles.form}>
        <Input label="E-mail" name="email" type="email" autoComplete="username" maxLength={254} required value={email} onChange={(event) => setEmail(event.target.value)} disabled={pending} placeholder="nome@exemplo.com" />
        <Input label="Senha" name="password" type="password" autoComplete="current-password" maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} disabled={pending} />
        {(error || snapshot.message) && <Notice tone="alert" role="alert">{error || snapshot.message}</Notice>}
        <Button type="submit" loading={pending}>Entrar</Button>
      </form>
      <Text size="sm" className={styles.link}>Ainda não tem conta? <Link to="/cadastro">Conhecer o cadastro</Link></Text>
    </Card><Link to="/">← Voltar à apresentação</Link>
  </Page><PublicFooter /></>
}
