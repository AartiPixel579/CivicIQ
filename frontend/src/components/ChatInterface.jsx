'use client';

import React, { useState, useRef, useEffect } from 'react';
import { 
  Send, RotateCcw, Bot, User, ShieldCheck, 
  HelpCircle, AlertCircle, FileText, CheckCircle2 
} from 'lucide-react';
import { FlowStepOptions } from './FlowStepOptions';
import { OfficialPdfCard } from './OfficialPdfCard';
import { RagCitationCard } from './RagCitationCard';

export const ChatInterface = ({
  messages = [],
  isLoading = false,
  activeDepartment,
  onSendMessage,
  onResetSession,
  onPreviewPdf,
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
                Pixelvyne Smart Assistant
              </h2>
              <span className="text-[10px] font-medium bg-blue-700/50 text-blue-200 px-2 py-0.5 rounded-full ring-1 ring-blue-500/40">
                Official Municipal Service Desk
              </span>
            </div>
            <p className="text-[11px] text-blue-200/80 flex items-center">
              Active Routing: <span className="font-semibold text-white ml-1">{activeDepartment?.name || 'All Municipal Departments'}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={onResetSession}
            className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-blue-800/80 hover:bg-blue-700 text-blue-100 text-xs font-medium transition-all"
            title="Reset active workflow and start fresh"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Reset Session</span>
          </button>
        </div>
      </div>

      {/* Rules Notice Strip */}
      <div className="px-5 py-1.5 bg-blue-50 border-b border-blue-100 flex items-center justify-between text-[11px] text-blue-900">
        <div className="flex items-center space-x-1.5 font-medium">
          <ShieldCheck className="h-3.5 w-3.5 text-blue-700" />
          <span>Strict Municipal Operating Rules: Grounded Link RAG & Official PDF Delivery Only</span>
        </div>
        <span className="text-blue-600 hidden md:inline">
          Counter intake verified under Municipal Code
        </span>
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
                  <p className="whitespace-pre-line">{msg.text}</p>

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
                  {msg.form_packet && (
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
              <span className="font-medium text-slate-600">Retrieving official municipal documentation & evaluating rules...</span>
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
