import { Link } from 'react-router'
import { Badge, Button, Card, Heading, Input, Page, PublicFooter, PublicHeader, Text } from '../../components'
import styles from './AccessPage.module.css'

export function AccessPage({ mode }: { mode: 'login' | 'cadastro' }) {
  const isLogin = mode === 'login'
  return (
    <>
      <PublicHeader />
      <Page id="conteudo" tabIndex={-1} className={styles.page}>
        <div className={styles.intro}>
          <Badge variant="warning">Disponível em breve</Badge>
          <Heading level={1}>{isLogin ? 'Seu condomínio mais perto.' : 'O primeiro passo para uma rotina mais organizada.'}</Heading>
          <Text tone="secondary">{isLogin ? 'Em breve, acesse sua conta e acompanhe a rotina do seu condomínio.' : 'Em breve, crie sua conta para conectar sua rotina à gestão do condomínio.'}</Text>
        </div>
        <Card>
          <Heading level={2} size="md">{isLogin ? 'Entrar na sua conta' : 'Criar sua conta'}</Heading>
          <Text size="sm" tone="secondary" id="aviso-previa">Os campos estão desabilitados. Nenhum dado é enviado ou armazenado nesta prévia.</Text>
          <form onSubmit={(event) => event.preventDefault()} aria-describedby="aviso-previa">
            <fieldset disabled className={styles.fields}>
              <legend className={styles.legend}>Prévia do formulário de {isLogin ? 'acesso' : 'cadastro'}</legend>
              {!isLogin && <Input label="Nome completo" autoComplete="off" placeholder="Seu nome" />}
              <Input label="E-mail" type="email" autoComplete="off" placeholder="nome@exemplo.com" />
              <Input label="Senha" type="password" autoComplete="off" placeholder="Disponível em breve" />
              <Button type="submit" disabled>{isLogin ? 'Acesso disponível em breve' : 'Cadastro disponível em breve'}</Button>
            </fieldset>
          </form>
          <Text size="sm" className={styles.switchLink}>{isLogin ? 'Ainda não tem conta?' : 'Já tem uma conta?'} <Link to={isLogin ? '/cadastro' : '/login'}>{isLogin ? 'Conhecer o cadastro' : 'Ver a tela de acesso'}</Link></Text>
        </Card>
        <Link to="/">← Voltar à apresentação</Link>
      </Page>
      <PublicFooter />
    </>
  )
}
