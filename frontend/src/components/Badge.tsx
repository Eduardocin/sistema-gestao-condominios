import React from 'react';
import './Badge.css';

interface BadgeProps {
  variant: 'success' | 'alert' | 'warning';
  children: React.ReactNode;
}

export const Badge: React.FC<BadgeProps> = ({ variant, children }) => {
  return (
    <span className={`base-badge badge-${variant}`}>
      {children}
    </span>
  );
};