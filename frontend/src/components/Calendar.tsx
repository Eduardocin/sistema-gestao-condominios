import { useEffect, useId, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { cx } from '../utils/cx'
import styles from './Calendar.module.css'

export interface CalendarProps {
  /** Data selecionada. */
  value?: Date | null
  onChange?: (date: Date) => void
  /** Datas fora do intervalo ficam desabilitadas. */
  min?: Date
  max?: Date
  locale?: string
  className?: string
}

const startOfDay = (date: Date) => new Date(date.getFullYear(), date.getMonth(), date.getDate())
const addDays = (date: Date, amount: number) =>
  new Date(date.getFullYear(), date.getMonth(), date.getDate() + amount)
const daysInMonth = (year: number, month: number) => new Date(year, month + 1, 0).getDate()
const pad = (value: number) => String(value).padStart(2, '0')
const keyOf = (date: Date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`

/** Move para outro mês mantendo o dia, quando existir (31 de janeiro -> 28 de fevereiro). */
function shiftMonth(date: Date, amount: number) {
  const target = new Date(date.getFullYear(), date.getMonth() + amount, 1)
  const day = Math.min(date.getDate(), daysInMonth(target.getFullYear(), target.getMonth()))
  return new Date(target.getFullYear(), target.getMonth(), day)
}

export function Calendar({ value, onChange, min, max, locale = 'pt-BR', className }: CalendarProps) {
  const titleId = useId()
  const gridRef = useRef<HTMLTableElement>(null)
  const moveFocus = useRef(false)
  const today = startOfDay(new Date())
  // A data com foco define também o mês exibido
  const [focusDate, setFocusDate] = useState(() => startOfDay(value ?? new Date()))

  const year = focusDate.getFullYear()
  const month = focusDate.getMonth()
  const minTime = min ? startOfDay(min).getTime() : -Infinity
  const maxTime = max ? startOfDay(max).getTime() : Infinity
  const isDisabled = (date: Date) => date.getTime() < minTime || date.getTime() > maxTime

  useEffect(() => {
    if (!moveFocus.current) return
    moveFocus.current = false
    gridRef.current?.querySelector<HTMLButtonElement>(`[data-date="${keyOf(focusDate)}"]`)?.focus()
  }, [focusDate])

  const monthTitle = new Intl.DateTimeFormat(locale, { month: 'long', year: 'numeric' }).format(focusDate)
  // 2023-01-01 foi um domingo: serve de base para os nomes dos dias da semana
  const weekdays = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(2023, 0, 1 + index)
    return {
      short: new Intl.DateTimeFormat(locale, { weekday: 'short' }).format(date),
      long: new Intl.DateTimeFormat(locale, { weekday: 'long' }).format(date),
    }
  })
  const fullDate = new Intl.DateTimeFormat(locale, { dateStyle: 'full' })

  const leading = new Date(year, month, 1).getDay()
  const cells: Array<Date | null> = [
    ...Array<null>(leading).fill(null),
    ...Array.from({ length: daysInMonth(year, month) }, (_, index) => new Date(year, month, index + 1)),
  ]
  while (cells.length % 7 !== 0) cells.push(null)
  const weeks = Array.from({ length: cells.length / 7 }, (_, index) => cells.slice(index * 7, index * 7 + 7))

  function goTo(date: Date, focus: boolean) {
    if (isDisabled(date)) return
    moveFocus.current = focus
    setFocusDate(date)
  }

  function handleKeyDown(event: KeyboardEvent) {
    const moves: Record<string, Date> = {
      ArrowLeft: addDays(focusDate, -1),
      ArrowRight: addDays(focusDate, 1),
      ArrowUp: addDays(focusDate, -7),
      ArrowDown: addDays(focusDate, 7),
      Home: addDays(focusDate, -focusDate.getDay()),
      End: addDays(focusDate, 6 - focusDate.getDay()),
      PageUp: shiftMonth(focusDate, -1),
      PageDown: shiftMonth(focusDate, 1),
    }
    const next = moves[event.key]
    if (!next) return
    event.preventDefault()
    goTo(next, true)
  }

  return (
    <div className={cx(styles.calendar, className)}>
      <div className={styles.header}>
        <button
          type="button"
          className={styles.nav}
          aria-label="Mês anterior"
          onClick={() => goTo(shiftMonth(focusDate, -1), false)}
        >
          <span aria-hidden="true">&lsaquo;</span>
        </button>
        <p id={titleId} className={styles.title} aria-live="polite">
          {monthTitle}
        </p>
        <button
          type="button"
          className={styles.nav}
          aria-label="Próximo mês"
          onClick={() => goTo(shiftMonth(focusDate, 1), false)}
        >
          <span aria-hidden="true">&rsaquo;</span>
        </button>
      </div>
      <table ref={gridRef} className={styles.grid} aria-labelledby={titleId} onKeyDown={handleKeyDown}>
        <thead>
          <tr>
            {weekdays.map((day) => (
              <th key={day.long} scope="col" abbr={day.long}>
                {day.short}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {weeks.map((week, weekIndex) => (
            <tr key={weekIndex}>
              {week.map((date, dayIndex) => (
                <td key={dayIndex}>
                  {date && (
                    <button
                      type="button"
                      className={cx(
                        styles.day,
                        value && keyOf(value) === keyOf(date) && styles.selected,
                        keyOf(today) === keyOf(date) && styles.today,
                      )}
                      data-date={keyOf(date)}
                      tabIndex={keyOf(date) === keyOf(focusDate) ? 0 : -1}
                      disabled={isDisabled(date)}
                      aria-label={fullDate.format(date)}
                      aria-pressed={value ? keyOf(value) === keyOf(date) : false}
                      aria-current={keyOf(today) === keyOf(date) ? 'date' : undefined}
                      onClick={() => {
                        setFocusDate(date)
                        onChange?.(date)
                      }}
                    >
                      {date.getDate()}
                    </button>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
