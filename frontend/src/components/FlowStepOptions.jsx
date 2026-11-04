'use client';

import React from 'react';
import { CheckCircle, ChevronRight } from 'lucide-react';

export const FlowStepOptions = ({
  options,
  onSelectOption,
  disabled = false,
}) => {
  if (!options || options.length === 0) return null;

  const isShortList = options.length <= 3 && options.every(o => !o.description && o.label.length < 32);

  return (
    <div className="mt-3">
      <div className={isShortList ? "flex flex-wrap gap-2" : "grid grid-cols-1 gap-2"}>
        {options.map((opt) => (
          <button
            key={opt.id}
            type="button"
            onClick={() => !disabled && onSelectOption(opt.id, opt.label)}
            disabled={disabled}
            className={`group flex items-center justify-between text-left ${
              isShortList ? 'px-4 py-2 rounded-xl' : 'p-3 rounded-xl'
            } border transition-all text-xs ${
              disabled
                ? 'opacity-60 bg-slate-100 border-slate-200 cursor-not-allowed'
                : 'bg-white border-blue-200/80 hover:border-blue-500 hover:bg-blue-50/50 hover:shadow-sm cursor-pointer'
            }`}
          >
            <div className="pr-2">
              <div className="font-semibold text-slate-900 group-hover:text-blue-900 flex items-center">
                <CheckCircle className="mr-1.5 h-3.5 w-3.5 text-blue-600 group-hover:text-blue-700 flex-shrink-0" />
                <span>{opt.label}</span>
              </div>
              {opt.description && (
                <p className="mt-0.5 text-slate-500 pl-5 text-[11px] leading-relaxed">
                  {opt.description}
                </p>
              )}
            </div>

            {!isShortList && (
              <div className="flex-shrink-0 p-1 rounded-full bg-slate-100 group-hover:bg-blue-600 group-hover:text-white text-slate-400 transition-colors">
                <ChevronRight className="h-4 w-4" />
              </div>
            )}
          </button>
        ))}
      </div>
    </div>
  );
};
