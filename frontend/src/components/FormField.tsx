import type { ReactNode } from 'react'
import { cx } from '../utils/cx'
import styles from './FormField.module.css'

interface FormFieldProps {
  id: string
  label: string
  required?: boolean
  hint?: string
  hintId?: string
  error?: string
  errorId?: string
  className?: string
  children: ReactNode
}

/** Estrutura comum de campo: label, controle, dica e erro. Usada por Input e Select. */
export function FormField({
  id,
  label,
  required,
  hint,
  hintId,
  error,
  errorId,
  className,
  children,
}: FormFieldProps) {
  return (
    <div className={cx(styles.field, className)}>
      <label htmlFor={id} className={styles.label}>
        {label}
        {required && (
          <span className={styles.required} aria-hidden="true">
            {' '}
            *
          </span>
        )}
      </label>
      {children}
      {hint && (
        <p id={hintId} className={styles.hint}>
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className={styles.error}>
          {error}
        </p>
      )}
    </div>
  )
}
