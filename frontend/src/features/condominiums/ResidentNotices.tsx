import { useEffect, useState } from 'react'
import { Card, Heading, Notice, Text } from '../../components'
import { useAuth } from '../auth/context'
import styles from '../resident/ResidentWorkspace.module.css'

interface NoticeItem {
  id: string
  titulo: string
  texto: string
  importante: boolean
}

export function ResidentNotices() {
  const { client } = useAuth()
  const [items, setItems] = useState<NoticeItem[]>([])
  const [error, setError] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    client.http
      .get<{ items: NoticeItem[] }>('/avisos/vigentes', {
        params: { page: 1, page_size: 100 },
        signal: controller.signal,
      })
      .then(({ data }) => setItems(data.items))
      .catch(() => {
        if (!controller.signal.aborted) setError(true)
      })
    return () => controller.abort()
  }, [client])
  if (error) return <Notice tone="warning">Não foi possível carregar os avisos.</Notice>
  if (!items.length) return null
  return (
    <Card className={styles.content}>
      <Heading level={2} size="md">
        Avisos do condomínio
      </Heading>
      {items.map((item) => (
        <article key={item.id} className={styles.listItem}>
          <Heading level={3} size="sm">
            {item.titulo}
          </Heading>
          <Text>{item.texto}</Text>
        </article>
      ))}
    </Card>
  )
}
