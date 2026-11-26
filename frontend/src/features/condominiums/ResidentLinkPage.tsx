import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { isAxiosError } from 'axios'
import { useNavigate } from 'react-router'
import { Button, ButtonLink, Card, Heading, Input, Notice, Page, Text } from '../../components'
import { useAuth } from '../auth/context'
import { AccessDenied } from '../auth/SessionPages'
import styles from '../resident/ResidentWorkspace.module.css'

export function ResidentLinkPage() {
  const { snapshot, client } = useAuth()
  const navigate = useNavigate()
  const [key, setKey] = useState('')
  const [error, setError] = useState('')
  const [result, setResult] = useState('')
  const [pending, setPending] = useState(false)
  const sending = useRef(false)
  if (
    !snapshot.identity ||
    snapshot.identity.administrador_plataforma ||
    (snapshot.identity.condominio && snapshot.identity.condominio.perfil !== 'morador')
  )
    return <AccessDenied />

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (sending.current) return
    sending.current = true
    setPending(true)
    setError('')
    try {
      const { data } = await client.http.post<{
        unidade: { identificacao: string }
        condominio: { id: string; nome: string }
      }>('/vinculos/chave', { chave: key.trim() })
      setResult(
        `Vínculo criado para ${data.condominio.nome}, unidade ${data.unidade.identificacao}.`,
      )
      setKey('')
      try {
        await client.selectCondominium(data.condominio.id)
        navigate('/app/morador', { replace: true })
      } catch {
        setResult(
          `Vínculo criado para ${data.condominio.nome}, unidade ${data.unidade.identificacao}. Entre novamente para atualizar a sessão.`,
        )
      }
    } catch (failure) {
      const message = isAxiosError<{ error?: { message?: string } }>(failure)
        ? failure.response?.data?.error?.message
        : undefined
      setError(message ?? 'Não foi possível vincular a unidade. Confira a chave e tente novamente.')
    } finally {
      sending.current = false
      setPending(false)
    }
  }

  return (
    <Page className={styles.content}>
      <Heading level={1}>Vincular unidade</Heading>
      <Card className={styles.content}>
        <Text>Informe a chave fornecida pela administração do condomínio.</Text>
        {result ? (
          <>
            <Notice tone="success" role="status">
              {result}
            </Notice>
            <Text>Confira sua área para acessar o condomínio.</Text>
          </>
        ) : (
          <form className={styles.form} onSubmit={(event) => void submit(event)}>
            <Input
              label="Chave de acesso"
              required
              maxLength={64}
              autoComplete="off"
              value={key}
              disabled={pending}
              onChange={(event) => setKey(event.target.value)}
            />
            {error && (
              <Notice tone="alert" role="alert">
                {error}
              </Notice>
            )}
            <div>
              <Button type="submit" loading={pending} disabled={!key.trim()}>
                Vincular unidade
              </Button>
            </div>
          </form>
        )}
      </Card>
      <ButtonLink to="/app" variant="secondary">
        Voltar à minha área
      </ButtonLink>
    </Page>
  )
}
