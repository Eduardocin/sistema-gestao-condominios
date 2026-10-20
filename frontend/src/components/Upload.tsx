import React from 'react';
import './Upload.css';

interface UploadProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export const Upload: React.FC<UploadProps> = ({ label = 'Clique para selecionar', id, ...props }) => {
  return (
    <label htmlFor={id} className="base-upload">
      <input id={id} type="file" className="base-upload-input" {...props} />
      <div className="base-upload-text">
        <span>{label}</span> ou arraste o ficheiro para aqui
      </div>
    </label>
  );
};