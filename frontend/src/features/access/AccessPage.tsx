import { Link } from 'react-router'
import { Badge, ButtonLink, Card, Heading, Page, PublicFooter, PublicHeader, Text } from '../../components'
import styles from './AccessPage.module.css'

export function AccessPage() {
  return (
    <>
      <PublicHeader />
      <Page id="conteudo" tabIndex={-1} className={styles.page}>
        <div className={styles.intro}>
          <Badge variant="primary">Criar conta</Badge>
          <Heading level={1}>O primeiro passo para uma rotina mais organizada.</Heading>
          <Text tone="secondary">Escolha como você vai usar a gestão do condomínio.</Text>
        </div>
        <Card>
          <Heading level={2} size="md">Sou morador</Heading>
          <Text tone="secondary">Crie sua conta pessoal para acompanhar a rotina do seu condomínio.</Text>
          <ButtonLink to="/cadastro/morador">Cadastrar como morador</ButtonLink>
        </Card>
        <Card><Heading level={2} size="md">Sou da Administração</Heading><Text tone="secondary">Crie uma conta para administrar condomínios. Tenha seu CPF ou CNPJ em mãos.</Text><ButtonLink to="/cadastro/administracao" variant="secondary">Cadastrar Administração</ButtonLink></Card>
        <Text size="sm">Já tem uma conta? <Link to="/login">Entrar na sua conta</Link></Text>
        <Link to="/">← Voltar à apresentação</Link>
      </Page>
      <PublicFooter />
    </>
  )
}
