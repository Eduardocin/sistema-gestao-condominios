import { useState } from 'react'
import type { SubmitEvent } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Button, Card, Heading, Input, Notice, Page, PublicFooter, PublicHeader, Text } from '../../components'
import { useAuth } from './context'
import {
  isInvalidResetToken,
  passwordHint,
  passwordRuleError,
  recoveryRequestError,
  resetPasswordError,
} from './password'
import styles from './Auth.module.css'

export function ForgotPasswordPage() {
  const { client } = useAuth()
  const [email, setEmail] = useState('')
  const [pending, setPending] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending) return
    setPending(true)
    setError('')
    try {
      await client.requestPasswordReset(email)
      setSent(true)
    } catch (failure) {
      setError(recoveryRequestError(failure))
    } finally {
      setPending(false)
    }
  }

  return (
    <>
      <PublicHeader />
      <Page id="conteudo" tabIndex={-1} className={styles.access}>
        <div>
          <Heading level={1}>Recuperar senha</Heading>
          <Text tone="secondary">Informe o e-mail da sua conta e enviaremos as instruções para criar uma nova senha.</Text>
        </div>
        <Card>
          {sent ? (
            <Notice tone="success" role="status" title="Pedido recebido">
              Se houver uma conta com este e-mail, você receberá as instruções em instantes. Confira também a caixa de spam.
            </Notice>
          ) : (
            <form onSubmit={(event) => void submit(event)} className={styles.form}>
              <Input label="E-mail" name="email" type="email" autoComplete="username" maxLength={254} required value={email} onChange={(event) => setEmail(event.target.value)} disabled={pending} placeholder="nome@exemplo.com" />
              {error && <Notice tone="alert" role="alert">{error}</Notice>}
              <Button type="submit" loading={pending}>Enviar instruções</Button>
            </form>
          )}
        </Card>
        <Link to="/login">← Voltar ao login</Link>
      </Page>
      <PublicFooter />
    </>
  )
}

export function ResetPasswordPage() {
  const { client } = useAuth()
  const [params, setParams] = useSearchParams()
  const token = params.get('token')?.trim() ?? ''
  const [pending, setPending] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const [tokenInvalid, setTokenInvalid] = useState(false)

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending || !token) return
    const form = new FormData(event.currentTarget)
    const password = String(form.get('senha') ?? '')
    const problem = passwordRuleError(password, String(form.get('confirmacao') ?? ''))
    if (problem) {
      setError(problem)
      setTokenInvalid(false)
      return
    }
    setPending(true)
    setError('')
    setTokenInvalid(false)
    try {
      await client.resetPassword(token, password)
      setDone(true)
      setParams({}, { replace: true })
    } catch (failure) {
      setError(resetPasswordError(failure))
      setTokenInvalid(isInvalidResetToken(failure))
    } finally {
      setPending(false)
    }
  }

  return (
    <>
      <PublicHeader />
      <Page id="conteudo" tabIndex={-1} className={styles.access}>
        <div>
          <Heading level={1}>Criar nova senha</Heading>
          <Text tone="secondary">Escolha a nova senha da sua conta.</Text>
        </div>
        <Card>
          {done ? (
            <>
              <Notice tone="success" role="status" title="Senha alterada">
                Sua senha foi redefinida. Entre com a nova senha.
              </Notice>
              <Link to="/login">Ir para o login</Link>
            </>
          ) : !token ? (
            <Notice tone="alert" role="alert" title="Link incompleto">
              O link de recuperação está incompleto. Solicite um novo e-mail.
              <div><Link to="/recuperar-senha">Recuperar senha</Link></div>
            </Notice>
          ) : (
            <form onSubmit={(event) => void submit(event)} className={styles.form}>
              <Input label="Nova senha" name="senha" type="password" autoComplete="new-password" required minLength={8} maxLength={128} hint={passwordHint} disabled={pending} />
              <Input label="Confirmar nova senha" name="confirmacao" type="password" autoComplete="new-password" required minLength={8} maxLength={128} disabled={pending} />
              {error && (
                <Notice tone="alert" role="alert">
                  {error} {tokenInvalid && <Link to="/recuperar-senha">Solicitar novo e-mail</Link>}
                </Notice>
              )}
              <Button type="submit" loading={pending}>Salvar nova senha</Button>
            </form>
          )}
        </Card>
      </Page>
      <PublicFooter />
    </>
  )
}
