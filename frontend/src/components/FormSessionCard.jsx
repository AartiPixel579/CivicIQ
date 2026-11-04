'use client';

import React, { useState } from 'react';
import { 
  FileText, CheckCircle2, Download, Edit3, ArrowRight, 
  AlertCircle, ShieldCheck, ExternalLink, HelpCircle 
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
      <div className="my-3 p-4 rounded-xl border-2 border-blue-600/40 bg-gradient-to-br from-blue-50/90 to-indigo-50/80 shadow-md text-slate-800">
        <div className="flex items-center space-x-2 text-xs font-bold text-blue-900 mb-1">
          <FileText className="h-4 w-4 text-blue-700" />
          <span>OFFICIAL APPLICATION IDENTIFIED</span>
        </div>
        <h4 className="text-sm font-bold text-slate-900 mb-1">
          {form.official_title}
        </h4>
        <p className="text-xs text-slate-600 mb-3 leading-relaxed">
          {form.description}
        </p>

        <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-blue-200/60">
          <button
            onClick={() => onStartSession(form.form_id)}
            className="inline-flex items-center px-4 py-2 rounded-lg bg-blue-700 hover:bg-blue-800 text-white text-xs font-bold shadow-sm transition-all hover:scale-[1.02]"
          >
            <span>Start Guided Application</span>
            <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
          </button>
          {form.local_filename && (
            <a
              href={`/api/forms/engineering/${form.local_filename}`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center px-3 py-2 rounded-lg bg-white hover:bg-slate-50 text-slate-700 border border-slate-300 text-xs font-medium"
            >
              <ExternalLink className="mr-1.5 h-3.5 w-3.5 text-slate-500" />
              Blank Form Reference
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
          <span className="font-bold text-blue-950 flex items-center">
            <FileText className="mr-1.5 h-3.5 w-3.5 text-blue-700" />
            {sessionInfo.form_title}
          </span>
          <span className="font-semibold text-blue-700">
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
      <div className="my-4 rounded-xl border-2 border-emerald-600/40 bg-white shadow-lg overflow-hidden text-slate-800">
        {/* Banner */}
        <div className="bg-gradient-to-r from-emerald-800 via-teal-800 to-blue-900 px-5 py-3.5 text-white flex items-center justify-between">
          <div>
            <span className="text-[10px] font-bold tracking-wider uppercase text-emerald-300 bg-emerald-950/60 px-2 py-0.5 rounded">
              Ready for Review & Signature
            </span>
            <h3 className="text-base font-bold text-white mt-1">
              Official Application Draft Generated
            </h3>
          </div>
          {pdfUrl && (
            <a
              href={pdfUrl}
              download
              className="inline-flex items-center px-4 py-2 rounded-lg bg-amber-400 hover:bg-amber-300 text-slate-950 text-xs font-bold shadow-md transition-all hover:scale-[1.02]"
            >
              <Download className="mr-1.5 h-4 w-4 stroke-[2.5]" />
              Download Official Draft PDF
            </a>
          )}
        </div>

        {/* Important Signature Notice */}
        <div className="p-4 space-y-3 text-xs">
          <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 leading-relaxed">
            <span className="font-bold flex items-center text-amber-950 mb-0.5">
              <AlertCircle className="mr-1.5 h-4 w-4 text-amber-600 flex-shrink-0" />
              Physical Ink Signature Required
            </span>
            Per municipal regulations, AI signatures are not accepted for official government filings. Please print this generated draft, sign by hand in Section 3, and submit with mandatory attachments.
          </div>

          {/* Checklist */}
          {guidance.supporting_documents && guidance.supporting_documents.length > 0 && (
            <div>
              <span className="font-bold text-slate-900 block mb-1">
                Mandatory Supporting Attachments:
              </span>
              <ul className="space-y-1 text-slate-700">
                {guidance.supporting_documents.map((doc, idx) => (
                  <li key={idx} className="flex items-start">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 mr-1.5 mt-0.5 flex-shrink-0" />
                    <span>{doc}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Submission routing link */}
          <div className="pt-2 border-t border-slate-200 flex items-center justify-between text-[11px] text-slate-600">
            <span>Official Portal: <strong>edisonnj.org/document_center</strong></span>
            <a
              href="https://www.edisonnj.org/document_center/index.php"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center font-semibold text-blue-700 hover:underline"
            >
              Access Document Center
              <ExternalLink className="ml-1 h-3 w-3" />
            </a>
          </div>
        </div>
      </div>
    );
  }

  return null;
};
