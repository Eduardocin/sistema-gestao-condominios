import type { ComponentProps } from 'react'
import { useFieldIds } from '../hooks/useFieldIds'
import { cx } from '../utils/cx'
import { FormField } from './FormField'
import styles from './FormField.module.css'

export interface SelectOption {
  value: string
  label: string
}

export interface SelectProps extends ComponentProps<'select'> {
  label: string
  options: SelectOption[]
  /** Texto da opção inicial, não selecionável. */
  placeholder?: string
  hint?: string
  error?: string
}

export function Select({
  label,
  options,
  placeholder = 'Selecione uma opção',
  hint,
  error,
  id: idProp,
  className,
  required,
  value,
  defaultValue,
  ...props
}: SelectProps) {
  const { id, hintId, errorId, describedBy, invalid } = useFieldIds(idProp, hint, error)
  // Controlado (value) ou não controlado (defaultValue): nunca os dois ao mesmo tempo.
  const valueProps = value !== undefined ? { value } : { defaultValue: defaultValue ?? '' }

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
      <select
        id={id}
        className={cx(styles.control, className)}
        required={required}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        {...valueProps}
        {...props}
      >
        <option value="" disabled>
          {placeholder}
        </option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </FormField>
  )
}
