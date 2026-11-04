'use client';

import React from 'react';
import { FileText, Download, Eye } from 'lucide-react';

export const OfficialPdfCard = ({ formPacket, onPreview }) => {
  if (!formPacket) return null;

  return (
    <div className="my-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:border-blue-400 transition-all text-slate-800">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center space-x-3 min-w-0">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-blue-700 flex-shrink-0">
            <FileText className="h-5 w-5" aria-hidden="true" focusable="false" />
          </div>
          <div className="min-w-0">
            <h4 className="text-sm font-semibold text-slate-900 leading-snug truncate sm:whitespace-normal">
              {formPacket.form_title}
            </h4>
          </div>
        </div>

        {/* Action Buttons: Preview & Direct Download */}
        <div className="flex items-center space-x-2 flex-shrink-0 self-end sm:self-auto">
          <button
            type="button"
            onClick={() => onPreview(formPacket.pdf_download_url, formPacket.form_title)}
            className="inline-flex items-center px-3.5 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-medium text-slate-700 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500"
            title="Preview Official PDF Document"
          >
            <Eye className="mr-1.5 h-3.5 w-3.5 text-slate-600" aria-hidden="true" focusable="false" />
            <span>Preview</span>
          </button>
          <a
            href={formPacket.pdf_download_url}
            download={formPacket.form_file}
            className="inline-flex items-center px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-xs font-medium text-white shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <Download className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" focusable="false" />
            <span>Download Official PDF</span>
          </a>
        </div>
      </div>
    </div>
  );
};
