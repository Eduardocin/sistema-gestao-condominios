import React from 'react';
import './TimeGrid.css';

export type SlotStatus = 'free' | 'own' | 'other';

export interface TimeSlotData {
  time: string;
  status: SlotStatus;
}

interface TimeGridProps {
  slots: TimeSlotData[];
  onSlotClick?: (time: string, status: SlotStatus) => void;
}

export const TimeGrid: React.FC<TimeGridProps> = ({ slots, onSlotClick }) => {
  return (
    <div className="time-grid-container">
      {slots.map((slot) => (
        <div
          key={slot.time}
          className={`time-slot slot-${slot.status}`}
          onClick={() => onSlotClick && onSlotClick(slot.time, slot.status)}
        >
          {slot.time}
        </div>
      ))}
    </div>
  );
};