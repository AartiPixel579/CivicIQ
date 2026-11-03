'use client';

import React from 'react';
import { HardHat, Stethoscope, HeartHandshake, Building2 } from 'lucide-react';

export const DepartmentSelector = ({
  departments = [],
  selectedDeptId,
  onSelectDepartment,
}) => {
  const getDeptIcon = (id) => {
    switch (id) {
      case 'engineering':
        return <HardHat className="h-4 w-4 text-blue-400" />;
      case 'healthcare':
        return <Stethoscope className="h-4 w-4 text-emerald-400" />;
      case 'animal_shelter':
        return <HeartHandshake className="h-4 w-4 text-amber-400" />;
      default:
        return <Building2 className="h-4 w-4 text-slate-300" />;
    }
  };

  return (
    <div className="flex items-center space-x-1.5 p-1 bg-blue-950/40 rounded-xl border border-blue-700/50">
      {departments.map((dept) => {
        const isSelected = dept.id === selectedDeptId;
        const isActive = dept.active !== false && dept.id === 'engineering';

        return (
          <button
            key={dept.id}
            onClick={() => onSelectDepartment(dept.id)}
            className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              isSelected
                ? 'bg-blue-600 text-white shadow-sm ring-1 ring-blue-400/40'
                : 'text-blue-200 hover:bg-blue-800/50 hover:text-white'
            }`}
          >
            {getDeptIcon(dept.id)}
            <span>{dept.short_name}</span>
            {isActive ? (
              <span className="text-[9px] bg-emerald-400/20 text-emerald-300 px-1.5 py-0.2 rounded-full font-bold">
                MVP
              </span>
            ) : (
              <span className="text-[9px] bg-slate-700 text-slate-300 px-1 py-0.2 rounded-full font-normal">
                Soon
              </span>
            )}
            {isSelected && <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />}
          </button>
        );
      })}
    </div>
  );
};
