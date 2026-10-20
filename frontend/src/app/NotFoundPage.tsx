import { Link } from 'react-router'
import { Heading, Page, Text } from '../components'

export function NotFoundPage() {
  return (
    <Page>
      <Text size="sm" tone="secondary">
        404
      </Text>
      <Heading level={1}>Página não encontrada</Heading>
      <Text>O endereço que você acessou não existe.</Text>
      <Link to="/">Voltar ao início</Link>
    </Page>
  )
}
