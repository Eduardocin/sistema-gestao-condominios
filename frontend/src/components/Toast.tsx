import { useEffect, useRef } from 'react'
import { cx } from '../utils/cx'
import styles from './Toast.module.css'

export type ToastVariant = 'success' | 'alert' | 'warning' | 'primary'

export interface ToastProps {
  message: string
  variant?: ToastVariant
  isVisible: boolean
  onClose: () => void
  /** Tempo até sumir, em milissegundos. Use 0 para só fechar pelo botão. */
  duration?: number
}

export function Toast({ message, variant = 'success', isVisible, onClose, duration = 6000 }: ToastProps) {
  // Guarda o onClose mais recente sem reiniciar o temporizador a cada render do pai
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  })

  useEffect(() => {
    if (!isVisible || duration <= 0) return
    const timer = setTimeout(() => onCloseRef.current(), duration)
    return () => clearTimeout(timer)
  }, [isVisible, duration])

  // O contêiner fica sempre na página: leitores de tela só anunciam
  // mudanças em regiões ao vivo que já existiam antes do conteúdo aparecer.
  return (
    <div
      className={styles.container}
      aria-live={variant === 'alert' ? 'assertive' : 'polite'}
      aria-atomic="true"
    >
      {isVisible && (
        <div className={cx(styles.toast, styles[variant])}>
          <span className={styles.message}>{message}</span>
          <button type="button" className={styles.close} onClick={onClose} aria-label="Fechar aviso">
            <span aria-hidden="true">&times;</span>
          </button>
        </div>
      )}
    </div>
  )
}
