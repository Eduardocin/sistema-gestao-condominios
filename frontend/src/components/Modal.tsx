import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'
import styles from './Modal.module.css'

export interface ModalProps {
  isOpen: boolean
  onClose: () => void
  title: string
  children: ReactNode
}

/**
 * Usa o <dialog> nativo: o navegador cuida de prender o foco dentro do modal,
 * fechar com Esc e devolver o foco ao botão que o abriu.
 */
export function Modal({ isOpen, onClose, title, children }: ModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const titleId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (isOpen && !dialog.open) dialog.showModal()
    if (!isOpen && dialog.open) dialog.close()
  }, [isOpen])

  return (
    <dialog
      ref={dialogRef}
      className={styles.dialog}
      aria-labelledby={titleId}
      onCancel={(event) => {
        // Esc: quem decide fechar é o estado do pai
        event.preventDefault()
        onClose()
      }}
      onClose={() => {
        if (isOpen) onClose()
      }}
      onClick={(event) => {
        // Clique no fundo escurecido (::backdrop) fecha
        if (event.target === event.currentTarget) onClose()
      }}
    >
      {isOpen && (
        <div className={styles.content}>
          <div className={styles.header}>
            <h2 id={titleId} className={styles.title}>
              {title}
            </h2>
            <button type="button" className={styles.close} onClick={onClose} aria-label="Fechar">
              <span aria-hidden="true">&times;</span>
            </button>
          </div>
          <div>{children}</div>
        </div>
      )}
    </dialog>
  )
}
