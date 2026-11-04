'use client';

import React, { useState } from 'react';
import { 
  FileText, CheckCircle2, Download, Edit3, ArrowRight, 
  AlertCircle, ExternalLink 
} from 'lucide-react';

export const FormSessionCard = ({
  recommendation,
  sessionInfo,
  pdfUrl,
  submissionGuidance,
  onStartSession,
  onEditField,
  onAnswerQuestion,
  onPreviewPdf
}) => {
  const [editingField, setEditingField] = useState(null);
  const [editValue, setEditValue] = useState('');

  // 1. Form Recommendation Card
  if (recommendation && !sessionInfo && !pdfUrl) {
    const form = recommendation.form;
    return (
      <div className="my-3 p-4 rounded-xl border border-blue-200 bg-blue-50/50 shadow-sm text-slate-800">
        <h4 className="text-sm font-semibold text-slate-900 mb-1">
          {form.official_title}
        </h4>
        <p className="text-xs text-slate-600 mb-3 leading-relaxed">
          {form.description}
        </p>

        <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-blue-100">
          <button
            onClick={() => onStartSession(form.form_id)}
            className="inline-flex items-center px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium shadow-sm transition-colors"
          >
            <span>Start Guided Application</span>
            <ArrowRight className="ml-1.5 h-3.5 w-3.5" aria-hidden="true" focusable="false" />
          </button>
          {form.local_filename && (
            <a
              href={`/api/forms/engineering/${form.local_filename}`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center px-3 py-1.5 rounded-lg bg-white hover:bg-slate-50 text-slate-700 border border-slate-300 text-xs font-medium transition-colors"
            >
              <ExternalLink className="mr-1.5 h-3.5 w-3.5 text-slate-500" aria-hidden="true" focusable="false" />
              <span>Blank Form</span>
            </a>
          )}
        </div>
      </div>
    );
  }

  // 2. Active Form-Filling Progress Bar
  if (sessionInfo && sessionInfo.status === 'in_progress') {
    const percent = Math.round((sessionInfo.current_step / sessionInfo.total_steps) * 100);
    return (
      <div className="my-3 p-3.5 rounded-xl border border-blue-200 bg-white shadow-sm">
        <div className="flex items-center justify-between text-xs mb-1.5">
          <span className="font-semibold text-slate-900 flex items-center">
            <FileText className="mr-1.5 h-3.5 w-3.5 text-blue-600 flex-shrink-0" aria-hidden="true" focusable="false" />
            <span>{sessionInfo.form_title}</span>
          </span>
          <span className="font-medium text-blue-600">
            Step {sessionInfo.current_step} of {sessionInfo.total_steps} ({percent}%)
          </span>
        </div>

        {/* Progress Bar */}
        <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden mb-2">
          <div 
            className="bg-blue-600 h-2 rounded-full transition-all duration-300"
            style={{ width: `${percent}%` }}
          />
        </div>

        {sessionInfo.can_edit && Object.keys(sessionInfo.collected_answers || {}).length > 0 && (
          <div className="text-[11px] text-slate-500 flex items-center justify-between pt-1 border-t border-slate-100">
            <span>Answers saved in active session</span>
            <span className="font-mono text-[10px] text-slate-400">Type /reset to restart</span>
          </div>
        )}
      </div>
    );
  }

  // 3. Completed PDF Draft Card & Signature Guidance
  if (pdfUrl || (sessionInfo && sessionInfo.is_complete)) {
    const guidance = submissionGuidance || {};
    return (
      <div className="my-4 rounded-xl border border-emerald-200 bg-white shadow-sm overflow-hidden text-slate-800">
        <div className="bg-emerald-50 px-4 py-3 border-b border-emerald-100 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-emerald-950">
              Completed Application Draft
            </h3>
            <span className="text-[11px] text-emerald-700">
              Ready to download, review and sign
            </span>
          </div>
          {pdfUrl && (
            <a
              href={pdfUrl}
              download
              className="inline-flex items-center px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium shadow-sm transition-colors"
            >
              <Download className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" focusable="false" />
              <span>Download Draft PDF</span>
            </a>
          )}
        </div>

        <div className="p-4 space-y-3 text-xs">
          <div className="p-2.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 leading-relaxed">
            <span className="font-semibold flex items-center text-amber-950 mb-0.5">
              <AlertCircle className="mr-1.5 h-3.5 w-3.5 text-amber-600 flex-shrink-0" aria-hidden="true" focusable="false" />
              <span>Physical Signature Required</span>
            </span>
            Please print this completed draft, sign by hand where indicated, and submit along with your required documents.
          </div>

          {/* Checklist */}
          {guidance.supporting_documents && guidance.supporting_documents.length > 0 && (
            <div>
              <span className="font-semibold text-slate-900 block mb-1">
                Required Attachments:
              </span>
              <ul className="space-y-1 text-slate-700">
                {guidance.supporting_documents.map((doc, idx) => (
                  <li key={idx} className="flex items-start">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 mr-1.5 mt-0.5 flex-shrink-0" aria-hidden="true" focusable="false" />
                    <span>{doc}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Submission routing link */}
          <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-500">
            <span>Online Document Center:</span>
            <a
              href="https://www.edisonnj.org/document_center/index.php"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center font-medium text-blue-600 hover:underline"
            >
              edisonnj.org/document_center
              <ExternalLink className="ml-1 h-3 w-3" />
            </a>
          </div>
        </div>
      </div>
    );
  }

  return null;
};
