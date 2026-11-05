'use client';

import React from 'react';
import { BookOpen, ExternalLink } from 'lucide-react';
import { resolveBackendUrl } from '../utils/url';

export const RagCitationCard = ({ citations }) => {
  if (!citations || citations.length === 0) return null;

  return (
    <div className="mt-3 pt-2.5 border-t border-slate-100">
      <div className="text-[11px] font-semibold text-slate-500 mb-1.5">
        Official Documents & References
      </div>
      <div className="space-y-1.5">
        {citations.map((c, idx) => (
          <a
            key={idx}
            href={resolveBackendUrl(c.url)}
            target="_blank"
            rel="noreferrer"
            className="flex items-center justify-between p-2 rounded-lg border border-slate-200/80 bg-slate-50/60 hover:bg-blue-50/50 hover:border-blue-300 text-xs text-slate-700 transition-colors group"
          >
            <div className="flex items-center space-x-2 truncate">
              <BookOpen className="h-3.5 w-3.5 text-blue-600 flex-shrink-0" aria-hidden="true" focusable="false" />
              <span className="font-medium text-blue-700 group-hover:text-blue-900 group-hover:underline truncate">
                {c.title}
              </span>
            </div>
            <ExternalLink className="h-3 w-3 text-slate-400 group-hover:text-blue-600 flex-shrink-0 ml-2" aria-hidden="true" focusable="false" />
          </a>
        ))}
      </div>
    </div>
  );
};
