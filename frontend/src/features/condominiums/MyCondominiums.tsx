import { useEffect, useState } from 'react'
import { ButtonLink, Card, Heading, Notice, Text } from '../../components'
import { useAuth } from '../auth/context'
import styles from '../resident/ResidentWorkspace.module.css'

interface Account {
  tipo_cadastro: 'morador' | 'administracao' | null
}
interface Condominium {
  id: string
  nome: string
  status: 'pendente' | 'ativo' | 'rejeitado' | 'desativado'
}

const statusLabel: Record<Condominium['status'], string> = {
  pendente: 'Em análise',
  ativo: 'Aprovado',
  rejeitado: 'Rejeitado',
  desativado: 'Desativado',
}

export function MyCondominiums() {
  const { client } = useAuth()
  const [data, setData] = useState<Condominium[] | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    client.http
      .get<Account>('/contas/me', { signal: controller.signal })
      .then(async ({ data }) => {
        if (data.tipo_cadastro !== 'administracao') return
        const response = await client.http.get<Condominium[]>('/condominios/meus', {
          signal: controller.signal,
        })
        if (!controller.signal.aborted) setData(response.data)
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(true)
      })
    return () => controller.abort()
  }, [client])

  if (error) return <Notice tone="alert">Não foi possível carregar seus condomínios.</Notice>
  if (!data) return null
  return (
    <Card className={styles.content}>
      <Heading level={2} size="md">
        Meus condomínios
      </Heading>
      {data.length === 0 ? (
        <Text>Você ainda não cadastrou um condomínio.</Text>
      ) : (
        data.map((item) => (
          <Text key={item.id}>
            {item.nome} · {statusLabel[item.status]}
          </Text>
        ))
      )}
      <div>
        <ButtonLink to="/app/cadastrar-condominio">Cadastrar condomínio</ButtonLink>
      </div>
    </Card>
  )
}
