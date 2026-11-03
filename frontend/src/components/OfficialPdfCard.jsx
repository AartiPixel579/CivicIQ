'use client';

import React, { useState } from 'react';
import { 
  FileText, Download, Eye, CheckCircle2, Circle, 
  MapPin, Clock, Phone, Mail, ShieldAlert, Award, ExternalLink 
} from 'lucide-react';

export const OfficialPdfCard = ({ formPacket, onPreview }) => {
  const [checkedItems, setCheckedItems] = useState({});

  if (!formPacket) return null;

  const toggleCheck = (idx) => {
    setCheckedItems(prev => ({ ...prev, [idx]: !prev[idx] }));
  };

  const attachments = formPacket.required_attachments || [];
  const allChecked = attachments.length > 0 &&
    attachments.every((_, idx) => checkedItems[idx]);

  return (
    <div className="my-4 rounded-xl border-2 border-blue-600/30 bg-white shadow-xl overflow-hidden text-slate-800 transition-all hover:border-blue-600/50">
      {/* Official Government Header Banner */}
      <div className="bg-gradient-to-r from-blue-900 via-blue-800 to-indigo-900 px-5 py-4 text-white">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center space-x-2">
            <span className="flex h-7 w-7 items-center justify-center rounded bg-blue-700/60 font-mono text-xs font-bold text-amber-300 ring-1 ring-amber-400/40">
              PV
            </span>
            <div className="text-xs uppercase tracking-wider font-semibold text-blue-200">
              City of Pixelvyne • Official Record
            </div>
          </div>
          <div className="inline-flex items-center rounded-full bg-emerald-500/20 px-2.5 py-0.5 text-xs font-medium text-emerald-300 ring-1 ring-emerald-500/30">
            <Award className="mr-1 h-3.5 w-3.5" />
            Verified Government Standard Form
          </div>
        </div>

        <div className="mt-3 flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div>
            <div className="font-mono text-xs font-bold text-amber-400">
              {formPacket.form_code}
            </div>
            <h3 className="text-lg font-bold text-white tracking-tight">
              {formPacket.form_title}
            </h3>
          </div>

          {/* Action Buttons: Preview & Direct Download */}
          <div className="flex items-center space-x-2">
            <button
              onClick={() => onPreview(formPacket.pdf_download_url, formPacket.form_title)}
              className="inline-flex items-center px-3 py-2 rounded-lg bg-blue-700 hover:bg-blue-600 text-xs font-semibold text-white shadow-sm transition-all focus:outline-none focus:ring-2 focus:ring-white/40"
              title="Preview Official PDF Document"
            >
              <Eye className="mr-1.5 h-4 w-4" />
              Preview Document
            </button>
            <a
              href={formPacket.pdf_download_url}
              download={formPacket.form_file}
              className="inline-flex items-center px-4 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-xs font-bold text-slate-950 shadow-md transition-all hover:scale-[1.02] focus:outline-none focus:ring-2 focus:ring-amber-300"
            >
              <Download className="mr-1.5 h-4 w-4 stroke-[2.5]" />
              Download Official PDF
            </a>
          </div>
        </div>
      </div>

      {/* Compliance Guarantee Bar */}
      <div className="bg-slate-100 border-b border-slate-200 px-5 py-2 flex items-center justify-between text-xs text-slate-600">
        <span className="flex items-center font-medium">
          <ShieldAlert className="mr-1.5 h-3.5 w-3.5 text-blue-700" />
          Pre-approved standardized form • Strict Municipal Policy: Zero AI hallucination
        </span>
        <span className="font-mono text-slate-500">
          File: {formPacket.form_file}
        </span>
      </div>

      <div className="p-5 space-y-5">
        {/* Fill-in Guidance */}
        <div className="rounded-lg bg-blue-50/60 p-3.5 border border-blue-100 text-xs text-slate-700">
          <div className="font-bold text-blue-950 mb-1 flex items-center">
            <FileText className="mr-1.5 h-3.5 w-3.5 text-blue-700" />
            Official Fill-In Instructions
          </div>
          <p className="whitespace-pre-line leading-relaxed text-slate-700">
            {formPacket.fill_in_instructions}
          </p>
        </div>

        {/* Mandatory Attachments Checklist */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center">
              Mandatory Attachments Checklist
              <span className="ml-2 text-[10px] normal-case font-normal text-slate-400">
                (Click to check off items as you gather them)
              </span>
            </h4>
            {allChecked && (
              <span className="text-xs font-semibold text-emerald-600 flex items-center">
                <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> All items verified!
              </span>
            )}
          </div>
          <div className="space-y-1.5">
            {attachments.map((item, idx) => {
              const isChecked = !!checkedItems[idx];
              return (
                <div
                  key={idx}
                  onClick={() => toggleCheck(idx)}
                  className={`flex items-start space-x-2.5 p-2 rounded-lg cursor-pointer border text-xs transition-all ${
                    isChecked 
                      ? 'bg-emerald-50/80 border-emerald-200 text-emerald-950' 
                      : 'bg-white border-slate-200 hover:bg-slate-50 text-slate-700'
                  }`}
                >
                  <div className="mt-0.5 flex-shrink-0">
                    {isChecked ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                    ) : (
                      <Circle className="h-4 w-4 text-slate-400" />
                    )}
                  </div>
                  <span className={`leading-snug ${isChecked ? 'line-through text-slate-500' : 'font-medium'}`}>
                    {item}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Fee & Lead Time Strip */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          {formPacket.fee_info && (
            <div className="p-3 rounded-lg bg-amber-50/60 border border-amber-200/80">
              <span className="font-bold text-amber-900 block mb-0.5">Municipal Fee Schedule</span>
              <span className="font-semibold text-slate-800">{formPacket.fee_info.amount}</span>
              <span className="text-[11px] text-slate-600 block mt-0.5">{formPacket.fee_info.payment_methods}</span>
            </div>
          )}
          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
            <span className="font-bold text-slate-900 block mb-0.5">Standard Processing Turnaround</span>
            <span className="font-semibold text-blue-900">{formPacket.lead_time}</span>
            <span className="text-[11px] text-slate-500 block mt-0.5">Subject to complete attachment verification</span>
          </div>
        </div>

        {/* Target Submission Desk Details (Prompt Requirement) */}
        {formPacket.submission_routing && (
          <div className="rounded-xl border border-blue-200 bg-gradient-to-br from-blue-50/80 to-indigo-50/50 p-4">
            <div className="flex items-center space-x-2 text-xs font-bold text-blue-950 mb-2">
              <MapPin className="h-4 w-4 text-blue-700" />
              <span>Target Submission Desk & Intake Routing</span>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-y-2 gap-x-4 text-xs text-slate-700">
              <div>
                <span className="text-slate-500 block text-[11px]">Department & Desk</span>
                <span className="font-bold text-slate-900">{formPacket.submission_routing.department}</span>
                <span className="block font-medium text-blue-800">{formPacket.submission_routing.desk}</span>
              </div>
              <div>
                <span className="text-slate-500 block text-[11px]">Building Address</span>
                <span className="font-medium text-slate-800">{formPacket.submission_routing.building_address}</span>
              </div>
              <div className="flex items-center space-x-1.5 pt-1">
                <Clock className="h-3.5 w-3.5 text-blue-700 flex-shrink-0" />
                <span>{formPacket.submission_routing.hours}</span>
              </div>
              <div className="flex items-center space-x-1.5 pt-1">
                <Phone className="h-3.5 w-3.5 text-blue-700 flex-shrink-0" />
                <span>{formPacket.submission_routing.contact_phone}</span>
                <span className="text-slate-300">|</span>
                <Mail className="h-3.5 w-3.5 text-blue-700 flex-shrink-0" />
                <span className="truncate">{formPacket.submission_routing.contact_email}</span>
              </div>
            </div>

            {formPacket.submission_routing.digital_upload_url && (
              <div className="mt-3 pt-3 border-t border-blue-200/60 flex items-center justify-between text-xs">
                <span className="text-slate-600">Digital Submission Portal:</span>
                <a
                  href={formPacket.submission_routing.digital_upload_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center font-semibold text-blue-700 hover:text-blue-900 hover:underline"
                >
                  Access Municipal e-Portal
                  <ExternalLink className="ml-1 h-3 w-3" />
                </a>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
