'use client';

import React from 'react';
import { ArrowRight, CheckCircle, ShieldAlert, ChevronRight } from 'lucide-react';

export const FlowStepOptions = ({
  options,
  onSelectOption,
  isMandatoryPrerequisite = false,
  disabled = false,
}) => {
  if (!options || options.length === 0) return null;

  return (
    <div className="mt-3 space-y-2">
      {isMandatoryPrerequisite && (
        <div className="inline-flex items-center text-[11px] font-semibold text-amber-700 bg-amber-50 px-2.5 py-1 rounded-md border border-amber-200 mb-1">
          <ShieldAlert className="mr-1.5 h-3.5 w-3.5 text-amber-600" />
          Mandatory Statutory Prerequisite — Verified selection required under Municipal Code
        </div>
      )}

      <div className="grid grid-cols-1 gap-2">
        {options.map((opt) => (
          <button
            key={opt.id}
            onClick={() => !disabled && onSelectOption(opt.id)}
            disabled={disabled}
            className={`group flex items-center justify-between text-left p-3.5 rounded-xl border transition-all text-xs ${
              disabled
                ? 'opacity-60 bg-slate-100 border-slate-200 cursor-not-allowed'
                : 'bg-white border-blue-200/80 hover:border-blue-600 hover:bg-blue-50/50 hover:shadow-md cursor-pointer'
            }`}
          >
            <div className="pr-3">
              <div className="font-bold text-slate-900 group-hover:text-blue-900 flex items-center">
                <CheckCircle className="mr-1.5 h-3.5 w-3.5 text-blue-600 group-hover:text-blue-700 flex-shrink-0" />
                <span>{opt.label}</span>
              </div>
              {opt.description && (
                <p className="mt-0.5 text-slate-500 pl-5 text-[11px] leading-relaxed">
                  {opt.description}
                </p>
              )}
            </div>

            <div className="flex-shrink-0 p-1.5 rounded-full bg-slate-100 group-hover:bg-blue-600 group-hover:text-white text-slate-400 transition-colors">
              <ChevronRight className="h-4 w-4" />
            </div>
          </button>
        ))}
      </div>
    </div>
  );
};
