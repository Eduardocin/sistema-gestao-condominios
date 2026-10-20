import type { ComponentProps } from 'react'
import { Link } from 'react-router'
import type { ButtonSize, ButtonVariant } from './Button'
import { cx } from '../utils/cx'
import styles from './Button.module.css'

export interface ButtonLinkProps extends ComponentProps<typeof Link> {
  variant?: ButtonVariant
  size?: ButtonSize
}

/** Navegação com a aparência do Button e a semântica de um link. */
export function ButtonLink({ variant = 'primary', size = 'md', className, ...props }: ButtonLinkProps) {
  return <Link className={cx(styles.button, styles[variant], styles[size], className)} {...props} />
}
