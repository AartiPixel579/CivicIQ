'use client';

import React from 'react';
import { 
  Building2, MapPin, Clock, Phone, Mail, FileText, 
  ShieldCheck, Download, Eye, HelpCircle 
} from 'lucide-react';

export const DepartmentDetailsSidebar = ({
  department,
  forms = [],
  onPreviewPdf,
  onAskSampleQuestion,
}) => {
  if (!department) return null;

  return (
    <aside className="w-full lg:w-80 flex-shrink-0 space-y-4">
      {/* Engineering Department Profile */}
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm text-slate-800">
        <div className="flex items-center space-x-2.5 mb-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-100 text-blue-800 font-bold font-mono text-sm ring-1 ring-blue-300">
            ENG
          </div>
          <div>
            <div className="text-[10px] uppercase font-bold text-blue-700 tracking-wider">
              Edison Township
            </div>
            <h2 className="text-sm font-bold text-slate-900 leading-tight">
              {department.name}
            </h2>
          </div>
        </div>

        <p className="text-xs text-slate-600 mb-3 leading-relaxed">
          {department.description}
        </p>

        {/* Counter & Location */}
        <div className="space-y-2.5 border-t border-slate-100 pt-3 text-xs">
          <div className="flex items-start space-x-2">
            <MapPin className="h-4 w-4 text-blue-600 flex-shrink-0 mt-0.5" />
            <div>
              <span className="font-bold text-slate-800 block">{department.location?.counter}</span>
              <span className="text-slate-500 text-[11px]">{department.location?.building}</span>
              <span className="text-slate-400 text-[10px] block">{department.location?.address}</span>
            </div>
          </div>

          <div className="flex items-start space-x-2">
            <Clock className="h-4 w-4 text-blue-600 flex-shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold text-slate-700">{department.operating_hours?.weekdays}</span>
              {department.operating_hours?.intake_cutoff && (
                <span className="text-amber-600 text-[11px] block">{department.operating_hours.intake_cutoff}</span>
              )}
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <Phone className="h-4 w-4 text-blue-600 flex-shrink-0" />
            <span className="font-medium text-slate-700">{department.contact?.phone}</span>
          </div>

          <div className="flex items-center space-x-2">
            <Mail className="h-4 w-4 text-blue-600 flex-shrink-0" />
            <span className="font-medium text-slate-600 truncate">{department.contact?.email}</span>
          </div>
        </div>
      </div>

      {/* Official PDF Forms */}
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm text-slate-800">
        <div className="flex items-center justify-between mb-2.5">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 flex items-center">
            <FileText className="mr-1.5 h-3.5 w-3.5 text-blue-600" />
            Official Applications & Forms
          </h3>
          <span className="text-[10px] text-slate-400 font-mono">
            edisonnj.org
          </span>
        </div>

        <div className="space-y-1.5 max-h-64 overflow-y-auto pr-0.5">
          {forms.map((formFile, idx) => {
            const downloadUrl = `/api/forms/engineering/${formFile}`;
            return (
              <div
                key={idx}
                className="flex items-center justify-between p-2 rounded-lg border border-slate-100 bg-slate-50 hover:bg-slate-100/80 transition-colors text-xs"
              >
                <div className="truncate pr-2 font-mono text-[11px] text-slate-700">
                  {formFile}
                </div>
                <div className="flex items-center space-x-1 flex-shrink-0">
                  <button
                    onClick={() => onPreviewPdf(downloadUrl, formFile)}
                    className="p-1 rounded text-slate-600 hover:text-blue-700 hover:bg-blue-100 transition-colors"
                    title="Preview PDF"
                  >
                    <Eye className="h-3.5 w-3.5" />
                  </button>
                  <a
                    href={downloadUrl}
                    download={formFile}
                    className="p-1 rounded text-slate-600 hover:text-amber-700 hover:bg-amber-100 transition-colors"
                    title="Download Official PDF"
                  >
                    <Download className="h-3.5 w-3.5" />
                  </a>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Common Resident Questions */}
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm text-slate-800">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2.5 flex items-center">
          <HelpCircle className="mr-1.5 h-3.5 w-3.5 text-blue-600" />
          Common Inquiries
        </h3>
        <div className="space-y-1.5 text-xs">
          <button
            onClick={() => onAskSampleQuestion("I need a street excavation permit to connect underground utilities.")}
            className="w-full text-left p-2 rounded-lg bg-blue-50/50 hover:bg-blue-100 text-blue-900 font-medium transition-colors"
          >
            🚧 How do I apply for a street opening / road excavation permit?
          </button>
          <button
            onClick={() => onAskSampleQuestion("I need to remove a tree on my property. What is the procedure?")}
            className="w-full text-left p-2 rounded-lg bg-blue-50/50 hover:bg-blue-100 text-blue-900 font-medium transition-colors"
          >
            🌳 What are the rules and permits for tree removal?
          </button>
          <button
            onClick={() => onAskSampleQuestion("How do I apply for a sewer connection in Edison?")}
            className="w-full text-left p-2 rounded-lg bg-blue-50/50 hover:bg-blue-100 text-blue-900 font-medium transition-colors"
          >
            💧 How do I apply for a sewer connection?
          </button>
          <button
            onClick={() => onAskSampleQuestion("What documents do I need to attach for a residential permit?")}
            className="w-full text-left p-2 rounded-lg bg-blue-50/50 hover:bg-blue-100 text-blue-900 font-medium transition-colors"
          >
            📋 What documents are required for residential permits?
          </button>
          <button
            onClick={() => onAskSampleQuestion("Where and when can I submit my engineering permit application in Edison?")}
            className="w-full text-left p-2 rounded-lg bg-blue-50/50 hover:bg-blue-100 text-blue-900 font-medium transition-colors"
          >
            🏢 Where and when can I submit my permit application?
          </button>
        </div>
      </div>
    </aside>
  );
};
