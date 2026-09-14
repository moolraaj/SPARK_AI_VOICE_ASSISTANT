'use client';

import React, { useState, useMemo, useEffect } from 'react';
import {
  Upload, FileText, CheckCircle2, AlertCircle, Trash2, Plus,
  Search, Save, RefreshCw, Sparkles, Layers, Tag, Lock, Unlock, X
} from 'lucide-react';

interface ExtractedItem {
  id?: string;
  category: string;
  item_name: string;
  price: number | string;
  is_veg: boolean;
  name_edited?: boolean;
  price_edited?: boolean;
  veg_edited?: boolean;
}

export default function DocumentProcessorPage() {
  const [token, setToken] = useState<string>('');
  const [isTokenLocked, setIsTokenLocked] = useState<boolean>(false);
  const [backendUrl, setBackendUrl] = useState<string>('http://localhost:8000/api/v1');
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);

  const [documentId, setDocumentId] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [detectedType, setDetectedType] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const [items, setItems] = useState<ExtractedItem[]>([]);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedCategoryFilter, setSelectedCategoryFilter] = useState<string>('ALL');

  const [alert, setAlert] = useState<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);

  // ── Page Mount: Load Token & Redis Preview Draft on Page Refresh ──────────
  useEffect(() => {
    const savedToken = localStorage.getItem('spark_auth_token');
    if (savedToken) {
      setToken(savedToken);
      setIsTokenLocked(true);
    }

    const savedDocId = localStorage.getItem('spark_active_doc_id');
    if (savedDocId) {
      fetchPreviewFromRedis(savedDocId, savedToken || '');
    }
  }, []);

  const fetchPreviewFromRedis = async (docId: string, authToken: string) => {
    try {
      const headers: Record<string, string> = {};
      if (authToken.trim()) {
        headers['Authorization'] = `Bearer ${authToken.trim()}`;
      }

      const res = await fetch(`${backendUrl}/upload/preview/${docId}`, {
        method: 'GET',
        headers
      });

      const result = await res.json();
      if (res.ok && result.success && result.data) {
        const data = result.data;
        setDocumentId(docId);
        setFileName(data.file_name || 'Uploaded Document');
        setDetectedType(data.detected_type || 'BUSINESS');
        setStatus('ACTIVE (DRAFT IN REDIS)');

        const rawItems: ExtractedItem[] = (data.items || []).map((it: any, idx: number) => ({
          id: `item_${idx}_${Date.now()}`,
          category: it.category || 'General',
          item_name: it.item_name || '',
          price: it.price !== undefined ? it.price : 0,
          is_veg: it.is_veg ?? true
        }));

        if (rawItems.length > 0) {
          setItems(rawItems);
          setAlert({
            type: 'info',
            message: `Restored ${rawItems.length} draft items from Redis preview for document "${data.file_name || docId}".`
          });
        } else {
          localStorage.removeItem('spark_active_doc_id');
        }
      } else {
        localStorage.removeItem('spark_active_doc_id');
      }
    } catch (err) {
      console.warn('Could not restore preview from Redis:', err);
    }
  };

  const handleTokenChange = (val: string) => {
    setToken(val);
    if (val.trim()) {
      localStorage.setItem('spark_auth_token', val.trim());
    } else {
      localStorage.removeItem('spark_auth_token');
    }
  };

  const toggleTokenLock = () => {
    if (!token.trim()) return;
    const newLockState = !isTokenLocked;
    setIsTokenLocked(newLockState);
    if (token.trim()) {
      localStorage.setItem('spark_auth_token', token.trim());
    }
    setAlert({
      type: newLockState ? 'success' : 'info',
      message: newLockState ? 'JWT Token locked & saved. Page refresh will preserve it.' : 'JWT Token unlocked for editing.'
    });
  };

  const handleClearToken = () => {
    setToken('');
    setIsTokenLocked(false);
    localStorage.removeItem('spark_auth_token');
    setAlert({ type: 'info', message: 'JWT Auth Token deleted.' });
  };

  // Group items by Category for clean Category-Section view (NO REPETITIVE CATEGORY NAMES!)
  const groupedCategories = useMemo(() => {
    const map: Record<string, ExtractedItem[]> = {};

    items.forEach(item => {
      const cat = item.category || 'General';
      if (!map[cat]) map[cat] = [];

      const matchesSearch =
        item.item_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        cat.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesCategory =
        selectedCategoryFilter === 'ALL' || cat === selectedCategoryFilter;

      if (matchesSearch && matchesCategory) {
        map[cat].push(item);
      }
    });

    return map;
  }, [items, searchQuery, selectedCategoryFilter]);

  const allCategoryNames = useMemo(() => {
    const set = new Set<string>();
    items.forEach(it => {
      if (it.category) set.add(it.category);
    });
    return Array.from(set).sort();
  }, [items]);

  const totalVisibleItems = useMemo(() => {
    return Object.values(groupedCategories).reduce((sum, list) => sum + list.length, 0);
  }, [groupedCategories]);

  // ── Step 1: Upload File & Get Raw JSON Array ──────────────────────────────
  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setAlert({ type: 'error', message: 'Please select a PDF, Excel, or CSV file to upload.' });
      return;
    }

    setUploading(true);
    setAlert(null);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const headers: Record<string, string> = {};
      if (token.trim()) {
        headers['Authorization'] = `Bearer ${token.trim()}`;
      }

      const res = await fetch(`${backendUrl}/upload/document`, {
        method: 'POST',
        headers,
        body: formData
      });

      const result = await res.json();

      if (!res.ok || !result.success) {
        setAlert({ type: 'error', message: result.message || 'Upload failed.' });
        setUploading(false);
        return;
      }

      const docData = result.data;
      setDocumentId(docData.id);
      setFileName(docData.file_name);
      setDetectedType(docData.detected_type);
      setStatus(docData.status);

      // Persist active document ID for page refresh restoration from Redis
      localStorage.setItem('spark_active_doc_id', docData.id);

      const rawItems: ExtractedItem[] = (docData.raw_items || []).map((it: any, idx: number) => ({
        id: `item_${idx}_${Date.now()}`,
        category: it.category || 'General',
        item_name: it.item_name || '',
        price: it.price !== undefined ? it.price : 0,
        is_veg: it.is_veg ?? true
      }));

      setItems(rawItems);
      setAlert({
        type: 'success',
        message: `Successfully uploaded "${docData.file_name}"! ${rawItems.length} items loaded into ${Object.keys(groupedCategories).length} Category Sections (Saved in Redis).`
      });

    } catch (err: any) {
      setAlert({ type: 'error', message: err.message || 'Failed to connect to backend server.' });
    } finally {
      setUploading(false);
    }
  };

  // ── Item Field Updates ───────────────────────────────────────────────────
  const updateTargetItem = (targetItem: ExtractedItem, field: keyof ExtractedItem, value: any) => {
    setItems(prevItems => prevItems.map(item => {
      if (item === targetItem) {
        const updated = { ...item, [field]: value };
        if (field === 'item_name') updated.name_edited = true;
        if (field === 'price') updated.price_edited = true;
        if (field === 'is_veg') updated.veg_edited = true;
        return updated;
      }
      return item;
    }));
  };

  const updateCategoryName = (oldCategoryName: string, newCategoryName: string) => {
    if (!newCategoryName.trim()) return;
    setItems(prevItems => prevItems.map(item => {
      if (item.category === oldCategoryName) {
        return { ...item, category: newCategoryName.trim() };
      }
      return item;
    }));
  };

  const deleteItem = (targetItem: ExtractedItem) => {
    setItems(prev => prev.filter(item => item !== targetItem));
  };

  const addItemToCategory = (catName: string) => {
    const newItem: ExtractedItem = {
      id: `new_${Date.now()}`,
      category: catName,
      item_name: 'New Menu Item',
      price: 100,
      is_veg: true,
      name_edited: true
    };
    setItems(prev => [newItem, ...prev]);
  };

  const addNewCategory = () => {
    const newCatName = prompt('Enter New Category Name (e.g. Special Desserts):');
    if (newCatName && newCatName.trim()) {
      addItemToCategory(newCatName.trim());
    }
  };

  // ── Step 2: Save Structured Data to Database ──────────────────────────────
  const handleSaveStructuredData = async () => {
    if (!documentId) {
      setAlert({ type: 'error', message: 'No active document ID found. Please upload a document first.' });
      return;
    }

    if (items.length === 0) {
      setAlert({ type: 'error', message: 'Cannot save empty items list. Please add at least one item.' });
      return;
    }

    setSaving(true);
    setAlert(null);

    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json'
      };
      if (token.trim()) {
        headers['Authorization'] = `Bearer ${token.trim()}`;
      }

      const payload = {
        items: items.map(it => ({
          category: it.category,
          item_name: it.item_name,
          price: it.price,
          is_veg: it.is_veg,
          name_edited: it.name_edited,
          price_edited: it.price_edited,
          veg_edited: it.veg_edited
        }))
      };

      const res = await fetch(`${backendUrl}/upload/create-structured-data/${documentId}`, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload)
      });

      const result = await res.json();

      if (!res.ok || !result.success) {
        setAlert({ type: 'error', message: result.message || 'Failed to save structured data.' });
        setSaving(false);
        return;
      }

      setStatus('PROCESSED');
      localStorage.removeItem('spark_active_doc_id');
      setAlert({
        type: 'success',
        message: `Success! ${items.length} items grouped into ${result.data?.structured_data?.document_info?.total_categories_count || 0} categories and saved to Database & Disk!`
      });

    } catch (err: any) {
      setAlert({ type: 'error', message: err.message || 'Failed to save structured data.' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen p-4 md:p-8 custom-scrollbar">
      {/* Header */}
      <header className="max-w-7xl mx-auto mb-8 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 glass-card p-6 rounded-2xl">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-indigo-600/30 rounded-xl border border-indigo-500/40 text-indigo-400">
            <Sparkles className="w-7 h-7" />
          </div>
          <div>
            <h1 className="text-2xl font-bold bg-gradient-to-r from-indigo-400 via-purple-300 to-pink-400 bg-clip-text text-transparent">
              Spark AI Assistant — Category-Grouped Document Hub
            </h1>
            <p className="text-sm text-slate-400">
              Raw JSON Extraction, Category-Wise Grouped Table Review & Database Storage
            </p>
          </div>
        </div>

        {/* API Config Box with Token Lock & Clear (X) controls */}
        <div className="flex flex-wrap items-center gap-3 w-full md:w-auto">
          <div className="relative flex items-center w-full md:w-64">
            <input
              type="text"
              placeholder="JWT Auth Token (optional)"
              value={token}
              disabled={isTokenLocked}
              onChange={e => handleTokenChange(e.target.value)}
              className={`glass-input pl-3 pr-16 py-2 text-xs rounded-xl w-full ${isTokenLocked ? 'bg-emerald-950/40 border-emerald-500/50 text-emerald-300 font-mono' : ''
                }`}
            />
            <div className="absolute right-2 flex items-center gap-1">
              {token.trim() && (
                <>
                  <button
                    type="button"
                    onClick={toggleTokenLock}
                    className={`p-1 rounded-lg transition-all ${isTokenLocked ? 'text-emerald-400 hover:bg-emerald-900/50' : 'text-slate-400 hover:bg-slate-800'
                      }`}
                    title={isTokenLocked ? 'Token Locked (Click to Unlock)' : 'Lock Token'}
                  >
                    {isTokenLocked ? <Lock className="w-3.5 h-3.5" /> : <Unlock className="w-3.5 h-3.5" />}
                  </button>
                  <button
                    type="button"
                    onClick={handleClearToken}
                    className="p-1 text-slate-400 hover:text-rose-400 hover:bg-rose-950/50 rounded-lg transition-all"
                    title="Delete / Clear Token (X)"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </>
              )}
            </div>
          </div>

          <input
            type="text"
            placeholder="Backend URL"
            value={backendUrl}
            onChange={e => setBackendUrl(e.target.value)}
            className="glass-input px-3 py-2 text-xs rounded-xl w-full md:w-48"
          />
        </div>
      </header>

      <main className="max-w-7xl mx-auto space-y-6">
        {/* Alert Notification */}
        {alert && (
          <div className={`p-4 rounded-xl border flex items-center gap-3 text-sm font-medium ${alert.type === 'success' ? 'bg-emerald-950/60 border-emerald-500/50 text-emerald-300' :
            alert.type === 'error' ? 'bg-rose-950/60 border-rose-500/50 text-rose-300' :
              'bg-indigo-950/60 border-indigo-500/50 text-indigo-300'
            }`}>
            {alert.type === 'success' && <CheckCircle2 className="w-5 h-5 flex-shrink-0 text-emerald-400" />}
            {alert.type === 'error' && <AlertCircle className="w-5 h-5 flex-shrink-0 text-rose-400" />}
            {alert.type === 'info' && <Sparkles className="w-5 h-5 flex-shrink-0 text-indigo-400" />}
            <span>{alert.message}</span>
          </div>
        )}

        {/* File Upload Section */}
        <section className="glass-card p-6 rounded-2xl">
          <h2 className="text-lg font-semibold text-slate-200 mb-4 flex items-center gap-2">
            <Upload className="w-5 h-5 text-indigo-400" />
            Upload Document (PDF, Excel, CSV)
          </h2>

          <form onSubmit={handleUpload} className="flex flex-col md:flex-row items-center gap-4">
            <div className="relative flex-1 w-full border-2 border-dashed border-indigo-500/30 hover:border-indigo-500/60 rounded-xl p-4 transition-all text-center glass-card">
              <input
                type="file"
                accept=".pdf,.xlsx,.xls,.csv"
                onChange={e => setFile(e.target.files?.[0] || null)}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              />
              <div className="flex items-center justify-center gap-3 text-slate-300">
                <FileText className="w-6 h-6 text-indigo-400" />
                <span className="text-sm font-medium">
                  {file ? file.name : 'Click or Drag & Drop Digital PDF, Excel (.xlsx, .xls) or CSV (.csv)'}
                </span>
              </div>
            </div>

            <button
              type="submit"
              disabled={uploading || !file}
              className="w-full md:w-auto px-6 py-3 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 disabled:opacity-50 text-white font-medium text-sm rounded-xl flex items-center justify-center gap-2 shadow-lg shadow-indigo-600/30 transition-all"
            >
              {uploading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Extracting & Grouping...
                </>
              ) : (
                <>
                  <Upload className="w-4 h-4" />
                  Upload & Load Categories
                </>
              )}
            </button>
          </form>

          {/* Uploaded File Info Cards */}
          {documentId && (
            <div className="mt-4 pt-4 border-t border-slate-700/50 grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
              <div className="p-3 bg-slate-900/60 rounded-xl border border-slate-800">
                <span className="text-slate-500 block">Document ID:</span>
                <span className="font-mono text-indigo-300 font-semibold">{documentId}</span>
              </div>
              <div className="p-3 bg-slate-900/60 rounded-xl border border-slate-800">
                <span className="text-slate-500 block">File Name:</span>
                <span className="text-slate-200 font-medium truncate block">{fileName}</span>
              </div>
              <div className="p-3 bg-slate-900/60 rounded-xl border border-slate-800">
                <span className="text-slate-500 block">Detected Business:</span>
                <span className="text-purple-300 font-medium">{detectedType}</span>
              </div>
              <div className="p-3 bg-slate-900/60 rounded-xl border border-slate-800">
                <span className="text-slate-500 block">Status:</span>
                <span className={`font-semibold ${status === 'PROCESSED' ? 'text-emerald-400' : 'text-amber-400'}`}>
                  {status}
                </span>
              </div>
            </div>
          )}
        </section>

        {/* Category-Grouped Sections */}
        {items.length > 0 && (
          <section className="space-y-6">
            {/* Top Action Control Bar */}
            <div className="glass-card p-4 rounded-2xl flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <Layers className="w-5 h-5 text-purple-400" />
                <div>
                  <h3 className="text-base font-semibold text-slate-200">
                    Category Sections ({Object.keys(groupedCategories).length} Categories, {totalVisibleItems} Items)
                  </h3>
                  <p className="text-xs text-slate-400">
                    Each Category is displayed ONCE as a Section Header with all related items below it.
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-3 w-full md:w-auto">
                {/* Search Input */}
                <div className="relative flex-1 md:w-60">
                  <Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Search item or category..."
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                    className="glass-input pl-9 pr-3 py-2 text-xs rounded-xl w-full"
                  />
                </div>

                {/* Category Filter */}
                <select
                  value={selectedCategoryFilter}
                  onChange={e => setSelectedCategoryFilter(e.target.value)}
                  className="glass-input px-3 py-2 text-xs rounded-xl"
                >
                  <option value="ALL">All Categories ({allCategoryNames.length})</option>
                  {allCategoryNames.map(cat => (
                    <option key={cat} value={cat}>{cat}</option>
                  ))}
                </select>

                {/* Add Category Button */}
                <button
                  onClick={addNewCategory}
                  className="px-3 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-medium rounded-xl flex items-center gap-1.5 transition-all"
                >
                  <Plus className="w-3.5 h-3.5 text-purple-400" />
                  New Category
                </button>

                {/* Save Structured Data Button */}
                <button
                  onClick={handleSaveStructuredData}
                  disabled={saving}
                  className="px-5 py-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 disabled:opacity-50 text-white text-xs font-semibold rounded-xl flex items-center gap-2 shadow-lg shadow-emerald-600/30 transition-all"
                >
                  {saving ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      Saving to DB...
                    </>
                  ) : (
                    <>
                      <Save className="w-3.5 h-3.5" />
                      Save & Sync to DB
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Render Category Sections (One By One) */}
            {Object.entries(groupedCategories).map(([catName, categoryItems]) => (
              <div key={catName} className="glass-card rounded-2xl overflow-hidden border border-slate-800/80">
                {/* Category Header Card (ONLY SHOWN 1 TIME PER CATEGORY!) */}
                <div className="p-4 bg-gradient-to-r from-slate-900 via-indigo-950/40 to-slate-900 border-b border-slate-800 flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <Tag className="w-5 h-5 text-purple-400" />
                    <input
                      type="text"
                      value={catName}
                      onChange={e => updateCategoryName(catName, e.target.value)}
                      className="bg-transparent text-lg font-bold text-purple-200 focus:bg-slate-800/80 focus:px-2 focus:py-1 rounded-lg outline-none border border-transparent focus:border-purple-500/50 transition-all font-sans"
                    />
                    <span className="px-3 py-1 rounded-full text-xs font-bold bg-purple-950/80 border border-purple-500/40 text-purple-300">
                      {categoryItems.length} items
                    </span>
                  </div>

                  <button
                    onClick={() => addItemToCategory(catName)}
                    className="px-3 py-1.5 bg-indigo-900/40 hover:bg-indigo-800/60 border border-indigo-500/30 text-indigo-200 text-xs font-medium rounded-xl flex items-center gap-1.5 transition-all"
                  >
                    <Plus className="w-3.5 h-3.5 text-indigo-400" />
                    Add Item
                  </button>
                </div>

                {/* Items Table Under This Category */}
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead className="bg-slate-950/60 border-b border-slate-800 text-slate-400 font-semibold">
                      <tr>
                        <th className="p-3 w-12 text-center">#</th>
                        <th className="p-3">Item Name</th>
                        <th className="p-3 w-36">Price (₹)</th>
                        <th className="p-3 w-36 text-center">Diet Type</th>
                        <th className="p-3 w-20 text-center">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/40 bg-slate-950/20">
                      {categoryItems.map((item, idx) => (
                        <tr key={item.id || idx} className="hover:bg-slate-900/60 transition-colors">
                          {/* Index */}
                          <td className="p-3 text-center text-slate-500 font-mono">{idx + 1}</td>

                          {/* Item Name */}
                          <td className="p-2">
                            <input
                              type="text"
                              value={item.item_name}
                              onChange={e => updateTargetItem(item, 'item_name', e.target.value)}
                              className="glass-input px-3 py-1.5 rounded-lg w-full text-xs text-slate-100 font-medium"
                            />
                          </td>

                          {/* Price */}
                          <td className="p-2">
                            <input
                              type="text"
                              value={item.price}
                              onChange={e => updateTargetItem(item, 'price', e.target.value)}
                              className="glass-input px-3 py-1.5 rounded-lg w-full text-xs font-mono text-emerald-400 font-semibold"
                            />
                          </td>

                          {/* Veg Toggle Badge */}
                          <td className="p-2 text-center">
                            <button
                              type="button"
                              onClick={() => updateTargetItem(item, 'is_veg', !item.is_veg)}
                              className={`px-3 py-1.5 rounded-full text-[10px] font-bold border transition-all ${item.is_veg
                                ? 'bg-emerald-950/60 text-emerald-400 border-emerald-500/40 hover:bg-emerald-900/60'
                                : 'bg-rose-950/60 text-rose-400 border-rose-500/40 hover:bg-rose-900/60'
                                }`}
                            >
                              {item.is_veg ? '🟢 VEG' : '🔴 NON-VEG'}
                            </button>
                          </td>

                          {/* Delete Action */}
                          <td className="p-2 text-center">
                            <button
                              onClick={() => deleteItem(item)}
                              className="p-1.5 text-slate-500 hover:text-rose-400 hover:bg-rose-950/50 rounded-lg transition-all"
                              title="Delete Item"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </section>
        )}
      </main>
    </div>
  );
}
