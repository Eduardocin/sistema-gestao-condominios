import { useId, useState } from 'react'
import type { ChangeEvent, ComponentProps } from 'react'
import { cx } from '../utils/cx'
import styles from './Upload.module.css'

export interface UploadProps extends Omit<ComponentProps<'input'>, 'type'> {
  /** Texto do botão de seleção. */
  label?: string
}

export function Upload({ label = 'Anexar arquivo', id: idProp, className, onChange, ...props }: UploadProps) {
  const generatedId = useId()
  const id = idProp ?? generatedId
  const [fileNames, setFileNames] = useState<string[]>([])

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    setFileNames(Array.from(event.target.files ?? [], (file) => file.name))
    onChange?.(event)
  }

  return (
    <div className={cx(styles.upload, className)}>
      {/* O input cobre a área toda (clique, arraste e teclado funcionam nativamente) */}
      <input id={id} type="file" className={styles.input} onChange={handleChange} {...props} />
      <label htmlFor={id} className={styles.text}>
        <span className={styles.action}>{label}</span> ou arraste o arquivo para cá
      </label>
      <p className={styles.files} aria-live="polite">
        {fileNames.length > 0 ? fileNames.join(', ') : 'Nenhum arquivo selecionado'}
      </p>
    </div>
  )
}
