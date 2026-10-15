import { useEffect, useState } from 'react'
import { checkHealth } from './health'

type Connection = 'checking' | 'online' | 'offline'

const labels: Record<Connection, string> = {
  checking: 'Verificando conexão com a API…',
  online: 'API acessível',
  offline: 'API indisponível. Verifique se o backend está em execução.',
}

export function HomePage() {
  const [connection, setConnection] = useState<Connection>('checking')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    checkHealth(controller.signal).then(
      () => { if (!controller.signal.aborted) setConnection('online') },
      () => { if (!controller.signal.aborted) setConnection('offline') },
    )
    return () => controller.abort()
  }, [attempt])

  function retry() {
    setConnection('checking')
    setAttempt((value) => value + 1)
  }

  return (
    <main className="shell">
      <p className="eyebrow">Projeto IESI</p>
      <h1>Gestão de Condomínios</h1>
      <p className="intro">Um ponto de partida para conectar a administração e a vida em condomínio.</p>
      <section className="connection" aria-label="Conexão com o servidor">
        <h2>Ambiente de desenvolvimento</h2>
        <p role="status" className={`status ${connection}`}>
          <span className="dot" aria-hidden="true" />{labels[connection]}
        </p>
        <button onClick={retry} disabled={connection === 'checking'}>Verificar novamente</button>
      </section>
      <p className="note">Os módulos de gestão serão disponibilizados nas próximas etapas do projeto.</p>
    </main>
  )
}
