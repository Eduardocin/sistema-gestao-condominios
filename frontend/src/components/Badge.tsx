import type { ComponentProps } from 'react'
import { cx } from '../utils/cx'
import styles from './Badge.module.css'

export type BadgeVariant = 'success' | 'alert' | 'warning' | 'primary' | 'neutral'

export interface BadgeProps extends ComponentProps<'span'> {
  variant?: BadgeVariant
}

export function Badge({ variant = 'neutral', className, children, ...props }: BadgeProps) {
  return (
    <span className={cx(styles.badge, styles[variant], className)} {...props}>
      {children}
    </span>
  )
}
