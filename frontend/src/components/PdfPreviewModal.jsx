'use client';

import React from 'react';
import { X, Download, ExternalLink, ShieldCheck, FileText } from 'lucide-react';
import { resolveBackendUrl } from '../utils/url';

export const PdfPreviewModal = ({
  isOpen,
  onClose,
  pdfUrl,
  title
}) => {
  if (!isOpen) return null;

  const resolvedUrl = resolveBackendUrl(pdfUrl);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm animate-fade-in">
      <div className="relative flex flex-col w-full max-w-4xl h-[88vh] bg-white rounded-2xl shadow-2xl border border-slate-300 overflow-hidden">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-5 py-3.5 bg-gradient-to-r from-blue-900 to-indigo-900 text-white">
          <div className="flex items-center space-x-2.5">
            <div className="p-1.5 rounded-lg bg-blue-800 ring-1 ring-blue-700">
              <FileText className="h-5 w-5 text-amber-300" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-amber-300">
                  Municipal Official Document Viewer
                </span>
                <span className="inline-flex items-center text-[10px] bg-emerald-500/20 text-emerald-300 px-2 py-0.2 rounded-full font-medium">
                  <ShieldCheck className="h-3 w-3 mr-0.5" /> Authentic Static PDF
                </span>
              </div>
              <h2 className="text-sm font-bold text-white truncate max-w-md md:max-w-xl">
                {title}
              </h2>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <a
              href={resolvedUrl}
              download
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold transition-all"
            >
              <Download className="h-3.5 w-3.5 mr-1" />
              Download
            </a>
            <a
              href={resolvedUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center p-2 rounded-lg bg-blue-800 hover:bg-blue-700 text-blue-200 transition-all"
              title="Open in new tab"
            >
              <ExternalLink className="h-4 w-4" />
            </a>
            <button
              onClick={onClose}
              className="p-2 rounded-lg bg-blue-800 hover:bg-red-600 text-white transition-all focus:outline-none"
              title="Close viewer"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* PDF Embedded View */}
        <div className="relative flex-1 w-full bg-slate-200">
          <iframe
            src={`${resolvedUrl}#toolbar=1&navpanes=0`}
            className="w-full h-full border-0"
            title={title}
          />
        </div>

        {/* Footer Info */}
        <div className="px-5 py-2.5 bg-slate-100 border-t border-slate-200 flex flex-wrap items-center justify-between text-xs text-slate-600">
          <span className="font-mono text-[11px]">
            Source: /departments/forms • Township of Edison Records Repository (edisonnj.org)
          </span>
          <span className="font-medium text-slate-500">
            Press Esc or click Close to return to assistant
          </span>
        </div>
      </div>
    </div>
  );
};
