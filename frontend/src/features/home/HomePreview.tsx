import { useId, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { Badge, Heading } from '../../components'
import { HomeIcon } from './HomeIcon'
import styles from './HomePage.module.css'

const profiles = [
  {
    id: 'morador',
    label: 'Morador',
    greeting: 'Olá, Marina',
    heading: 'Tudo em ordem por aqui',
    stats: [
      { icon: 'box', value: '03', label: 'Encomendas' },
      { icon: 'people', value: '02', label: 'Visitas hoje' },
      { icon: 'calendar', value: '01', label: 'Reserva próxima' },
    ],
    feed: 'Atividade recente',
    period: 'Hoje',
    activity: [
      {
        icon: 'box',
        title: 'Encomenda registrada',
        detail: 'Portaria · há poucos minutos',
        tone: 'warning',
        status: 'Aguardando retirada',
      },
      {
        icon: 'people',
        title: 'Visita autorizada',
        detail: 'Unidade 204 · hoje, às 14h',
        tone: 'success',
        status: 'Confirmada',
      },
    ],
  },
  {
    id: 'admin',
    label: 'Administração',
    greeting: 'Olá, equipe da administração',
    heading: 'O condomínio em um olhar',
    stats: [
      { icon: 'bell', value: '04', label: 'Avisos vigentes' },
      { icon: 'chat', value: '05', label: 'Ocorrências abertas' },
      { icon: 'calendar', value: '02', label: 'Reservas hoje' },
    ],
    feed: 'Para acompanhar',
    period: 'Hoje',
    activity: [
      {
        icon: 'chat',
        title: 'Nova ocorrência',
        detail: 'Unidade 312 · barulho após as 22h',
        tone: 'warning',
        status: 'Aberta',
      },
      {
        icon: 'bell',
        title: 'Aviso publicado',
        detail: 'Manutenção do elevador B',
        tone: 'success',
        status: 'Vigente',
      },
    ],
  },
  {
    id: 'portaria',
    label: 'Portaria',
    greeting: 'Olá, portaria',
    heading: 'Movimento do dia',
    stats: [
      { icon: 'box', value: '06', label: 'Na portaria' },
      { icon: 'people', value: '04', label: 'Visitantes dentro' },
      { icon: 'key', value: '11', label: 'Entradas hoje' },
    ],
    feed: 'Fila da portaria',
    period: 'Agora',
    activity: [
      {
        icon: 'people',
        title: 'Visitante esperado',
        detail: 'Unidade 204 · autorizado pelo morador',
        tone: 'success',
        status: 'Liberar entrada',
      },
      {
        icon: 'box',
        title: 'Entregar encomenda',
        detail: 'Unidade 101 · aguardando retirada',
        tone: 'warning',
        status: 'Pendente',
      },
    ],
  },
] as const

export function HomePreview() {
  const prefix = useId()
  const [selected, setSelected] = useState(0)
  const buttons = useRef<(HTMLButtonElement | null)[]>([])

  function handleTabKey(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next: number
    switch (event.key) {
      case 'ArrowRight':
        next = (index + 1) % profiles.length
        break
      case 'ArrowLeft':
        next = (index + profiles.length - 1) % profiles.length
        break
      case 'Home':
        next = 0
        break
      case 'End':
        next = profiles.length - 1
        break
      default:
        return
    }
    event.preventDefault()
    setSelected(next)
    buttons.current[next]?.focus()
  }

  return (
    <div className={styles.scene}>
      <div className={styles.panel} role="group" aria-labelledby={`${prefix}-title`}>
        <div className={styles.panelTop}>
          <span className={styles.lights} aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span className={styles.panelTitle} id={`${prefix}-title`}>
            Residencial Alameda · prévia ilustrativa
          </span>
        </div>
        <div className={styles.tabs} role="tablist" aria-label="Perfil da prévia">
          {profiles.map(({ id, label }, index) => (
            <button
              key={id}
              ref={(button) => {
                buttons.current[index] = button
              }}
              className={styles.tab}
              type="button"
              role="tab"
              id={`${prefix}-tab-${id}`}
              aria-controls={`${prefix}-panel-${id}`}
              aria-selected={selected === index}
              tabIndex={selected === index ? 0 : -1}
              onClick={() => setSelected(index)}
              onKeyDown={(event) => handleTabKey(event, index)}
            >
              {label}
            </button>
          ))}
        </div>
        {profiles.map((profile, index) => (
          <div
            key={profile.id}
            className={styles.panelBody}
            role="tabpanel"
            id={`${prefix}-panel-${profile.id}`}
            aria-labelledby={`${prefix}-tab-${profile.id}`}
            hidden={selected !== index}
            tabIndex={selected === index ? 0 : -1}
          >
            <p className={styles.greeting}>{profile.greeting}</p>
            <Heading level={2} className={styles.panelHeading}>
              {profile.heading}
            </Heading>
            <ul className={styles.stats}>
              {profile.stats.map(({ icon, value, label }) => (
                <li key={label} className={styles.stat}>
                  <span className={styles.statIcon}>
                    <HomeIcon name={icon} />
                  </span>
                  <strong>{value}</strong>
                  <span className={styles.statLabel}>{label}</span>
                </li>
              ))}
            </ul>
            <div className={styles.feed}>
              <div className={styles.feedHead}>
                <strong>{profile.feed}</strong>
                <span>{profile.period}</span>
              </div>
              <ul className={styles.activity}>
                {profile.activity.map(({ icon, title, detail, status, tone }) => (
                  <li key={title} className={styles.row}>
                    <span className={styles.rowIcon}>
                      <HomeIcon name={icon} />
                    </span>
                    <span className={styles.rowCopy}>
                      <strong>{title}</strong>
                      <span>{detail}</span>
                    </span>
                    <Badge variant={tone} className={styles.pill}>
                      {status}
                    </Badge>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ))}
      </div>
      <div className={styles.float} aria-hidden="true">
        <span className={styles.floatIcon}>
          <HomeIcon name="check" />
        </span>
        <span>
          <strong>Retirada confirmada</strong>
          <span className={styles.floatDetail}>Encomenda · unidade 101</span>
        </span>
      </div>
    </div>
  )
}
