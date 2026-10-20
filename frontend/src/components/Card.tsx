import type { ComponentProps } from 'react'
import { cx } from '../utils/cx'
import styles from './Card.module.css'

export function Card({ className, children, ...props }: ComponentProps<'div'>) {
  return (
    <div className={cx(styles.card, className)} {...props}>
      {children}
    </div>
  )
}
