import { useEffect, useState } from 'react'
import { Button, Card, Heading, Page, Text } from '../../components'
import { cx } from '../../utils/cx'
import { checkHealth } from './health'
import styles from './StatusPage.module.css'

type Connection = 'checking' | 'online' | 'offline'

const labels: Record<Connection, string> = {
  checking: 'Verificando conexão com a API…',
  online: 'API acessível',
  offline: 'API indisponível. Verifique se o backend está em execução.',
}

export function StatusPage() {
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
    <Page id="conteudo">
      <Text size="sm" tone="secondary" className={styles.eyebrow}>Status da plataforma</Text>
      <Heading level={1}>Gestão de Condomínios</Heading>
      <Text tone="secondary" className={styles.intro}>
        Um ponto de partida para conectar a administração e a vida em condomínio.
      </Text>
      <Card className={styles.connection} role="region" aria-label="Conexão com o servidor">
        <Heading level={2} size="sm">Ambiente de desenvolvimento</Heading>
        <p role="status" className={cx(styles.status, styles[connection])}>
          <span className={styles.dot} aria-hidden="true" />{labels[connection]}
        </p>
        <Button onClick={retry} loading={connection === 'checking'}>Verificar novamente</Button>
      </Card>
      <Text size="sm" tone="secondary" className={styles.note}>
        Consulte acima a disponibilidade de conexão com a plataforma.
      </Text>
    </Page>
  )
}
