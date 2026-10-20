import type { ComponentProps } from 'react'
import { cx } from '../utils/cx'
import styles from './Page.module.css'

/** Área principal de uma tela: largura máxima e respiro padrão. */
export function Page({ className, children, ...props }: ComponentProps<'main'>) {
  return (
    <main className={cx(styles.page, className)} {...props}>
      {children}
    </main>
  )
}
