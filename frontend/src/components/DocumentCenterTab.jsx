'use client';

import React, { useState, useEffect } from 'react';
import { 
  FileText, Search, ExternalLink, Download, Eye, 
  ArrowRight, Filter, Building2, Mail, MapPin, 
  DollarSign, ShieldCheck, CheckCircle2, RefreshCw 
} from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

export const DocumentCenterTab = ({ onStartFlow, onPreviewPdf }) => {
  const [documents, setDocuments] = useState([]);
  const [categories, setCategories] = useState(['All']);
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchDocuments();
  }, [selectedCategory, searchQuery]);

  const fetchDocuments = async () => {
    setIsLoading(true);
    try {
      const params = new URLSearchParams();
      if (selectedCategory && selectedCategory !== 'All') {
        params.append('category', selectedCategory);
      }
      if (searchQuery.trim()) {
        params.append('search', searchQuery.trim());
      }

      const res = await fetch(`${API_BASE}/api/document-center?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setDocuments(data.documents || []);
        if (data.categories && data.categories.length > 0) {
          setCategories(data.categories);
        }
      }
    } catch (err) {
      console.error('Error fetching document center data:', err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden min-h-[600px] max-h-[85vh]">
      {/* Header Banner */}
      <div className="px-6 py-4 bg-gradient-to-r from-blue-950 via-slate-900 to-indigo-950 text-white">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-xl bg-blue-800/80 ring-1 ring-blue-600 text-amber-300">
              <FileText className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-amber-400">
                  Municipal Document Center
                </span>
                <span className="inline-flex items-center text-[10px] bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded-full font-medium">
                  <ShieldCheck className="h-3 w-3 mr-1" /> Verified Official Forms
                </span>
              </div>
              <h2 className="text-base font-bold text-white tracking-tight">
                Township of Edison Public Records & Forms Repository
              </h2>
            </div>
          </div>

          <a
            href="https://www.edisonnj.org/document_center/index.php"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center px-3 py-1.5 rounded-lg bg-blue-800/60 hover:bg-blue-700 text-xs font-semibold text-blue-200 hover:text-white transition-all ring-1 ring-blue-600/40"
          >
            <span>Live edisonnj.org Portal</span>
            <ExternalLink className="ml-1.5 h-3.5 w-3.5" />
          </a>
        </div>

        {/* Search Bar & Category Filters */}
        <div className="mt-4 flex flex-col sm:flex-row gap-3 items-center justify-between">
          <div className="relative w-full sm:w-80">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search forms, permits, keywords (e.g. zoning, pool, deck, road)..."
              className="w-full pl-9 pr-4 py-2 rounded-xl bg-slate-900/80 border border-slate-700 text-xs text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:border-transparent transition-all"
            />
          </div>

          {/* Quick Counter */}
          <div className="text-xs text-blue-300 font-medium">
            Showing <span className="font-bold text-white">{documents.length}</span> official municipal forms
          </div>
        </div>

        {/* Category Filter Pills */}
        <div className="mt-3 flex items-center space-x-2 overflow-x-auto pb-1 scrollbar-none">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-3 py-1 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${
                selectedCategory === cat
                  ? 'bg-amber-400 text-slate-950 shadow-sm'
                  : 'bg-blue-900/60 text-blue-200 hover:bg-blue-800/80 hover:text-white'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Documents List */}
      <div className="flex-1 overflow-y-auto p-5 bg-slate-50/60 space-y-3">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-16 text-slate-400 space-y-2">
            <RefreshCw className="h-6 w-6 animate-spin text-blue-600" />
            <span className="text-xs font-medium">Loading official documents from edisonnj.org repository...</span>
          </div>
        ) : documents.length === 0 ? (
          <div className="p-8 text-center bg-white rounded-xl border border-slate-200 text-slate-500">
            <FileText className="h-8 w-8 mx-auto text-slate-300 mb-2" />
            <p className="text-xs font-semibold">No documents found matching "{searchQuery}".</p>
            <p className="text-[11px] text-slate-400 mt-1">Try clearing your search query or selecting "All" categories.</p>
          </div>
        ) : (
          documents.map((doc) => (
            <div
              key={doc.id}
              className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:shadow-md hover:border-blue-300 transition-all text-xs text-slate-800"
            >
              <div className="flex flex-col md:flex-row md:items-start justify-between gap-3">
                <div className="flex-1">
                  <div className="flex items-center space-x-2 mb-1">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-blue-700 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-md">
                      {doc.category}
                    </span>
                    {doc.flow_id && (
                      <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-md flex items-center">
                        <CheckCircle2 className="h-3 w-3 mr-1" /> Guided Procedure Available
                      </span>
                    )}
                  </div>

                  <h3 className="text-sm font-bold text-slate-900 mb-1">
                    {doc.title}
                  </h3>
                  <p className="text-slate-600 text-xs leading-relaxed mb-3">
                    {doc.description}
                  </p>

                  {/* Submission and Fee Info */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px] text-slate-600 border-t border-slate-100 pt-2">
                    <div className="flex items-center space-x-1.5">
                      <MapPin className="h-3.5 w-3.5 text-blue-600 flex-shrink-0" />
                      <span className="truncate">{doc.submission_desk}</span>
                    </div>
                    {doc.contact_email && (
                      <div className="flex items-center space-x-1.5">
                        <Mail className="h-3.5 w-3.5 text-blue-600 flex-shrink-0" />
                        <span className="font-mono text-blue-800">{doc.contact_email}</span>
                      </div>
                    )}
                    {doc.fee_summary && (
                      <div className="flex items-center space-x-1.5 col-span-1 sm:col-span-2">
                        <DollarSign className="h-3.5 w-3.5 text-amber-600 flex-shrink-0" />
                        <span className="font-medium text-slate-700">{doc.fee_summary}</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Actions */}
                <div className="flex flex-row md:flex-col items-center md:items-end justify-end space-x-2 md:space-x-0 md:space-y-2 flex-shrink-0">
                  <a
                    href={doc.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center px-3 py-1.5 rounded-lg bg-blue-50 hover:bg-blue-100 text-blue-700 text-xs font-semibold transition-all border border-blue-200"
                    title="Direct PDF download from edisonnj.org"
                  >
                    <Download className="mr-1.5 h-3.5 w-3.5" />
                    Download PDF
                  </a>

                  {doc.local_file && (
                    <button
                      onClick={() => onPreviewPdf(`/api/forms/${doc.department_id}/${doc.local_file}`, doc.title)}
                      className="inline-flex items-center px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition-all"
                      title="Preview in document modal"
                    >
                      <Eye className="mr-1.5 h-3.5 w-3.5" />
                      Preview
                    </button>
                  )}

                  {doc.flow_id && (
                    <button
                      onClick={() => onStartFlow(doc.flow_id)}
                      className="inline-flex items-center px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold transition-all shadow-sm"
                    >
                      <span>Start Procedure</span>
                      <ArrowRight className="ml-1 h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
