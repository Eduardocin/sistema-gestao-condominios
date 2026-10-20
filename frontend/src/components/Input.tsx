import type { ComponentProps } from 'react'
import { useFieldIds } from '../hooks/useFieldIds'
import { cx } from '../utils/cx'
import { FormField } from './FormField'
import styles from './FormField.module.css'

export interface InputProps extends ComponentProps<'input'> {
  /** Obrigatório: todo campo precisa de um rótulo visível. */
  label: string
  /** Texto de apoio abaixo do campo. */
  hint?: string
  /** Mensagem de erro; também marca o campo como inválido. */
  error?: string
}

export function Input({ label, hint, error, id: idProp, className, required, ...props }: InputProps) {
  const { id, hintId, errorId, describedBy, invalid } = useFieldIds(idProp, hint, error)

  return (
    <FormField
      id={id}
      label={label}
      required={required}
      hint={hint}
      hintId={hintId}
      error={error}
      errorId={errorId}
    >
      <input
        id={id}
        className={cx(styles.control, className)}
        required={required}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        {...props}
      />
    </FormField>
  )
}
