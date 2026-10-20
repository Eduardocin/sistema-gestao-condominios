import type { ComponentProps } from 'react'
import { cx } from '../utils/cx'
import styles from './Text.module.css'

export interface TextProps extends ComponentProps<'p'> {
  /** Elemento HTML a renderizar. */
  as?: 'p' | 'span' | 'div'
  size?: 'md' | 'sm' | 'xs'
  tone?: 'main' | 'secondary'
}

export function Text({ as: Tag = 'p', size = 'md', tone = 'main', className, children, ...props }: TextProps) {
  return (
    <Tag className={cx(styles.text, styles[size], styles[tone], className)} {...props}>
      {children}
    </Tag>
  )
}
