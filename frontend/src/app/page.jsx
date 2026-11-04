'use client';

import React, { useState, useEffect } from 'react';
import { ShieldCheck, Bot, Sparkles } from 'lucide-react';
import { ChatInterface } from '../components/ChatInterface';
import { PdfPreviewModal } from '../components/PdfPreviewModal';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

export default function Home() {
  const [sessionId, setSessionId] = useState('');
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  // PDF Preview Modal State
  const [previewPdfUrl, setPreviewPdfUrl] = useState('');
  const [previewPdfTitle, setPreviewPdfTitle] = useState('');
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);

  // 1. Initialize session and welcome message
  useEffect(() => {
    let sid = localStorage.getItem('civiciq_session_id');
    if (!sid) {
      sid = 'session_' + Math.random().toString(36).substring(2, 9) + '_' + Date.now();
      localStorage.setItem('civiciq_session_id', sid);
    }
    setSessionId(sid);

    if (messages.length === 0) {
      const welcomeMsg = {
        id: 'welcome_' + Date.now(),
        sender: 'assistant',
        text: `CivicIQ\n\nMushkil Your Edison Township Buddy\n\nHow can **"CivicIQ"** help you today?`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        mode: 'general',
      };
      setMessages([welcomeMsg]);
    }
  }, []);

  // 2. Send Message (with conversation context)
  const handleSendMessage = async (text, optionId) => {
    if (!sessionId) return;

    if (text) {
      const userMsg = {
        id: 'user_' + Date.now(),
        sender: 'user',
        text: text,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages(prev => [...prev, userMsg]);
    } else if (optionId) {
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
          department_id: 'engineering',
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
          pdf_download_url: data.pdf_download_url,
          submission_guidance: data.submission_guidance,
          form_recommendation: data.form_recommendation,
          form_session_info: data.form_session_info,
        };
        setMessages(prev => [...prev, assistantMsg]);
      } else {
        const errData = await res.json().catch(() => ({}));
        const errorMsg = {
          id: 'err_' + Date.now(),
          sender: 'assistant',
          text: `⚠️ **Notice**: ${errData.detail || 'An error occurred while communicating with the service. Please retry.'}`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        };
        setMessages(prev => [...prev, errorMsg]);
      }
    } catch (err) {
      console.error('Chat error:', err);
      const errorMsg = {
        id: 'err_network_' + Date.now(),
        sender: 'assistant',
        text: '⚠️ **Network Notice**: Unable to contact backend API. Please ensure the backend server is running.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  // 3. Start Form Session directly via API or message
  const handleStartFormSession = async (formId) => {
    if (!sessionId) return;
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/form-session/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          form_id: formId,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        const asstMsg = {
          id: 'asst_' + Date.now(),
          sender: 'assistant',
          text: data.message,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          form_session_info: data.session_info,
        };
        setMessages(prev => [...prev, asstMsg]);
      } else {
        await handleSendMessage(`Yes, please help me fill out the ${formId} application.`);
      }
    } catch (err) {
      console.error('Start form error:', err);
      await handleSendMessage(`Yes, please help me fill out this application.`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleEditField = (fieldId) => {
    handleSendMessage(`edit ${fieldId}`);
  };

  // 4. Reset session
  const handleResetSession = async () => {
    if (!sessionId) return;
    try {
      await fetch(`${API_BASE}/api/flow/reset?session_id=${encodeURIComponent(sessionId)}`, {
        method: 'POST',
      });
      const resetMsg = {
        id: 'reset_' + Date.now(),
        sender: 'assistant',
        text: `CivicIQ\n\nMushkil Your Edison Township Buddy\n\nHow can **"CivicIQ"** help you today?`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        mode: 'general',
      };
      setMessages([resetMsg]);
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
      {/* Top Navigation Bar */}
      <header className="sticky top-0 z-40 bg-gradient-to-r from-blue-950 via-slate-900 to-blue-950 text-white shadow-md border-b border-blue-900">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          {/* Logo & Tagline */}
          <div className="flex items-center space-x-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-amber-400 to-amber-600 text-blue-950 font-black shadow-inner ring-2 ring-amber-300/40">
              <span className="text-base tracking-tighter">CIQ</span>
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-lg font-extrabold text-white tracking-tight leading-none">
                  CivicIQ
                </h1>
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
              </div>
              <p className="text-xs font-medium text-amber-300/90 tracking-wide">
                Mushkil Your Edison Township Buddy
              </p>
            </div>
          </div>

          <div className="text-right hidden sm:block">
            <span className="text-[11px] font-semibold text-blue-200 block">
              Township of Edison, NJ
            </span>
            <span className="text-[10px] text-slate-400">
              Department of Engineering
            </span>
          </div>
        </div>
      </header>

      {/* Centered Main Chat Assistant */}
      <main className="flex-1 max-w-4xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col">
        <ChatInterface
          messages={messages}
          isLoading={isLoading}
          onSendMessage={handleSendMessage}
          onResetSession={handleResetSession}
          onPreviewPdf={handleOpenPdfPreview}
          onStartSession={handleStartFormSession}
          onEditField={handleEditField}
        />
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-slate-200 py-3.5 px-6 text-center text-xs text-slate-500">
        <div className="max-w-4xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-1.5">
          <span className="flex items-center">
            <ShieldCheck className="h-4 w-4 mr-1.5 text-blue-700" />
            CivicIQ • Mushkil Your Edison Township Buddy • Edison Township Engineering
          </span>
          <span className="font-mono text-slate-400 text-[11px]">
            edisonnj.org/document_center
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
