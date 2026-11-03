'use client';

import React from 'react';
import { 
  Building2, MapPin, Clock, Phone, Mail, FileText, 
  ArrowRight, ShieldCheck, Download, Eye, ExternalLink, HelpCircle 
} from 'lucide-react';

export const DepartmentDetailsSidebar = ({
  department,
  flows = [],
  forms = [],
  onStartFlow,
  onPreviewPdf,
  onAskSampleQuestion,
}) => {
  if (!department) return null;

  return (
    <aside className="w-full lg:w-80 flex-shrink-0 space-y-4">
      {/* Department Official Profile */}
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm text-slate-800">
        <div className="flex items-center space-x-2.5 mb-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-100 text-blue-800 font-bold font-mono text-sm ring-1 ring-blue-300">
            {department.badge}
          </div>
          <div>
            <div className="text-[10px] uppercase font-bold text-blue-700 tracking-wider">
              Department Profile
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
        <div className="space-y-2 border-t border-slate-100 pt-3 text-xs">
          <div className="flex items-start space-x-2">
            <MapPin className="h-4 w-4 text-blue-600 flex-shrink-0 mt-0.5" />
            <div>
              <span className="font-bold text-slate-800 block">{department.location?.counter}</span>
              <span className="text-slate-500 text-[11px]">{department.location?.building}, {department.location?.floor}</span>
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

      {/* Available Procedural Decision Trees */}
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm text-slate-800">
        <div className="flex items-center justify-between mb-2.5">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Procedural Flows
          </h3>
          <span className="text-[10px] font-semibold text-blue-700 bg-blue-50 px-2 py-0.5 rounded-full border border-blue-200">
            Deterministic Engine
          </span>
        </div>

        <div className="space-y-2">
          {flows.map((flow) => (
            <div
              key={flow.id}
              className="p-3 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-blue-50/40 hover:border-blue-300 transition-all text-xs"
            >
              <div className="font-bold text-slate-900 mb-1 flex items-center justify-between">
                <span>{flow.title}</span>
                <span className="font-mono text-[10px] text-slate-400">{flow.code}</span>
              </div>
              <p className="text-slate-500 text-[11px] line-clamp-2 mb-2 leading-relaxed">
                {flow.description}
              </p>
              <button
                onClick={() => onStartFlow(flow.id)}
                className="w-full inline-flex items-center justify-center px-3 py-1.5 rounded-lg bg-blue-700 hover:bg-blue-600 text-white font-semibold text-xs transition-colors shadow-sm"
              >
                <span>Launch Procedure</span>
                <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Official PDF Document Registry */}
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm text-slate-800">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center">
            <FileText className="mr-1.5 h-3.5 w-3.5 text-blue-600" />
            Official PDF Repository
          </h3>
          <span className="text-[10px] text-slate-400">
            /departments/{department.id}/forms
          </span>
        </div>

        <div className="space-y-1.5">
          {forms.map((formFile, idx) => {
            const downloadUrl = `/api/forms/${department.id}/${formFile}`;
            return (
              <div
                key={idx}
                className="flex items-center justify-between p-2 rounded-lg border border-slate-100 bg-slate-50 text-xs"
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

      {/* Quick Grounded Q&A Inquiries */}
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm text-slate-800">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2 flex items-center">
          <HelpCircle className="mr-1.5 h-3.5 w-3.5 text-blue-600" />
          Sample Grounded Inquiries
        </h3>
        <div className="space-y-1.5 text-xs">
          {department.id === 'engineering' ? (
            <>
              <button
                onClick={() => onAskSampleQuestion("What are the minimum setback distances for an R-1 residential zone?")}
                className="w-full text-left p-2 rounded-lg bg-blue-50/50 hover:bg-blue-100 text-blue-900 font-medium transition-colors"
              >
                📐 What are the setback distances for R-1 residential zone?
              </button>
              <button
                onClick={() => onAskSampleQuestion("How much is the residential building permit fee and plan review cost?")}
                className="w-full text-left p-2 rounded-lg bg-blue-50/50 hover:bg-blue-100 text-blue-900 font-medium transition-colors"
              >
                💵 What is the residential permit fee schedule for 2026?
              </button>
              <button
                onClick={() => onAskSampleQuestion("What are the required inspection sequence stages before Certificate of Occupancy?")}
                className="w-full text-left p-2 rounded-lg bg-blue-50/50 hover:bg-blue-100 text-blue-900 font-medium transition-colors"
              >
                🔍 What inspections are required before Certificate of Occupancy?
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => onAskSampleQuestion("What are the mandatory cold-holding and hot-holding temperatures for food?")}
                className="w-full text-left p-2 rounded-lg bg-blue-50/50 hover:bg-blue-100 text-blue-900 font-medium transition-colors"
              >
                🌡️ What are the temperature requirements for food storage?
              </button>
              <button
                onClick={() => onAskSampleQuestion("What is the annual operating license fee for a restaurant under 50 seats?")}
                className="w-full text-left p-2 rounded-lg bg-blue-50/50 hover:bg-blue-100 text-blue-900 font-medium transition-colors"
              >
                💵 How much is the food establishment licensing fee?
              </button>
              <button
                onClick={() => onAskSampleQuestion("What water tank capacity is required for a mobile food truck?")}
                className="w-full text-left p-2 rounded-lg bg-blue-50/50 hover:bg-blue-100 text-blue-900 font-medium transition-colors"
              >
                🚚 What water tank capacity is required for food trucks?
              </button>
            </>
          )}
        </div>
      </div>
    </aside>
  );
};
