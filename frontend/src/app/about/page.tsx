'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Upload, FileText, Trash2, Send,
  Loader2, Bot, User, BookOpen, ChevronDown, ChevronUp,
  Sparkles, Database, Brain, AlertCircle, CheckCircle2,
  File, ArrowLeft, Wrench, MessageSquare, Search, Hash, BarChart2
} from 'lucide-react';
import Link from 'next/link';

// ─── Types ────────────────────────────────────────────────────────────────────

interface PDFDocument { document_name: string; chunk_count: number; }
interface Source { document_name: string; page_number: number; score: number; snippet: string; }
interface ChatMessage {
  id: string; role: 'user' | 'assistant';
  content: string; sources?: Source[];
  timestamp: Date; isLoading?: boolean;
}
interface ToolResult { document_name: string; page_number: number; score: number; text: string; }

const getBackendUrl = () => {
  if (typeof window === 'undefined') return 'http://localhost:8000/api/v1';
  return `http://localhost:8000/api/v1`;
};
const formatTime = (d: Date) => d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

// ─── Source Card (chat) ───────────────────────────────────────────────────────
function SourceCard({ source }: { source: Source }) {
  const [expanded, setExpanded] = useState(false);
  const pct = Math.round(source.score * 100);
  return (
    <div className="source-card">
      <button className="source-header" onClick={() => setExpanded(!expanded)}>
        <div className="source-meta">
          <FileText size={12} /><span className="source-name">{source.document_name}</span>
          <span className="source-page">p.{source.page_number}</span>
        </div>
        <div className="source-right">
          <div className="score-badge">{pct}%</div>
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </div>
      </button>
      {expanded && <p className="source-snippet">{source.snippet}</p>}
    </div>
  );
}

// ─── Tool Result Card ─────────────────────────────────────────────────────────
function ToolResultCard({ result, index }: { result: ToolResult; index: number }) {
  const [expanded, setExpanded] = useState(true);
  const pct = Math.round(result.score * 100);
  const barColor = pct >= 50 ? '#22c55e' : pct >= 30 ? '#f59e0b' : '#ef4444';
  return (
    <div className="tr-card">
      <div className="tr-header" onClick={() => setExpanded(!expanded)}>
        <div className="tr-left">
          <div className="tr-index">#{index + 1}</div>
          <div>
            <div className="tr-docname">{result.document_name}</div>
            <div className="tr-meta"><Hash size={11} /> Page {result.page_number}</div>
          </div>
        </div>
        <div className="tr-right">
          <div className="tr-score-wrap">
            <div className="tr-score-bar">
              <div className="tr-score-fill" style={{ width: `${pct}%`, background: barColor }} />
            </div>
            <span className="tr-score-num" style={{ color: barColor }}>{pct}%</span>
          </div>
          {expanded ? <ChevronUp size={13} style={{ color: '#475569' }} /> : <ChevronDown size={13} style={{ color: '#475569' }} />}
        </div>
      </div>
      {expanded && (
        <div className="tr-body">
          <div className="tr-text-label">Extracted Chunk Text</div>
          <div className="tr-text">{result.text}</div>
        </div>
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function AboutPage() {
  const backendUrl = getBackendUrl();
  const [activeTab, setActiveTab] = useState<'chat' | 'tool'>('chat');

  // PDF state
  const [documents, setDocuments] = useState<PDFDocument[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [docsLoading, setDocsLoading] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Chat state
  const [messages, setMessages] = useState<ChatMessage[]>([{
    id: 'welcome', role: 'assistant',
    content: '👋 Upload a PDF on the left, then ask me anything about its content!',
    timestamp: new Date(),
  }]);
  const [input, setInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Tool tester state
  const [toolQuery, setToolQuery] = useState('');
  const [toolLoading, setToolLoading] = useState(false);
  const [toolResults, setToolResults] = useState<ToolResult[] | null>(null);
  const [toolError, setToolError] = useState<string | null>(null);
  const [toolQueryTime, setToolQueryTime] = useState<number | null>(null);

  const fetchDocuments = useCallback(async () => {
    try {
      const res = await fetch(`${backendUrl}/testing/documents`);
      const data = await res.json();
      if (data.success) setDocuments(data.data);
    } catch { } finally { setDocsLoading(false); }
  }, [backendUrl]);

  useEffect(() => { fetchDocuments(); }, [fetchDocuments]);
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const handleUpload = async (file: File) => {
    if (!file.name.endsWith('.pdf')) {
      setUploadStatus({ type: 'error', msg: 'Only PDF files supported.' });
      setTimeout(() => setUploadStatus(null), 4000); return;
    }
    setUploading(true); setUploadStatus(null);
    const fd = new FormData(); fd.append('file', file);
    try {
      const res = await fetch(`${backendUrl}/testing/upload-pdf`, { method: 'POST', body: fd });
      const data = await res.json();
      if (data.success) { setUploadStatus({ type: 'success', msg: data.message }); await fetchDocuments(); }
      else setUploadStatus({ type: 'error', msg: data.message || 'Upload failed.' });
    } catch { setUploadStatus({ type: 'error', msg: 'Network error. Is backend running?' }); }
    finally { setUploading(false); setTimeout(() => setUploadStatus(null), 5000); }
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (f) handleUpload(f); e.target.value = '';
  };
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault(); setIsDragging(false);
    const f = e.dataTransfer.files?.[0]; if (f) handleUpload(f);
  };
  const handleDelete = async (name: string) => {
    try {
      await fetch(`${backendUrl}/testing/documents/${encodeURIComponent(name)}`, { method: 'DELETE' });
      setDocuments(p => p.filter(d => d.document_name !== name));
    } catch { }
  };

  const handleSend = async () => {
    const q = input.trim(); if (!q || chatLoading) return;
    setMessages(p => [...p,
      { id: `u-${Date.now()}`, role: 'user', content: q, timestamp: new Date() },
      { id: `l-${Date.now()}`, role: 'assistant', content: '', timestamp: new Date(), isLoading: true },
    ]);
    setInput(''); setChatLoading(true);
    try {
      const res = await fetch(`${backendUrl}/testing/chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
      });
      const data = await res.json();
      setMessages(p => [...p.filter(m => !m.isLoading), {
        id: `b-${Date.now()}`, role: 'assistant',
        content: data.success ? data.answer : (data.message || 'Error.'),
        sources: data.sources || [], timestamp: new Date(),
      }]);
    } catch {
      setMessages(p => [...p.filter(m => !m.isLoading), {
        id: `e-${Date.now()}`, role: 'assistant', content: '❌ Network error.', timestamp: new Date(),
      }]);
    } finally { setChatLoading(false); }
  };

  const handleToolSearch = async () => {
    const q = toolQuery.trim(); if (!q || toolLoading) return;
    setToolLoading(true); setToolResults(null); setToolError(null); setToolQueryTime(null);
    const t0 = performance.now();
    try {
      const res = await fetch(`${backendUrl}/testing/chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
      });
      const data = await res.json();
      const elapsed = Math.round(performance.now() - t0);
      setToolQueryTime(elapsed);
      if (data.success) {
        const results: ToolResult[] = (data.sources || []).map((s: any) => ({
          document_name: s.document_name,
          page_number: s.page_number,
          score: s.score,
          text: s.snippet,
        }));
        setToolResults(results);
      } else {
        setToolError(data.message || 'Search failed.');
      }
    } catch { setToolError('Network error. Is backend running?'); }
    finally { setToolLoading(false); }
  };

  return (
    <>
      <style>{`
        .about-root { min-height:100vh; background:radial-gradient(circle at top left,#0f172a 0%,#1e1b4b 50%,#090d16 100%); color:#f8fafc; font-family:'Inter',system-ui,sans-serif; display:flex; flex-direction:column; }
        .about-header { display:flex; align-items:center; justify-content:space-between; padding:0.85rem 2rem; border-bottom:1px solid rgba(99,102,241,0.2); background:rgba(15,23,42,0.6); backdrop-filter:blur(16px); position:sticky; top:0; z-index:10; }
        .header-left { display:flex; align-items:center; gap:0.75rem; }
        .back-btn { display:flex; align-items:center; gap:0.4rem; color:#94a3b8; text-decoration:none; font-size:0.82rem; padding:0.35rem 0.75rem; border-radius:8px; border:1px solid rgba(255,255,255,0.1); transition:all 0.2s; }
        .back-btn:hover { color:#f8fafc; border-color:rgba(99,102,241,0.4); }
        .header-title { display:flex; align-items:center; gap:0.5rem; font-size:1rem; font-weight:700; background:linear-gradient(135deg,#818cf8,#a78bfa); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
        .chips { display:flex; gap:0.4rem; }
        .chip { display:flex; align-items:center; gap:0.3rem; font-size:0.7rem; padding:0.25rem 0.6rem; border-radius:999px; border:1px solid rgba(255,255,255,0.1); background:rgba(30,41,59,0.6); color:#94a3b8; }
        .chip-dot { width:6px; height:6px; border-radius:50%; background:#22c55e; animation:pulse 2s infinite; }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
        @keyframes spin { to{transform:rotate(360deg)} }
        @keyframes fadeUp { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }
        @keyframes bounce { 0%,60%,100%{transform:translateY(0)} 30%{transform:translateY(-7px)} }
        @keyframes shimmer { 0%{opacity:0.6}50%{opacity:1}100%{opacity:0.6} }

        .about-main { display:grid; grid-template-columns:330px 1fr; flex:1; height:calc(100vh - 58px); overflow:hidden; }

        .left-panel { border-right:1px solid rgba(99,102,241,0.15); display:flex; flex-direction:column; overflow:hidden; background:rgba(15,23,42,0.4); }
        .panel-header { padding:1rem 1.2rem 0.8rem; border-bottom:1px solid rgba(255,255,255,0.05); }
        .panel-title { font-size:0.85rem; font-weight:600; color:#c4b5fd; display:flex; align-items:center; gap:0.4rem; margin-bottom:0.2rem; }
        .panel-sub { font-size:0.72rem; color:#64748b; }
        .dropzone { margin:0.85rem 1.1rem; border:2px dashed rgba(99,102,241,0.35); border-radius:12px; padding:1.2rem 1rem; text-align:center; cursor:pointer; transition:all 0.25s; background:rgba(99,102,241,0.04); position:relative; }
        .dropzone:hover,.dropzone.drag { border-color:#6366f1; background:rgba(99,102,241,0.1); box-shadow:0 4px 20px rgba(99,102,241,0.12); }
        .dz-icon { display:flex; align-items:center; justify-content:center; width:40px; height:40px; border-radius:10px; background:rgba(99,102,241,0.15); margin:0 auto 0.55rem; }
        .dz-text { font-size:0.8rem; color:#cbd5e1; font-weight:500; margin-bottom:0.2rem; }
        .dz-hint { font-size:0.68rem; color:#475569; }
        .upload-bar { position:absolute; bottom:0; left:0; right:0; height:3px; background:linear-gradient(90deg,#6366f1,#a78bfa); border-radius:0 0 10px 10px; animation:shimmer 1.2s infinite; }
        .status-msg { margin:0 1.1rem; padding:0.5rem 0.8rem; border-radius:9px; font-size:0.74rem; display:flex; align-items:flex-start; gap:0.4rem; line-height:1.4; }
        .status-msg.success { background:rgba(34,197,94,0.1); border:1px solid rgba(34,197,94,0.2); color:#86efac; }
        .status-msg.error { background:rgba(239,68,68,0.1); border:1px solid rgba(239,68,68,0.2); color:#fca5a5; }
        .docs-section { flex:1; overflow-y:auto; padding:0.5rem 1.1rem 1rem; }
        .docs-section::-webkit-scrollbar { width:4px; }
        .docs-section::-webkit-scrollbar-thumb { background:rgba(99,102,241,0.3); border-radius:4px; }
        .docs-label { font-size:0.67rem; color:#475569; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:0.5rem; padding-bottom:0.35rem; border-bottom:1px solid rgba(255,255,255,0.05); }
        .doc-item { display:flex; align-items:center; gap:0.5rem; padding:0.6rem 0.65rem; border-radius:9px; border:1px solid rgba(255,255,255,0.06); background:rgba(30,41,59,0.5); margin-bottom:0.4rem; transition:all 0.2s; }
        .doc-item:hover { border-color:rgba(99,102,241,0.3); }
        .doc-icon { width:28px; height:28px; border-radius:7px; background:rgba(99,102,241,0.15); display:flex; align-items:center; justify-content:center; flex-shrink:0; color:#818cf8; }
        .doc-info { flex:1; min-width:0; }
        .doc-name { font-size:0.77rem; color:#e2e8f0; font-weight:500; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .doc-chunks { font-size:0.67rem; color:#64748b; }
        .doc-del { background:none; border:none; color:#475569; cursor:pointer; padding:0.25rem; border-radius:5px; transition:all 0.2s; }
        .doc-del:hover { color:#ef4444; background:rgba(239,68,68,0.1); }
        .docs-empty { text-align:center; padding:1.8rem 1rem; color:#475569; font-size:0.77rem; }
        .docs-empty-icon { margin:0 auto 0.6rem; width:36px; height:36px; border-radius:9px; background:rgba(255,255,255,0.04); display:flex; align-items:center; justify-content:center; }

        .right-panel { display:flex; flex-direction:column; overflow:hidden; }
        .tab-bar { display:flex; border-bottom:1px solid rgba(99,102,241,0.15); background:rgba(15,23,42,0.5); padding:0 1.25rem; }
        .tab-btn { display:flex; align-items:center; gap:0.4rem; padding:0.72rem 1rem; font-size:0.82rem; font-weight:500; background:none; border:none; color:#64748b; cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-1px; transition:all 0.2s; }
        .tab-btn:hover { color:#94a3b8; }
        .tab-btn.active { color:#818cf8; border-bottom-color:#6366f1; }

        .chat-messages { flex:1; overflow-y:auto; padding:1.2rem; display:flex; flex-direction:column; gap:0.85rem; }
        .chat-messages::-webkit-scrollbar { width:4px; }
        .chat-messages::-webkit-scrollbar-thumb { background:rgba(99,102,241,0.25); border-radius:4px; }
        .msg-row { display:flex; gap:0.6rem; align-items:flex-start; animation:fadeUp 0.25s ease; }
        .msg-row.user { flex-direction:row-reverse; }
        .avatar { width:30px; height:30px; border-radius:8px; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
        .avatar.bot { background:linear-gradient(135deg,#4f46e5,#7c3aed); }
        .avatar.uav { background:linear-gradient(135deg,#0ea5e9,#6366f1); }
        .bubble-wrap { max-width:78%; }
        .bubble { padding:0.75rem 0.95rem; border-radius:13px; font-size:0.84rem; line-height:1.65; white-space:pre-wrap; }
        .bubble.bot-b { background:rgba(30,41,59,0.8); border:1px solid rgba(99,102,241,0.18); border-top-left-radius:4px; color:#e2e8f0; }
        .bubble.user-b { background:linear-gradient(135deg,#4338ca,#5b21b6); border-top-right-radius:4px; color:#fff; margin-left:auto; }
        .msg-time { font-size:0.64rem; color:#475569; margin-top:0.25rem; padding:0 0.2rem; }
        .msg-row.user .msg-time { text-align:right; }
        .ldots { display:flex; gap:5px; align-items:center; padding:0.3rem 0; }
        .ldots span { width:6px; height:6px; border-radius:50%; background:#6366f1; animation:bounce 1.2s infinite; }
        .ldots span:nth-child(2){animation-delay:.2s} .ldots span:nth-child(3){animation-delay:.4s}
        .sources-section { margin-top:0.45rem; }
        .sources-title { font-size:0.66rem; color:#64748b; text-transform:uppercase; letter-spacing:0.07em; margin-bottom:0.3rem; }
        .source-card { border:1px solid rgba(255,255,255,0.07); border-radius:7px; background:rgba(15,23,42,0.5); margin-bottom:0.28rem; overflow:hidden; }
        .source-header { display:flex; align-items:center; justify-content:space-between; padding:0.38rem 0.55rem; cursor:pointer; background:none; border:none; color:#94a3b8; width:100%; transition:background 0.15s; }
        .source-header:hover { background:rgba(99,102,241,0.06); }
        .source-meta { display:flex; align-items:center; gap:0.3rem; font-size:0.69rem; min-width:0; }
        .source-name { max-width:140px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .source-page { color:#64748b; }
        .source-right { display:flex; align-items:center; gap:0.3rem; flex-shrink:0; }
        .score-badge { font-size:0.63rem; padding:0.1rem 0.38rem; border-radius:999px; background:rgba(99,102,241,0.15); color:#818cf8; border:1px solid rgba(99,102,241,0.2); }
        .source-snippet { font-size:0.72rem; color:#64748b; padding:0.4rem 0.6rem; border-top:1px solid rgba(255,255,255,0.05); line-height:1.55; margin:0; }

        .chat-input-bar { padding:0.85rem 1.2rem; border-top:1px solid rgba(99,102,241,0.15); background:rgba(15,23,42,0.5); backdrop-filter:blur(12px); }
        .chat-input-wrap { display:flex; align-items:flex-end; gap:0.6rem; background:rgba(30,41,59,0.7); border:1px solid rgba(99,102,241,0.25); border-radius:11px; padding:0.5rem 0.65rem; transition:border-color 0.2s,box-shadow 0.2s; }
        .chat-input-wrap:focus-within { border-color:#6366f1; box-shadow:0 0 0 3px rgba(99,102,241,0.1); }
        .chat-textarea { flex:1; background:transparent; border:none; outline:none; color:#f1f5f9; font-size:0.84rem; line-height:1.5; resize:none; max-height:100px; overflow-y:auto; font-family:inherit; }
        .chat-textarea::placeholder { color:#475569; }
        .send-btn { width:32px; height:32px; border-radius:8px; border:none; background:linear-gradient(135deg,#4f46e5,#7c3aed); color:white; cursor:pointer; display:flex; align-items:center; justify-content:center; flex-shrink:0; transition:all 0.2s; }
        .send-btn:hover:not(:disabled) { transform:translateY(-1px); box-shadow:0 4px 12px rgba(99,102,241,0.35); }
        .send-btn:disabled { opacity:0.4; cursor:not-allowed; }
        .input-hint { font-size:0.65rem; color:#475569; text-align:center; margin-top:0.4rem; }

        .tool-panel { flex:1; display:flex; flex-direction:column; overflow:hidden; }
        .tool-search-bar { padding:1rem 1.2rem; border-bottom:1px solid rgba(99,102,241,0.12); background:rgba(15,23,42,0.3); }
        .tool-search-label { font-size:0.71rem; color:#64748b; margin-bottom:0.5rem; display:flex; align-items:center; gap:0.35rem; }
        .tool-input-row { display:flex; gap:0.55rem; }
        .tool-input { flex:1; background:rgba(30,41,59,0.7); border:1px solid rgba(99,102,241,0.25); border-radius:9px; padding:0.58rem 0.8rem; color:#f1f5f9; font-size:0.84rem; font-family:inherit; outline:none; transition:border-color 0.2s,box-shadow 0.2s; }
        .tool-input:focus { border-color:#6366f1; box-shadow:0 0 0 3px rgba(99,102,241,0.1); }
        .tool-input::placeholder { color:#475569; }
        .tool-search-btn { display:flex; align-items:center; gap:0.4rem; padding:0.58rem 1rem; border-radius:9px; border:none; background:linear-gradient(135deg,#4f46e5,#7c3aed); color:white; font-size:0.8rem; font-weight:600; cursor:pointer; transition:all 0.2s; white-space:nowrap; }
        .tool-search-btn:hover:not(:disabled) { transform:translateY(-1px); box-shadow:0 4px 14px rgba(99,102,241,0.35); }
        .tool-search-btn:disabled { opacity:0.45; cursor:not-allowed; }
        .tool-results-area { flex:1; overflow-y:auto; padding:1rem 1.2rem; }
        .tool-results-area::-webkit-scrollbar { width:4px; }
        .tool-results-area::-webkit-scrollbar-thumb { background:rgba(99,102,241,0.25); border-radius:4px; }
        .tool-meta-bar { display:flex; align-items:center; justify-content:space-between; margin-bottom:0.85rem; padding:0.5rem 0.7rem; background:rgba(99,102,241,0.06); border:1px solid rgba(99,102,241,0.15); border-radius:8px; }
        .tool-meta-left { display:flex; align-items:center; gap:0.5rem; font-size:0.74rem; color:#94a3b8; flex-wrap:wrap; }
        .tool-meta-count { font-size:0.7rem; color:#818cf8; background:rgba(99,102,241,0.15); padding:0.12rem 0.45rem; border-radius:999px; }
        .tool-meta-time { font-size:0.68rem; color:#64748b; }
        .tool-empty { text-align:center; padding:3rem 1rem; color:#475569; }
        .tool-empty-icon { margin:0 auto 0.7rem; width:46px; height:46px; border-radius:12px; background:rgba(255,255,255,0.03); display:flex; align-items:center; justify-content:center; }
        .tool-empty-title { font-size:0.84rem; color:#64748b; margin-bottom:0.35rem; }
        .tool-empty-sub { font-size:0.72rem; color:#334155; line-height:1.7; }
        .tool-error { margin-bottom:0.75rem; padding:0.6rem 0.85rem; border-radius:9px; background:rgba(239,68,68,0.1); border:1px solid rgba(239,68,68,0.2); color:#fca5a5; font-size:0.79rem; display:flex; align-items:center; gap:0.45rem; }
        .tr-card { border:1px solid rgba(255,255,255,0.07); border-radius:10px; background:rgba(20,30,50,0.7); margin-bottom:0.6rem; overflow:hidden; animation:fadeUp 0.25s ease; }
        .tr-header { display:flex; align-items:center; justify-content:space-between; padding:0.62rem 0.8rem; cursor:pointer; transition:background 0.15s; }
        .tr-header:hover { background:rgba(99,102,241,0.05); }
        .tr-left { display:flex; align-items:center; gap:0.55rem; }
        .tr-index { font-size:0.68rem; font-weight:700; color:#6366f1; background:rgba(99,102,241,0.12); padding:0.18rem 0.42rem; border-radius:5px; }
        .tr-docname { font-size:0.79rem; color:#e2e8f0; font-weight:500; }
        .tr-meta { display:flex; align-items:center; gap:0.25rem; font-size:0.67rem; color:#64748b; margin-top:0.12rem; }
        .tr-right { display:flex; align-items:center; gap:0.55rem; }
        .tr-score-wrap { display:flex; align-items:center; gap:0.38rem; }
        .tr-score-bar { width:55px; height:5px; background:rgba(255,255,255,0.08); border-radius:999px; overflow:hidden; }
        .tr-score-fill { height:100%; border-radius:999px; transition:width 0.4s ease; }
        .tr-score-num { font-size:0.7rem; font-weight:600; min-width:28px; text-align:right; }
        .tr-body { padding:0 0.8rem 0.65rem; border-top:1px solid rgba(255,255,255,0.05); }
        .tr-text-label { font-size:0.65rem; color:#475569; text-transform:uppercase; letter-spacing:0.07em; padding:0.45rem 0 0.3rem; }
        .tr-text { font-size:0.79rem; color:#94a3b8; line-height:1.65; background:rgba(15,23,42,0.5); padding:0.6rem 0.7rem; border-radius:7px; border:1px solid rgba(255,255,255,0.05); white-space:pre-wrap; }
      `}</style>

      <div className="about-root">
        <header className="about-header">
          <div className="header-left">
            <Link href="/" className="back-btn"><ArrowLeft size={13} /> Back</Link>
            <div className="header-title"><Brain size={16} /> PDF Knowledge Chatbot</div>
          </div>
          <div className="chips">
            <div className="chip"><div className="chip-dot" /><Database size={11} /> Qdrant</div>
            <div className="chip"><Sparkles size={11} /> OpenAI RAG</div>
          </div>
        </header>

        <main className="about-main">
          {/* Left: PDF Upload */}
          <aside className="left-panel">
            <div className="panel-header">
              <div className="panel-title"><BookOpen size={13} /> Knowledge Base</div>
              <div className="panel-sub">Upload PDFs to train the chatbot</div>
            </div>
            <div
              className={`dropzone${isDragging ? ' drag' : ''}`}
              onClick={() => fileInputRef.current?.click()}
              onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={onDrop}
            >
              <div className="dz-icon">
                {uploading
                  ? <Loader2 size={19} color="#818cf8" style={{ animation: 'spin 1s linear infinite' }} />
                  : <Upload size={19} color="#818cf8" />}
              </div>
              <div className="dz-text">{uploading ? 'Uploading & embedding...' : 'Drop PDF or click to browse'}</div>
              <div className="dz-hint">PDF files only</div>
              {uploading && <div className="upload-bar" />}
              <input ref={fileInputRef} type="file" accept=".pdf" style={{ display: 'none' }} onChange={onFileChange} />
            </div>

            {uploadStatus && (
              <div className={`status-msg ${uploadStatus.type}`}>
                {uploadStatus.type === 'success'
                  ? <CheckCircle2 size={13} style={{ flexShrink: 0, marginTop: 1 }} />
                  : <AlertCircle size={13} style={{ flexShrink: 0, marginTop: 1 }} />}
                {uploadStatus.msg}
              </div>
            )}

            <div className="docs-section">
              <div className="docs-label">Uploaded ({documents.length})</div>
              {docsLoading ? (
                <div className="docs-empty">
                  <Loader2 size={17} style={{ margin: '0 auto 0.5rem', display: 'block', animation: 'spin 1s linear infinite', color: '#475569' }} />
                  Loading...
                </div>
              ) : documents.length === 0 ? (
                <div className="docs-empty">
                  <div className="docs-empty-icon"><FileText size={15} color="#334155" /></div>
                  No documents yet.<br />Upload a PDF to start.
                </div>
              ) : documents.map(doc => (
                <div className="doc-item" key={doc.document_name}>
                  <div className="doc-icon"><File size={12} /></div>
                  <div className="doc-info">
                    <div className="doc-name" title={doc.document_name}>{doc.document_name}</div>
                    <div className="doc-chunks">{doc.chunk_count} chunks</div>
                  </div>
                  <button className="doc-del" onClick={() => handleDelete(doc.document_name)} title="Delete"><Trash2 size={12} /></button>
                </div>
              ))}
            </div>
          </aside>

          {/* Right: Tabs */}
          <section className="right-panel">
            <div className="tab-bar">
              <button className={`tab-btn${activeTab === 'chat' ? ' active' : ''}`} onClick={() => setActiveTab('chat')}>
                <MessageSquare size={13} /> Chat
              </button>
              <button className={`tab-btn${activeTab === 'tool' ? ' active' : ''}`} onClick={() => setActiveTab('tool')}>
                <Wrench size={13} /> Tool Tester
              </button>
            </div>

            {/* ── Chat Tab ── */}
            {activeTab === 'chat' && (
              <>
                <div className="chat-messages">
                  {messages.map(msg => (
                    <div className={`msg-row${msg.role === 'user' ? ' user' : ''}`} key={msg.id}>
                      <div className={`avatar ${msg.role === 'user' ? 'uav' : 'bot'}`}>
                        {msg.role === 'user' ? <User size={14} /> : <Bot size={14} />}
                      </div>
                      <div className="bubble-wrap">
                        <div className={`bubble ${msg.role === 'user' ? 'user-b' : 'bot-b'}`}>
                          {msg.isLoading ? <div className="ldots"><span /><span /><span /></div> : msg.content}
                        </div>
                        {msg.sources && msg.sources.length > 0 && (
                          <div className="sources-section">
                            <div className="sources-title">📎 Sources ({msg.sources.length})</div>
                            {msg.sources.map((s, i) => <SourceCard key={i} source={s} />)}
                          </div>
                        )}
                        <div className="msg-time">{formatTime(msg.timestamp)}</div>
                      </div>
                    </div>
                  ))}
                  <div ref={chatEndRef} />
                </div>
                <div className="chat-input-bar">
                  <div className="chat-input-wrap">
                    <textarea
                      className="chat-textarea"
                      placeholder="Ask anything about your PDFs..."
                      value={input} rows={1}
                      onChange={e => setInput(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                    />
                    <button className="send-btn" onClick={handleSend} disabled={chatLoading || !input.trim()}>
                      {chatLoading ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Send size={14} />}
                    </button>
                  </div>
                  <div className="input-hint">Enter to send · Shift+Enter for new line</div>
                </div>
              </>
            )}

            {/* ── Tool Tester Tab ── */}
            {activeTab === 'tool' && (
              <div className="tool-panel">
                <div className="tool-search-bar">
                  <div className="tool-search-label">
                    <Wrench size={12} />
                    <span><strong style={{ color: '#818cf8' }}>search_pdf_knowledge</strong> — Raw Qdrant vector search results (top 5)</span>
                  </div>
                  <div className="tool-input-row">
                    <input
                      className="tool-input"
                      placeholder='e.g. "desserts", "breakfast items", "cold beverages price"'
                      value={toolQuery}
                      onChange={e => setToolQuery(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') handleToolSearch(); }}
                    />
                    <button className="tool-search-btn" onClick={handleToolSearch} disabled={toolLoading || !toolQuery.trim()}>
                      {toolLoading
                        ? <><Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> Searching...</>
                        : <><Search size={13} /> Search</>}
                    </button>
                  </div>
                </div>

                <div className="tool-results-area">
                  {toolError && <div className="tool-error"><AlertCircle size={13} />{toolError}</div>}

                  {toolResults !== null && (
                    <>
                      <div className="tool-meta-bar">
                        <div className="tool-meta-left">
                          <BarChart2 size={13} />
                          Query: <strong style={{ color: '#e2e8f0' }}>"{toolQuery}"</strong>
                          <span className="tool-meta-count">{toolResults.length} chunks returned</span>
                        </div>
                        {toolQueryTime !== null && <span className="tool-meta-time">⏱ {toolQueryTime}ms</span>}
                      </div>
                      {toolResults.length === 0 ? (
                        <div className="tool-empty">
                          <div className="tool-empty-icon"><Search size={19} color="#334155" /></div>
                          <div className="tool-empty-title">No results found</div>
                          <div className="tool-empty-sub">Try a different query or upload more documents.</div>
                        </div>
                      ) : toolResults.map((r, i) => <ToolResultCard key={i} result={r} index={i} />)}
                    </>
                  )}

                  {toolResults === null && !toolError && !toolLoading && (
                    <div className="tool-empty">
                      <div className="tool-empty-icon"><Wrench size={19} color="#334155" /></div>
                      <div className="tool-empty-title">Tool Tester</div>
                      <div className="tool-empty-sub">
                        Type any query to see exactly what the <strong style={{ color: '#818cf8' }}>search_pdf_knowledge</strong> AI tool returns from Qdrant.<br /><br />
                        Each result shows: <strong style={{ color: '#94a3b8' }}>document · page · similarity score · raw text chunk</strong> — exactly what the AI sees.
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </section>
        </main>
      </div>
    </>
  );
}
