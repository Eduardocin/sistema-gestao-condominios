import type { ComponentProps } from 'react'
import { cx } from '../utils/cx'
import styles from './Badge.module.css'

export type BadgeVariant = 'success' | 'alert' | 'warning' | 'primary' | 'neutral'

export interface BadgeProps extends ComponentProps<'span'> {
  variant?: BadgeVariant
  wrap?: boolean
}

export function Badge({ variant = 'neutral', wrap = false, className, children, ...props }: BadgeProps) {
  return (
    <span className={cx(styles.badge, styles[variant], wrap && styles.wrap, className)} {...props}>
      {children}
    </span>
  )
}
