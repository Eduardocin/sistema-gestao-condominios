import type { ComponentProps } from 'react'
import { cx } from '../utils/cx'
import styles from './Button.module.css'

export type ButtonVariant = 'primary' | 'secondary' | 'success' | 'alert' | 'warning'
export type ButtonSize = 'sm' | 'md'

export interface ButtonProps extends ComponentProps<'button'> {
  variant?: ButtonVariant
  size?: ButtonSize
  /** Mostra um indicador de carregamento e bloqueia novos cliques. */
  loading?: boolean
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  type = 'button',
  disabled,
  className,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cx(styles.button, styles[variant], styles[size], loading && styles.loading, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {children}
    </button>
  )
}
