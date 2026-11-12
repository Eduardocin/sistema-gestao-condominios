import { useState } from 'react'
import { Link, Navigate } from 'react-router'
import {
  Badge,
  Button,
  Card,
  Heading,
  Input,
  Notice,
  Page,
  PublicFooter,
  PublicHeader,
  Text,
} from '../../components'
import { useAuth } from './context'
import { homePath } from './navigation'
import { SessionStatus } from './SessionPages'
import styles from './Auth.module.css'

export function RegistrationPage({ profile }: { profile: 'morador' | 'administracao' }) {
  const { snapshot, client } = useAuth()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (snapshot.status === 'loading' || snapshot.status === 'error') return <SessionStatus />
  if (snapshot.identity)
    return <Navigate to={homePath(snapshot.identity, snapshot.condominiums)} replace />
  const administration = profile === 'administracao'

  async function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending) return
    const form = event.currentTarget
    const values = new FormData(form)
    const value = (name: string) => String(values.get(name) ?? '')
    if (value('senha') !== value('confirmacao')) {
      setError('As senhas devem ser iguais.')
      return
    }
    if (value('senha').toLowerCase() === value('email').trim().toLowerCase()) {
      setError('Escolha uma senha diferente do e-mail.')
      return
    }
    setPending(true)
    setError(null)
    try {
      await client.register(profile, {
        nome: value('nome').trim(),
        email: value('email').trim().toLowerCase(),
        telefone: value('telefone').replace(/\D/g, ''),
        senha: value('senha'),
        ...(administration ? { documento: value('documento').replace(/\D/g, '') } : {}),
      })
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Não foi possível criar sua conta. Tente novamente.',
      )
    } finally {
      form.querySelectorAll<HTMLInputElement>('input[type="password"]').forEach((input) => {
        input.value = ''
      })
      setPending(false)
    }
  }

  return (
    <>
      <PublicHeader />
      <Page id="conteudo" tabIndex={-1} className={styles.access}>
        <div>
          <Badge variant="primary">{administration ? 'Administração' : 'Morador'}</Badge>
          <Heading level={1}>
            {administration
              ? 'Uma gestão mais próxima começa aqui.'
              : 'Faça parte da rotina do seu condomínio.'}
          </Heading>
          <Text tone="secondary">
            Crie sua conta. Você entrará automaticamente após o cadastro.
          </Text>
        </div>
        <Card>
          <Heading level={2} size="md">
            {administration ? 'Cadastro da Administração' : 'Cadastro de morador'}
          </Heading>
          <form onSubmit={submit} className={styles.form}>
            <Input
              label={administration ? 'Nome ou razão social' : 'Nome completo'}
              name="nome"
              autoComplete="name"
              required
              minLength={3}
              maxLength={120}
              pattern={administration ? undefined : '\\S+(?:\\s+\\S+)+'}
              hint={administration ? undefined : 'Informe nome e sobrenome.'}
              disabled={pending}
            />
            {administration && (
              <Input
                label="CPF ou CNPJ"
                name="documento"
                inputMode="numeric"
                autoComplete="off"
                required
                pattern="[0-9]{11}|[0-9]{14}"
                maxLength={14}
                hint="Somente números, 11 ou 14 dígitos."
                disabled={pending}
              />
            )}
            <Input
              label="Telefone com DDD"
              name="telefone"
              type="tel"
              autoComplete="tel-national"
              required
              pattern="[0-9]{10,11}"
              minLength={10}
              maxLength={11}
              hint="Somente números, incluindo o DDD."
              disabled={pending}
            />
            <Input
              label="E-mail"
              name="email"
              type="email"
              autoComplete="email"
              required
              maxLength={254}
              disabled={pending}
            />
            <Input
              label="Senha"
              name="senha"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              maxLength={128}
              pattern={'(?=.*\\p{L})(?=.*\\p{N}).{8,128}'}
              hint="De 8 a 128 caracteres, com pelo menos uma letra e um número."
              disabled={pending}
            />
            <Input
              label="Confirmar senha"
              name="confirmacao"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              maxLength={128}
              disabled={pending}
            />
            {error && (
              <Notice tone="alert" role="alert">
                {error}
              </Notice>
            )}
            <Button type="submit" loading={pending}>
              Criar conta
            </Button>
          </form>
          <Text size="sm" className={styles.link}>
            Já tem conta? <Link to="/login">Entrar</Link>
          </Text>
        </Card>
        <Link to="/cadastro">← Escolher outro tipo de conta</Link>
      </Page>
      <PublicFooter />
    </>
  )
}
