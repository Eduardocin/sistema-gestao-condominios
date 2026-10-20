import React from 'react';
import './Table.css';

interface TableProps {
  headers: string[];
  rows: React.ReactNode[][];
}

export const Table: React.FC<TableProps> = ({ headers, rows }) => {
  return (
    <div className="base-table-wrapper">
      <table className="base-table">
        <thead>
          <tr>
            {headers.map((header, index) => (
              <th key={index}>{header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};