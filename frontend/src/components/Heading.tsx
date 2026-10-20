import type { ComponentProps } from 'react'
import { cx } from '../utils/cx'
import styles from './Heading.module.css'

export type HeadingLevel = 1 | 2 | 3 | 4
export type HeadingSize = 'xl' | 'lg' | 'md' | 'sm'

const defaultSize: Record<HeadingLevel, HeadingSize> = { 1: 'xl', 2: 'lg', 3: 'md', 4: 'sm' }

export interface HeadingProps extends ComponentProps<'h2'> {
  /** Nível semântico (h1 a h4): define a estrutura para leitores de tela. */
  level?: HeadingLevel
  /** Tamanho visual, quando precisa diferir do padrão do nível. */
  size?: HeadingSize
}

export function Heading({ level = 2, size, className, children, ...props }: HeadingProps) {
  const Tag = `h${level}` as const
  return (
    <Tag className={cx(styles.heading, styles[size ?? defaultSize[level]], className)} {...props}>
      {children}
    </Tag>
  )
}
