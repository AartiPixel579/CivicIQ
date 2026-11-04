'use client';

import React, { useState, useRef, useEffect } from 'react';
import { 
  Send, RotateCcw, Bot, User, ShieldCheck, 
  HelpCircle, AlertCircle, FileText, CheckCircle2 
} from 'lucide-react';
import { FlowStepOptions } from './FlowStepOptions';
import { OfficialPdfCard } from './OfficialPdfCard';
import { RagCitationCard } from './RagCitationCard';
import { FormSessionCard } from './FormSessionCard';

export const renderFormattedText = (text) => {
  if (!text) return null;
  const paragraphs = text.split('\n');

  return paragraphs.map((paragraph, pIdx) => {
    const parts = [];
    const regex = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;
    let lastIndex = 0;
    let match;
    let keyIdx = 0;

    while ((match = regex.exec(paragraph)) !== null) {
      if (match.index > lastIndex) {
        parts.push(paragraph.substring(lastIndex, match.index));
      }
      const token = match[0];
      if (token.startsWith('**') && token.endsWith('**')) {
        parts.push(
          <strong key={`b-${pIdx}-${keyIdx++}`} className="font-bold text-inherit">
            {token.slice(2, -2)}
          </strong>
        );
      } else if (token.startsWith('`') && token.endsWith('`')) {
        parts.push(
          <code key={`c-${pIdx}-${keyIdx++}`} className="bg-slate-100 px-1 py-0.5 rounded text-[11px] font-mono text-slate-800">
            {token.slice(1, -1)}
          </code>
        );
      } else if (token.startsWith('[') && token.includes('](')) {
        const linkText = token.substring(1, token.indexOf(']('));
        const linkUrl = token.substring(token.indexOf('](') + 2, token.length - 1);
        parts.push(
          <a
            key={`a-${pIdx}-${keyIdx++}`}
            href={linkUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 underline hover:text-blue-800 font-medium"
          >
            {linkText}
          </a>
        );
      }
      lastIndex = regex.lastIndex;
    }

    if (lastIndex < paragraph.length) {
      parts.push(paragraph.substring(lastIndex));
    }

    return (
      <span key={`p-${pIdx}`} className="block min-h-[1em]">
        {parts.length > 0 ? parts : paragraph}
      </span>
    );
  });
};

export const ChatInterface = ({
  messages = [],
  isLoading = false,
  activeDepartment,
  onSendMessage,
  onResetSession,
  onPreviewPdf,
  onStartSession,
  onEditField,
}) => {
  const [inputText, setInputText] = useState('');
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!inputText.trim() || isLoading) return;
    const text = inputText;
    setInputText('');
    onSendMessage(text);
  };

  const handleSelectOption = (optionId) => {
    if (isLoading) return;
    onSendMessage('', optionId);
  };

  return (
    <div className="flex-1 flex flex-col bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden min-h-[600px] max-h-[85vh]">
      {/* Assistant Header Banner */}
      <div className="px-5 py-3.5 bg-gradient-to-r from-blue-900 via-blue-800 to-indigo-900 text-white flex items-center justify-between shadow-sm">
        <div className="flex items-center space-x-3">
          <div className="relative">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-700/80 text-amber-300 ring-1 ring-blue-500">
              <Bot className="h-5 w-5" />
            </div>
            <span className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full bg-emerald-500 ring-2 ring-blue-900" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h2 className="text-sm font-bold text-white tracking-wide">
                CivicIQ
              </h2>
              <span className="text-[10px] font-medium bg-amber-400/20 text-amber-300 px-2 py-0.5 rounded-full ring-1 ring-amber-400/40">
                Mushkil Your Edison Township Buddy
              </span>
            </div>
            <p className="text-[11px] text-blue-200/80 flex items-center">
              <span>Township of Edison • Department of Engineering</span>
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={onResetSession}
            className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-blue-800/80 hover:bg-blue-700 text-blue-100 text-xs font-medium transition-all"
            title="Reset conversation"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Reset</span>
          </button>
        </div>
      </div>

      {/* Chat Messages Log */}
      <div className="flex-1 overflow-y-auto p-5 space-y-4 bg-slate-50/40">
        {messages.map((msg, idx) => {
          const isUser = msg.sender === 'user';

          return (
            <div
              key={msg.id || idx}
              className={`flex items-start space-x-3 ${isUser ? 'flex-row-reverse space-x-reverse' : ''}`}
            >
              {/* Avatar */}
              <div
                className={`flex h-8 w-8 items-center justify-center rounded-xl flex-shrink-0 text-xs font-bold ${
                  isUser
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'bg-gradient-to-br from-blue-800 to-indigo-900 text-amber-300 shadow-sm ring-1 ring-blue-700'
                }`}
              >
                {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
              </div>

              {/* Message Content */}
              <div className={`max-w-[85%] md:max-w-[80%] ${isUser ? 'text-right' : 'text-left'}`}>
                <div
                  className={`inline-block p-4 rounded-2xl text-xs leading-relaxed text-left shadow-sm ${
                    isUser
                      ? 'bg-blue-700 text-white rounded-tr-none'
                      : 'bg-white border border-slate-200 text-slate-800 rounded-tl-none'
                  }`}
                >
                  <div className="space-y-1">
                    {renderFormattedText(msg.text)}
                  </div>

                  {/* Form Recommendation */}
                  {msg.form_recommendation && (
                    <FormSessionCard
                      recommendation={msg.form_recommendation}
                      onStartSession={onStartSession}
                    />
                  )}

                  {/* Active Form Session Progress */}
                  {msg.form_session_info && !msg.pdf_download_url && (
                    <FormSessionCard
                      sessionInfo={msg.form_session_info}
                      onEditField={onEditField}
                    />
                  )}

                  {/* Generated PDF Download & Signature Guidance Card */}
                  {(msg.pdf_download_url || (msg.form_session_info && msg.form_session_info.is_complete)) && (
                    <FormSessionCard
                      pdfUrl={msg.pdf_download_url}
                      submissionGuidance={msg.submission_guidance}
                      sessionInfo={msg.form_session_info}
                      onPreviewPdf={onPreviewPdf}
                    />
                  )}

                  {/* Flowchart Decision Step Options */}
                  {msg.options && msg.options.length > 0 && !msg.completed && (
                    <FlowStepOptions
                      options={msg.options}
                      onSelectOption={handleSelectOption}
                      isMandatoryPrerequisite={msg.current_step?.is_mandatory_prerequisite}
                      disabled={isLoading}
                    />
                  )}

                  {/* Official PDF Document Delivery Card */}
                  {msg.form_packet && !msg.pdf_download_url && (
                    <OfficialPdfCard
                      formPacket={msg.form_packet}
                      onPreview={onPreviewPdf}
                    />
                  )}

                  {/* Grounded Link Citations */}
                  {msg.citations && msg.citations.length > 0 && (
                    <RagCitationCard citations={msg.citations} />
                  )}
                </div>

                {/* Message Timestamp */}
                <div className={`mt-1 text-[10px] text-slate-400 ${isUser ? 'text-right' : 'text-left'}`}>
                  {msg.timestamp || 'Just now'}
                </div>
              </div>
            </div>
          );
        })}

        {/* Loading Indicator */}
        {isLoading && (
          <div className="flex items-center space-x-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-blue-900 text-amber-300 ring-1 ring-blue-700 flex-shrink-0">
              <Bot className="h-4 w-4 animate-spin" />
            </div>
            <div className="p-3.5 rounded-2xl rounded-tl-none bg-white border border-slate-200 text-xs text-slate-500 shadow-sm flex items-center space-x-2">
              <div className="flex space-x-1">
                <span className="h-2 w-2 rounded-full bg-blue-600 animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="h-2 w-2 rounded-full bg-blue-600 animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="h-2 w-2 rounded-full bg-blue-600 animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span className="font-medium text-slate-600">Mushkil is consulting official Edison Township engineering records...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Bar */}
      <div className="p-3 bg-white border-t border-slate-200">
        <form onSubmit={handleSubmit} className="flex items-center space-x-2">
          <input
            ref={inputRef}
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            disabled={isLoading}
            placeholder={
              activeDepartment
                ? `Ask ${activeDepartment.short_name} or enter procedure keyword (e.g. "apply for building permit", "setbacks", "fees")...`
                : "Ask any municipal inquiry or request a permit procedure..."
            }
            className="flex-1 px-4 py-2.5 rounded-xl border border-slate-300 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-transparent bg-slate-50 focus:bg-white transition-all"
          />
          <button
            type="submit"
            disabled={!inputText.trim() || isLoading}
            className="inline-flex items-center justify-center px-4 py-2.5 rounded-xl bg-blue-700 hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-semibold shadow-sm transition-all focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <span>Send</span>
            <Send className="ml-1.5 h-3.5 w-3.5" />
          </button>
        </form>
        <div className="mt-1.5 flex items-center justify-between text-[11px] text-slate-400 px-1">
          <span>Type <code className="bg-slate-100 text-slate-600 px-1 py-0.5 rounded font-mono">/reset</code> to restart flow</span>
          <span>Municipal Records Portal • Revision 2026</span>
        </div>
      </div>
    </div>
  );
};
