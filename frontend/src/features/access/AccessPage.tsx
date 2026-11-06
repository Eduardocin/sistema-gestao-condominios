import { Link } from 'react-router'
import { Badge, Button, Card, Heading, Input, Page, PublicFooter, PublicHeader, Text } from '../../components'
import styles from './AccessPage.module.css'

export function AccessPage() {
  return (
    <>
      <PublicHeader />
      <Page id="conteudo" tabIndex={-1} className={styles.page}>
        <div className={styles.intro}>
          <Badge variant="warning">Disponível em breve</Badge>
          <Heading level={1}>O primeiro passo para uma rotina mais organizada.</Heading>
          <Text tone="secondary">Em breve, crie sua conta para conectar sua rotina à gestão do condomínio.</Text>
        </div>
        <Card>
          <Heading level={2} size="md">Criar sua conta</Heading>
          <Text size="sm" tone="secondary" id="aviso-previa">Os campos estão desabilitados. Nenhum dado é enviado ou armazenado nesta prévia.</Text>
          <form onSubmit={(event) => event.preventDefault()} aria-describedby="aviso-previa">
            <fieldset disabled className={styles.fields}>
              <legend className={styles.legend}>Prévia do formulário de cadastro</legend>
              <Input label="Nome completo" autoComplete="off" placeholder="Seu nome" />
              <Input label="E-mail" type="email" autoComplete="off" placeholder="nome@exemplo.com" />
              <Input label="Senha" type="password" autoComplete="off" placeholder="Disponível em breve" />
              <Button type="submit" disabled>Cadastro disponível em breve</Button>
            </fieldset>
          </form>
          <Text size="sm" className={styles.switchLink}>Já tem uma conta? <Link to="/login">Entrar na sua conta</Link></Text>
        </Card>
        <Link to="/">← Voltar à apresentação</Link>
      </Page>
      <PublicFooter />
    </>
  )
}
