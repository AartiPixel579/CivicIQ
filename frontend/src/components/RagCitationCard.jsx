'use client';

import React, { useState } from 'react';
import { ExternalLink, BookOpen, ChevronDown, ChevronUp, ShieldCheck, Link2 } from 'lucide-react';

export const RagCitationCard = ({ citations }) => {
  const [expanded, setExpanded] = useState({});

  if (!citations || citations.length === 0) return null;

  const toggleExpand = (idx) => {
    setExpanded(prev => ({ ...prev, [idx]: !prev[idx] }));
  };

  return (
    <div className="mt-4 pt-3 border-t border-slate-200">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 flex items-center">
          <Link2 className="mr-1.5 h-3.5 w-3.5 text-blue-600" aria-hidden="true" focusable="false" />
          <span>Official Municipal References</span>
        </span>
        <span className="text-[10px] text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full flex items-center">
          <ShieldCheck className="mr-1 h-3 w-3" aria-hidden="true" focusable="false" />
          <span>Grounded Reference</span>
        </span>
      </div>

      <div className="space-y-2">
        {citations.map((c, idx) => {
          const isExp = !!expanded[idx];
          return (
            <div
              key={idx}
              className="rounded-lg border border-slate-200 bg-slate-50/70 p-2.5 text-xs text-slate-700 transition-all hover:border-blue-300"
            >
              <div className="flex items-center justify-between gap-2">
                <a
                  href={c.url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-bold text-blue-700 hover:text-blue-900 hover:underline flex items-center truncate"
                >
                  <BookOpen className="mr-1.5 h-3.5 w-3.5 flex-shrink-0 text-blue-600" aria-hidden="true" focusable="false" />
                  <span className="truncate">{c.title}</span>
                  <ExternalLink className="ml-1 h-3 w-3 flex-shrink-0" aria-hidden="true" focusable="false" />
                </a>

                <div className="flex items-center space-x-2 flex-shrink-0">
                  <span className="text-[10px] bg-blue-100 text-blue-800 font-semibold px-1.5 py-0.5 rounded">
                    {c.category}
                  </span>
                  <span className="text-[10px] font-mono text-slate-500">
                    Match: {Math.round(c.relevance_score * 100)}%
                  </span>
                  <button
                    onClick={() => toggleExpand(idx)}
                    className="p-1 text-slate-400 hover:text-slate-600"
                    title={isExp ? "Collapse excerpt" : "Expand excerpt"}
                  >
                    {isExp ? (
                      <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" focusable="false" />
                    ) : (
                      <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" focusable="false" />
                    )}
                  </button>
                </div>
              </div>

              {/* Exact citation URL */}
              <div className="mt-1 font-mono text-[10px] text-slate-400 truncate">
                {c.url}
              </div>

              {/* Excerpt */}
              {isExp && (
                <div className="mt-2 p-2 bg-white rounded border border-slate-200 text-slate-600 text-[11px] leading-relaxed italic border-l-2 border-l-blue-600">
                  "{c.excerpt}"
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
