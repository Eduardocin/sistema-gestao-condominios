import React, { useEffect } from 'react';
import './Toast.css';

interface ToastProps {
  message: string;
  variant?: 'success' | 'alert' | 'warning' | 'primary';
  isVisible: boolean;
  onClose: () => void;
}

export const Toast: React.FC<ToastProps> = ({ message, variant = 'success', isVisible, onClose }) => {
  useEffect(() => {
    if (isVisible) {
      const timer = setTimeout(() => {
        onClose();
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [isVisible, onClose]);

  if (!isVisible) return null;

  return (
    <div className="toast-container">
      <div className={`base-toast toast-${variant}`}>
        <span className="toast-message">{message}</span>
        <button className="toast-close-btn" onClick={onClose}>&times;</button>
      </div>
    </div>
  );
};