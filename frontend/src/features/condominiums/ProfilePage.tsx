import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { isAxiosError } from 'axios'
import { Button, ButtonLink, Card, Heading, Input, Notice, Page } from '../../components'
import { useAuth } from '../auth/context'
import { changePasswordError, passwordHint, passwordRuleError } from '../auth/password'
import styles from '../resident/ResidentWorkspace.module.css'
import { saveFlash, takeFlash } from './flash'

const FLASH = 'perfil-atualizado'
type Account = { nome: string; email: string; telefone: string | null }

export function ProfilePage() {
  const { client, snapshot } = useAuth()
  const [passwordError, setPasswordError] = useState('')
  const [passwordPending, setPasswordPending] = useState(false)
  const [account, setAccount] = useState<Account>()
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(() => takeFlash(FLASH))
  const [pending, setPending] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    client.http
      .get<Account>('/contas/me', { signal: controller.signal })
      .then(({ data }) => setAccount(data))
      .catch(() => {
        if (!controller.signal.aborted) setError('Não foi possível carregar seus dados.')
      })
    return () => controller.abort()
  }, [client])
  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (passwordPending) return
    const form = event.currentTarget
    const data = new FormData(form)
    const next = String(data.get('senha_nova') ?? '')
    const problem = passwordRuleError(
      next,
      String(data.get('confirmacao') ?? ''),
      snapshot.identity?.usuario.email,
    )
    if (problem) {
      setPasswordError(problem)
      return
    }
    setPasswordError('')
    setSuccess('')
    setPasswordPending(true)
    try {
      await client.changePassword(String(data.get('senha_atual') ?? ''), next, () =>
        saveFlash(FLASH, 'Senha alterada. Os outros acessos à sua conta foram encerrados.'),
      )
      form.reset()
      setSuccess('Senha alterada. Os outros acessos à sua conta foram encerrados.')
    } catch (failure) {
      setPasswordError(changePasswordError(failure))
    } finally {
      setPasswordPending(false)
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!account || pending) return
    setError('')
    setSuccess('')
    setPending(true)
    try {
      await client.http.put('/contas/me', {
        nome: account.nome.trim(),
        email: account.email.trim(),
        telefone: account.telefone ?? '',
      })
      setSuccess('Perfil atualizado.')
      saveFlash(FLASH, 'Perfil atualizado.')
      await client.restore()
    } catch (failure) {
      const message = isAxiosError<{ error?: { message?: string } }>(failure)
        ? failure.response?.data?.error?.message
        : undefined
      setError(message ?? 'Não foi possível salvar seu perfil.')
    } finally {
      setPending(false)
    }
  }
  return (
    <Page className={styles.content}>
      <Heading level={1}>Meu perfil</Heading>
      <Card className={styles.content}>
        {error && (
          <Notice tone="alert" role="alert">
            {error}
          </Notice>
        )}
        {success && (
          <Notice tone="success" role="status">
            {success}
          </Notice>
        )}
        {account && (
          <form className={styles.form} onSubmit={(event) => void submit(event)}>
            <Input
              label="Nome"
              value={account.nome}
              required
              maxLength={120}
              disabled={pending}
              onChange={(event) => setAccount({ ...account, nome: event.target.value })}
            />
            <Input
              label="E-mail"
              type="email"
              value={account.email}
              required
              maxLength={254}
              disabled={pending}
              onChange={(event) => setAccount({ ...account, email: event.target.value })}
            />
            <Input
              label="Telefone"
              type="tel"
              value={account.telefone ?? ''}
              required
              maxLength={16}
              disabled={pending}
              onChange={(event) => setAccount({ ...account, telefone: event.target.value })}
            />
            <div>
              <Button type="submit" loading={pending}>
                Salvar perfil
              </Button>
            </div>
          </form>
        )}
      </Card>
      <Card className={styles.content}>
        <Heading level={2} size="md">
          Trocar senha
        </Heading>
        <form className={styles.form} onSubmit={(event) => void changePassword(event)}>
          <Input
            label="Senha atual"
            name="senha_atual"
            type="password"
            autoComplete="current-password"
            required
            maxLength={128}
            disabled={passwordPending}
          />
          <Input
            label="Nova senha"
            name="senha_nova"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            maxLength={128}
            hint={passwordHint}
            disabled={passwordPending}
          />
          <Input
            label="Confirmar nova senha"
            name="confirmacao"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            maxLength={128}
            disabled={passwordPending}
          />
          {passwordError && (
            <Notice tone="alert" role="alert">
              {passwordError}
            </Notice>
          )}
          <div>
            <Button type="submit" loading={passwordPending}>
              Trocar senha
            </Button>
          </div>
        </form>
      </Card>
      <ButtonLink to="/app" variant="secondary">
        Voltar à minha área
      </ButtonLink>
    </Page>
  )
}
