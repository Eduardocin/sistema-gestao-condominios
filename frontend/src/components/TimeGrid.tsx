import { cx } from '../utils/cx'
import styles from './TimeGrid.module.css'

export type SlotStatus = 'free' | 'own' | 'other'

export interface TimeSlotData {
  time: string
  status: SlotStatus
}

export interface TimeGridProps {
  slots: TimeSlotData[]
  /** Nome do grupo, anunciado por leitores de tela (ex.: "Horários da quadra"). */
  label: string
  /** Horário já marcado pela própria pessoa pode ser clicado para cancelar. */
  onSlotClick?: (time: string, status: SlotStatus) => void
  className?: string
}

// O estado aparece também em texto: cor sozinha não basta (daltonismo, leitor de tela).
const statusLabel: Record<SlotStatus, string> = {
  free: 'Livre',
  own: 'Sua reserva',
  other: 'Ocupado',
}

export function TimeGrid({ slots, label, onSlotClick, className }: TimeGridProps) {
  return (
    <div role="group" aria-label={label} className={cx(styles.grid, className)}>
      {slots.map((slot) => (
        <button
          key={slot.time}
          type="button"
          className={cx(styles.slot, styles[slot.status])}
          disabled={slot.status === 'other'}
          aria-pressed={slot.status === 'free' ? false : slot.status === 'own' ? true : undefined}
          onClick={() => onSlotClick?.(slot.time, slot.status)}
        >
          <span className={styles.time}>{slot.time}</span>
          <span className={styles.caption}>{statusLabel[slot.status]}</span>
        </button>
      ))}
    </div>
  )
}
