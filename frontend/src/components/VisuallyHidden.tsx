import type { ComponentProps } from 'react'
import { cx } from '../utils/cx'
import styles from './VisuallyHidden.module.css'

/** Texto que só leitores de tela percebem (rótulos extras, estados sem cor). */
export function VisuallyHidden({ className, ...props }: ComponentProps<'span'>) {
  return <span className={cx(styles.hidden, className)} {...props} />
}
