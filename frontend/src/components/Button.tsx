/*
 * Componente Base: Button
 * Botão reutilizável que aplica as cores do Design System.
 * Aceita as variantes: 'primary', 'success', 'alert' e 'warning'.
 * Repassa automaticamente eventos HTML nativos, como onClick e disabled.
 */
import React from 'react';
import './Button.css';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'success' | 'alert' | 'warning';
}

export const Button: React.FC<ButtonProps> = ({ 
  variant = 'primary', 
  children, 
  ...props 
}) => {
  return (
    <button className={`base-button variant-${variant}`} {...props}>
      {children}
    </button>
  );
};