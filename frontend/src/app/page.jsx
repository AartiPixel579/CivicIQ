'use client';

import React, { useState, useEffect } from 'react';
import { 
  Building, ShieldCheck, HardHat, Stethoscope, FileText, 
  Sparkles, Layers, Info, MapPin, Phone, HelpCircle 
} from 'lucide-react';
import { DepartmentSelector } from '../components/DepartmentSelector';
import { DepartmentDetailsSidebar } from '../components/DepartmentDetailsSidebar';
import { ChatInterface } from '../components/ChatInterface';
import { PdfPreviewModal } from '../components/PdfPreviewModal';
import { DocumentCenterTab } from '../components/DocumentCenterTab';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

export default function Home() {
  const [departments, setDepartments] = useState([]);
  const [selectedDeptId, setSelectedDeptId] = useState('engineering');
  const [activeDepartment, setActiveDepartment] = useState(null);
  const [flows, setFlows] = useState([]);
  const [forms, setForms] = useState([]);
  
  const [sessionId, setSessionId] = useState('');
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('assistant'); // 'assistant' | 'documents'

  // PDF Preview Modal State
  const [previewPdfUrl, setPreviewPdfUrl] = useState('');
  const [previewPdfTitle, setPreviewPdfTitle] = useState('');
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);

  // 1. Initialize session and load departments
  useEffect(() => {
    let sid = localStorage.getItem('pixelvyne_session_id');
    if (!sid) {
      sid = 'session_' + Math.random().toString(36).substring(2, 9) + '_' + Date.now();
      localStorage.setItem('pixelvyne_session_id', sid);
    }
    setSessionId(sid);

    fetchDepartments();
  }, []);

  // 2. Fetch all departments
  const fetchDepartments = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/departments`);
      if (res.ok) {
        const data = await res.json();
        setDepartments(data);
        if (data.length > 0) {
          loadDepartmentData(data[0].id);
        }
      }
    } catch (err) {
      console.error('Failed to load departments:', err);
    }
  };

  // 3. Load specific department details (flows, forms, config)
  const loadDepartmentData = async (deptId) => {
    try {
      const res = await fetch(`${API_BASE}/api/departments/${deptId}`);
      if (res.ok) {
        const data = await res.json();
        setActiveDepartment(data.config);
        setFlows(data.flows || []);
        setForms(data.forms || []);
        setSelectedDeptId(deptId);

        // Add welcome message if chat is empty
        if (messages.length === 0) {
          const welcomeMsg = {
            id: 'welcome_' + Date.now(),
            sender: 'assistant',
            text: `Welcome to the **City of Pixelvyne Smart Assistant**. I operate under municipal protocols to provide verified procedural guidance.\n\n• **Grounded Link RAG**: Inquiries are strictly retrieved from official municipal links.\n• **Deterministic Flowcharts**: Step-by-step prerequisite checks for permit/license issuance.\n• **Official PDF Delivery**: Standardized, authentic government forms (no AI-fabricated documents).\n\nCurrently routing to the **${data.config.name}** (${data.config.location.counter}).\nHow may I assist your municipal service request today?`,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            mode: 'general',
          };
          setMessages([welcomeMsg]);
        }
      }
    } catch (err) {
      console.error(`Failed to load department ${deptId}:`, err);
    }
  };

  const handleSelectDepartment = (deptId) => {
    setSelectedDeptId(deptId);
    loadDepartmentData(deptId);
    
    // Notify in chat
    const switchMsg = {
      id: 'switch_' + Date.now(),
      sender: 'system',
      text: `Routed inquiry desk to ${deptId.toUpperCase()} Department.`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    setMessages(prev => [...prev, switchMsg]);
  };

  // 4. Send Message (either free text or step choice)
  const handleSendMessage = async (text, optionId) => {
    if (!sessionId) return;

    // Append user message if user typed something
    if (text) {
      const userMsg = {
        id: 'user_' + Date.now(),
        sender: 'user',
        text: text,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages(prev => [...prev, userMsg]);
    } else if (optionId) {
      // Find label for option to display as user action
      const lastMsg = messages[messages.length - 1];
      const opt = lastMsg?.options?.find(o => o.id === optionId);
      const userMsg = {
        id: 'user_opt_' + Date.now(),
        sender: 'user',
        text: opt ? `Selected: ${opt.label}` : `Choice: ${optionId}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages(prev => [...prev, userMsg]);
    }

    setIsLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          message: text || '',
          department_id: selectedDeptId,
          selected_option_id: optionId || null,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        const assistantMsg = {
          id: 'asst_' + Date.now(),
          sender: 'assistant',
          text: data.message,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          mode: data.mode,
          options: data.options,
          form_packet: data.form_packet,
          citations: data.citations,
          current_step: data.current_step,
          active_flow_id: data.active_flow_id,
          department_id: data.department_id,
          completed: data.completed,
        };
        setMessages(prev => [...prev, assistantMsg]);
      } else {
        const errData = await res.json().catch(() => ({}));
        const errorMsg = {
          id: 'err_' + Date.now(),
          sender: 'assistant',
          text: `⚠️ **Municipal Desk Notice**: ${errData.detail || 'An error occurred while communicating with the service registry. Please retry.'}`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        };
        setMessages(prev => [...prev, errorMsg]);
      }
    } catch (err) {
      console.error('Chat error:', err);
      const errorMsg = {
        id: 'err_network_' + Date.now(),
        sender: 'assistant',
        text: '⚠️ **Network Notice**: Unable to contact municipal backend API. Please ensure the backend service is running on port 8000.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  // 5. Start a specific flow from sidebar
  const handleStartFlow = async (flowId) => {
    if (!sessionId) return;
    setIsLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/flow/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          department_id: selectedDeptId,
          flow_id: flowId,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        const flowMsg = {
          id: 'flow_start_' + Date.now(),
          sender: 'assistant',
          text: `Initiating procedure: **${data.current_step?.title || flowId}**\n\n${data.message}`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          mode: 'flow',
          options: data.options,
          current_step: data.current_step,
          active_flow_id: flowId,
          department_id: selectedDeptId,
          completed: false,
        };
        setMessages(prev => [...prev, flowMsg]);
      }
    } catch (err) {
      console.error('Start flow error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // 6. Reset session
  const handleResetSession = async () => {
    if (!sessionId) return;
    try {
      await fetch(`${API_BASE}/api/flow/reset?session_id=${encodeURIComponent(sessionId)}`, {
        method: 'POST',
      });
      const resetMsg = {
        id: 'reset_' + Date.now(),
        sender: 'assistant',
        text: 'Session state reset. You are at the main municipal inquiries desk. You may start a new procedure or ask any grounded question.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        mode: 'general',
      };
      setMessages(prev => [...prev, resetMsg]);
    } catch (err) {
      console.error('Reset error:', err);
    }
  };

  const handleOpenPdfPreview = (url, title) => {
    setPreviewPdfUrl(url);
    setPreviewPdfTitle(title);
    setIsPreviewOpen(true);
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-100 text-slate-800">
      {/* Top Municipal Navigation Bar */}
      <header className="sticky top-0 z-40 bg-gradient-to-r from-blue-950 via-slate-900 to-blue-950 text-white shadow-md border-b border-blue-900">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          {/* Logo & Municipal Seal */}
          <div className="flex items-center space-x-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-amber-400 to-amber-600 text-blue-950 font-black shadow-inner ring-2 ring-amber-300/40">
              <span className="text-base tracking-tighter">PV</span>
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-xs font-bold tracking-widest uppercase text-amber-400">
                  City of Pixelvyne
                </span>
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-[10px] text-emerald-300 font-mono">Service Portal Live</span>
              </div>
              <h1 className="text-base font-extrabold text-white tracking-tight leading-none">
                Pixelvyne Smart Assistant
              </h1>
            </div>
          </div>

          {/* Department Switcher & Navigation Tabs */}
          <div className="hidden sm:flex items-center space-x-3">
            <div className="flex items-center space-x-1 bg-slate-900 p-1 rounded-xl border border-slate-700 text-xs">
              <button
                onClick={() => setActiveTab('assistant')}
                className={`px-3 py-1.5 rounded-lg font-semibold transition-all ${
                  activeTab === 'assistant'
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'text-slate-300 hover:text-white'
                }`}
              >
                Smart Assistant
              </button>
              <button
                onClick={() => setActiveTab('documents')}
                className={`px-3 py-1.5 rounded-lg font-semibold transition-all flex items-center space-x-1.5 ${
                  activeTab === 'documents'
                    ? 'bg-amber-500 text-slate-950 shadow-sm'
                    : 'text-slate-300 hover:text-white'
                }`}
              >
                <span>Document Center</span>
                <span className="text-[10px] bg-amber-400/30 text-amber-300 px-1.5 py-0.2 rounded-full font-bold">
                  edisonnj.org
                </span>
              </button>
            </div>

            <span className="text-xs text-blue-300 font-medium">Department:</span>
            <DepartmentSelector
              departments={departments}
              selectedDeptId={selectedDeptId}
              onSelectDepartment={handleSelectDepartment}
            />
          </div>
        </div>

        {/* Mobile department & tab bar */}
        <div className="sm:hidden px-4 py-2 bg-blue-950 border-t border-blue-900 flex flex-col space-y-2">
          <div className="flex justify-center space-x-2 text-xs">
            <button
              onClick={() => setActiveTab('assistant')}
              className={`px-3 py-1 rounded-lg font-semibold ${activeTab === 'assistant' ? 'bg-blue-600 text-white' : 'text-slate-300'}`}
            >
              Assistant
            </button>
            <button
              onClick={() => setActiveTab('documents')}
              className={`px-3 py-1 rounded-lg font-semibold ${activeTab === 'documents' ? 'bg-amber-500 text-slate-950' : 'text-slate-300'}`}
            >
              Document Center (edisonnj.org)
            </button>
          </div>
          <div className="flex justify-center">
            <DepartmentSelector
              departments={departments}
              selectedDeptId={selectedDeptId}
              onSelectDepartment={handleSelectDepartment}
            />
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <div className="flex flex-col lg:flex-row gap-6 items-start">
          {activeTab === 'assistant' ? (
            <ChatInterface
              messages={messages}
              isLoading={isLoading}
              activeDepartment={activeDepartment}
              onSendMessage={handleSendMessage}
              onResetSession={handleResetSession}
              onPreviewPdf={handleOpenPdfPreview}
            />
          ) : (
            <DocumentCenterTab
              onStartFlow={(flowId) => {
                setActiveTab('assistant');
                handleStartFlow(flowId);
              }}
              onPreviewPdf={handleOpenPdfPreview}
            />
          )}

          {/* Department Information & Quick Action Sidebar */}
          <DepartmentDetailsSidebar
            department={activeDepartment}
            flows={flows}
            forms={forms}
            onStartFlow={(flowId) => {
              setActiveTab('assistant');
              handleStartFlow(flowId);
            }}
            onPreviewPdf={handleOpenPdfPreview}
            onAskSampleQuestion={(q) => {
              setActiveTab('assistant');
              handleSendMessage(q);
            }}
          />
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-slate-200 py-4 px-6 text-center text-xs text-slate-500">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2">
          <span className="flex items-center">
            <ShieldCheck className="h-4 w-4 mr-1.5 text-blue-700" />
            Official Government Record Portal • City of Pixelvyne • Powered by Grounded Link RAG & Deterministic Flow Engine
          </span>
          <span className="font-mono text-slate-400">
            Municipal Code Chapter 48 & 33 Compliant
          </span>
        </div>
      </footer>

      {/* Official PDF Document Preview Modal */}
      <PdfPreviewModal
        isOpen={isPreviewOpen}
        onClose={() => setIsPreviewOpen(false)}
        pdfUrl={previewPdfUrl}
        title={previewPdfTitle}
      />
    </div>
  );
}
