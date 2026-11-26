import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { isAxiosError } from 'axios'
import { Button, ButtonLink, Card, Heading, Input, Notice, Page, Text } from '../../components'
import { useAuth } from '../auth/context'
import { AccessDenied } from '../auth/SessionPages'
import styles from '../resident/ResidentWorkspace.module.css'

type Draft = {
  nome: string
  cnpj: string
  cep: string
  logradouro: string
  numero: string
  complemento: string
  bairro: string
  cidade: string
  uf: string
  bloco: string
  andares: number
  unidadesPorAndar: number
}

const empty: Draft = {
  nome: '',
  cnpj: '',
  cep: '',
  logradouro: '',
  numero: '',
  complemento: '',
  bairro: '',
  cidade: '',
  uf: '',
  bloco: '',
  andares: 1,
  unidadesPorAndar: 1,
}
const labels: { key: keyof Draft; label: string; maxLength?: number }[] = [
  { key: 'nome', label: 'Nome do condomínio', maxLength: 120 },
  { key: 'cnpj', label: 'CNPJ', maxLength: 18 },
  { key: 'cep', label: 'CEP', maxLength: 9 },
  { key: 'logradouro', label: 'Logradouro', maxLength: 150 },
  { key: 'numero', label: 'Número', maxLength: 20 },
  { key: 'complemento', label: 'Complemento', maxLength: 80 },
  { key: 'bairro', label: 'Bairro', maxLength: 80 },
  { key: 'cidade', label: 'Cidade', maxLength: 80 },
  { key: 'uf', label: 'UF', maxLength: 2 },
]

export function CondominiumWizard() {
  const { snapshot, client } = useAuth()
  const identity = snapshot.identity
  const storageKey = `condominio-rascunho:${identity?.usuario.id ?? ''}`
  const [draft, setDraft] = useState<Draft>(() => {
    try {
      return { ...empty, ...JSON.parse(sessionStorage.getItem(storageKey) ?? '{}') }
    } catch {
      return empty
    }
  })
  const [step, setStep] = useState(1)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [pending, setPending] = useState(false)
  const submitting = useRef(false)
  if (
    !identity ||
    identity.administrador_plataforma ||
    (identity.condominio && identity.condominio.perfil !== 'administracao')
  )
    return <AccessDenied />

  function update(next: Draft) {
    setDraft(next)
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(next))
    } catch {
      /* Storage may be unavailable. */
    }
  }

  const blockNames = draft.bloco
    .split(',')
    .map((name) => name.trim())
    .filter(Boolean)
  const invalidBlocks =
    blockNames.length < 1 ||
    blockNames.length > 20 ||
    new Set(blockNames).size !== blockNames.length ||
    blockNames.some((name) => name.length > 50)
  const unitCount = blockNames.length * draft.andares * draft.unidadesPorAndar
  const floors = Array.from({ length: Math.min(Math.max(draft.andares, 0), 100) }, (_, index) => ({
    nome: `${index + 1}º andar`,
    ordem: index + 1,
    unidades: Array.from(
      { length: Math.min(Math.max(draft.unidadesPorAndar, 0), 60) },
      (_, unit) => `${index + 1}${String(unit + 1).padStart(2, '0')}`,
    ),
  }))

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting.current) return
    setError('')
    if (step < 3) {
      setStep(step + 1)
      return
    }
    submitting.current = true
    setPending(true)
    try {
      await client.http.post('/condominios', {
        nome: draft.nome.trim(),
        cnpj: draft.cnpj.replace(/\D/g, ''),
        endereco: {
          cep: draft.cep.replace(/\D/g, ''),
          logradouro: draft.logradouro.trim(),
          numero: draft.numero.trim(),
          complemento: draft.complemento.trim() || null,
          bairro: draft.bairro.trim(),
          cidade: draft.cidade.trim(),
          uf: draft.uf.trim().toUpperCase(),
        },
        blocos: blockNames.map((nome) => ({ nome, andares: floors })),
      })
      try {
        sessionStorage.removeItem(storageKey)
      } catch {
        /* The registration is already saved. */
      }
      setSuccess('Cadastro enviado para análise. Acompanhe a aprovação na sua conta.')
    } catch (failure) {
      const message = isAxiosError<{ error?: { message?: string } }>(failure)
        ? failure.response?.data?.error?.message
        : undefined
      setError(message || 'Não foi possível enviar o cadastro. Confira os dados e tente novamente.')
    } finally {
      submitting.current = false
      setPending(false)
    }
  }

  return (
    <Page className={styles.content}>
      <Heading level={1}>Cadastrar condomínio</Heading>
      {success ? (
        <Notice tone="success" role="status">
          {success}
        </Notice>
      ) : (
        <Card>
          <form className={styles.form} onSubmit={(event) => void submit(event)}>
            <Text>Etapa {step} de 3</Text>
            {step === 1 &&
              labels.map(({ key, label, maxLength }) => (
                <Input
                  key={key}
                  label={label}
                  value={String(draft[key])}
                  required={key !== 'complemento'}
                  maxLength={maxLength}
                  onChange={(event) => update({ ...draft, [key]: event.target.value })}
                />
              ))}
            {step === 2 && (
              <>
                <Input
                  label="Blocos separados por vírgula"
                  required
                  maxLength={500}
                  value={draft.bloco}
                  onChange={(event) => update({ ...draft, bloco: event.target.value })}
                />
                <Input
                  label="Quantidade de andares"
                  required
                  type="number"
                  min={1}
                  max={100}
                  value={draft.andares}
                  onChange={(event) => update({ ...draft, andares: Number(event.target.value) })}
                />
                <Input
                  label="Unidades por andar"
                  required
                  type="number"
                  min={1}
                  max={60}
                  value={draft.unidadesPorAndar}
                  onChange={(event) =>
                    update({ ...draft, unidadesPorAndar: Number(event.target.value) })
                  }
                />
                <Text>Até 2.000 unidades por condomínio.</Text>
                {unitCount > 2000 && <Notice tone="alert">Reduza o total de unidades.</Notice>}
                {invalidBlocks && draft.bloco && (
                  <Notice tone="alert">
                    Informe até 20 blocos com nomes diferentes e no máximo 50 caracteres cada.
                  </Notice>
                )}
              </>
            )}
            {step === 3 && (
              <>
                <Heading level={2}>Confira os dados</Heading>
                <Text>
                  {draft.nome} · CNPJ {draft.cnpj}
                </Text>
                <Text>
                  {draft.logradouro}, {draft.numero} · {draft.bairro}, {draft.cidade} / {draft.uf}
                </Text>
                <Text>
                  {blockNames.length} blocos · {unitCount} unidades
                </Text>
                {blockNames.map((block) => (
                  <section key={block}>
                    <Heading level={3}>{block}</Heading>
                    {floors.map((floor) => (
                      <Text key={floor.ordem}>
                        {floor.nome} · {floor.unidades.join(', ')}
                      </Text>
                    ))}
                  </section>
                ))}
              </>
            )}
            {error && (
              <Notice tone="alert" role="alert">
                {error}
              </Notice>
            )}
            <div className={styles.actions}>
              {step > 1 && (
                <Button variant="secondary" disabled={pending} onClick={() => setStep(step - 1)}>
                  Voltar
                </Button>
              )}
              <Button
                type="submit"
                loading={pending}
                disabled={step === 2 && (unitCount > 2000 || invalidBlocks)}
              >
                {step === 3 ? 'Enviar cadastro' : 'Continuar'}
              </Button>
            </div>
          </form>
        </Card>
      )}
      <ButtonLink to="/app" variant="secondary">
        Voltar à minha área
      </ButtonLink>
    </Page>
  )
}
