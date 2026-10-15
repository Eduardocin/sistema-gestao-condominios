import { Link } from 'react-router'

export function NotFoundPage() {
  return (
    <main className="shell">
      <p className="eyebrow">404</p>
      <h1>Página não encontrada</h1>
      <p>O endereço que você acessou não existe.</p>
      <Link to="/">Voltar ao início</Link>
    </main>
  )
}
