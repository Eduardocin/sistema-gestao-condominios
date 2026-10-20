import type { ReactNode } from 'react'
import { cx } from '../utils/cx'
import styles from './Table.module.css'

export interface TableProps {
  headers: string[]
  rows: ReactNode[][]
  /** Título da tabela, anunciado por leitores de tela. */
  caption?: string
  /** Texto exibido quando não há linhas. */
  emptyMessage?: string
  className?: string
}

export function Table({
  headers,
  rows,
  caption,
  emptyMessage = 'Nenhum registro encontrado.',
  className,
}: TableProps) {
  return (
    // Região rolável precisa ser focável e ter nome para quem usa só o teclado
    <div
      className={cx(styles.wrapper, className)}
      role={caption ? 'region' : undefined}
      aria-label={caption}
      tabIndex={caption ? 0 : undefined}
    >
      <table className={styles.table}>
        {caption && <caption className={styles.caption}>{caption}</caption>}
        <thead>
          <tr>
            {headers.map((header, index) => (
              <th key={index} scope="col">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={headers.length} className={styles.empty}>
                {emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex}>{cell}</td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
