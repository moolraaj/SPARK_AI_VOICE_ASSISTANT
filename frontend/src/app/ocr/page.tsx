'use client';

import { useState, type FormEvent, type ChangeEvent } from 'react';
import JSZip from 'jszip';

interface OCRPageData {
  page_number: number;
  text: string;
}

interface OCRManifest {
  document_id: string;
  language: string;
  pages: OCRPageData[];
  empty_text_pages: number[];
  review_required: boolean;
  note: string;
}

export default function OCRPage() {
  const [busy, setBusy] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [statusType, setStatusType] = useState<'idle' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');

  // Preview Modal States
  const [showModal, setShowModal] = useState(false);
  const [activeTab, setActiveTab] = useState<'pdf' | 'json' | 'pages'>('pdf');
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState<string | null>(null);
  const [extractedJson, setExtractedJson] = useState<OCRManifest | null>(null);
  const [zipBlobUrl, setZipBlobUrl] = useState<string | null>(null);
  const [copiedJson, setCopiedJson] = useState(false);

  function isValidFile(file: File) {
    const validMimes = ['application/pdf', 'image/jpeg', 'image/png', 'image/webp', 'image/bmp', 'image/tiff'];
    return validMimes.includes(file.type) || /\.(pdf|jpg|jpeg|png|webp|bmp|tiff)$/i.test(file.name);
  }

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      if (!isValidFile(file)) {
        setStatusType('error');
        setMessage('Please select a valid PDF or Image file (.pdf, .jpg, .png, .webp).');
        setSelectedFile(null);
        return;
      }
      setSelectedFile(file);
      setStatusType('idle');
      setMessage('');
    }
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    setDragActive(true);
  }

  function handleDragLeave() {
    setDragActive(false);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      if (!isValidFile(file)) {
        setStatusType('error');
        setMessage('Please drop a valid PDF or Image file (.pdf, .jpg, .png, .webp).');
        return;
      }
      setSelectedFile(file);
      setStatusType('idle');
      setMessage('');
    }
  }

  function cleanUpPreviousUrls() {
    if (pdfPreviewUrl) {
      URL.revokeObjectURL(pdfPreviewUrl);
      setPdfPreviewUrl(null);
    }
    if (zipBlobUrl) {
      URL.revokeObjectURL(zipBlobUrl);
      setZipBlobUrl(null);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile) {
      setStatusType('error');
      setMessage('Please select or drop a PDF or Image file first.');
      return;
    }

    const formData = new FormData(event.currentTarget);
    formData.set('file', selectedFile);

    setBusy(true);
    setStatusType('idle');
    setMessage('Processing your document/image (OCR conversion in progress)...');

    cleanUpPreviousUrls();
    setExtractedJson(null);

    try {
      const backendBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
      const serviceKey = process.env.NEXT_PUBLIC_OCR_SERVICE_KEY || 'OHS_2LkyHVEqFzIRlt5QQ3NPV2sRMvazsxosPeQOOaE';
      const ocrEndpoint = `${backendBase.replace(/\/$/, '')}/documents/ocr`;

      const response = await fetch(ocrEndpoint, {
        method: 'POST',
        headers: {
          'X-Service-Key': serviceKey,
        },
        body: formData,
      });

      const contentType = response.headers.get('content-type') || '';

      if (!response.ok || contentType.includes('application/json')) {
        const errorData = await response.json().catch(() => ({}));
        const rawDetail = typeof errorData.detail === 'string' ? errorData.detail : 'OCR Conversion Failed.';
        throw new Error(rawDetail);
      }

      const blob = await response.blob();
      const zipUrl = URL.createObjectURL(blob);
      setZipBlobUrl(zipUrl);

      // Unpack ZIP directly in browser
      const zip = await JSZip.loadAsync(blob);
      const pdfFile = zip.file('searchable.pdf');
      const jsonFile = zip.file('pages.json');

      if (pdfFile) {
        const pdfBlob = await pdfFile.async('blob');
        const pdfUrl = URL.createObjectURL(new Blob([pdfBlob], { type: 'application/pdf' }));
        setPdfPreviewUrl(pdfUrl);
      }

      if (jsonFile) {
        const jsonText = await jsonFile.async('string');
        const parsedManifest: OCRManifest = JSON.parse(jsonText);
        setExtractedJson(parsedManifest);
      }

      setStatusType('success');
      setMessage('Success! Searchable digital PDF & extracted text are ready for viewing.');
      setShowModal(true);
    } catch (err: unknown) {
      setStatusType('error');
      if (err instanceof Error) {
        setMessage(err.message);
      } else {
        setMessage('An unexpected error occurred during OCR conversion.');
      }
    } finally {
      setBusy(false);
    }
  }

  function handleCopyJson() {
    if (extractedJson) {
      navigator.clipboard.writeText(JSON.stringify(extractedJson, null, 2));
      setCopiedJson(true);
      setTimeout(() => setCopiedJson(false), 2000);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-3xl w-full space-y-8">

        {/* Header Section */}
        <div className="text-center space-y-3">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-semibold uppercase tracking-wider">
            <span>✨ AI Powered Document & Image Digitizer</span>
          </div>
          <h1 className="text-4xl font-extrabold tracking-tight sm:text-5xl bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
            Scanned PDF & Image OCR
          </h1>
          <p className="text-slate-400 text-base max-w-xl mx-auto">
            Upload scanned PDFs or images (.jpg, .png, .webp). Preview searchable PDFs and extracted JSON text directly in interactive modal.
          </p>
        </div>

        {/* Card Form Container */}
        <div className="bg-slate-900/80 backdrop-blur-xl border border-slate-800 rounded-2xl p-6 sm:p-8 shadow-2xl space-y-6">
          <form onSubmit={handleSubmit} className="space-y-6">

            {/* File Dropzone */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                PDF or Image File <span className="text-rose-400">*</span>
              </label>
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                className={`relative border-2 border-dashed rounded-xl p-8 text-center transition-all cursor-pointer ${dragActive
                  ? 'border-blue-500 bg-blue-500/10'
                  : selectedFile
                    ? 'border-emerald-500/50 bg-emerald-500/5'
                    : 'border-slate-700 hover:border-slate-500 bg-slate-950/50'
                  }`}
              >
                <input
                  type="file"
                  name="file"
                  accept="application/pdf,image/jpeg,image/png,image/webp,image/tiff,image/bmp,.pdf,.jpg,.jpeg,.png,.webp,.tiff,.bmp"
                  onChange={handleFileChange}
                  disabled={busy}
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
                />

                <div className="flex flex-col items-center space-y-3">
                  <div className="p-3 bg-slate-800/80 rounded-full border border-slate-700 text-slate-300">
                    {selectedFile ? (
                      <svg className="w-8 h-8 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    ) : (
                      <svg className="w-8 h-8 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                      </svg>
                    )}
                  </div>

                  {selectedFile ? (
                    <div className="space-y-1">
                      <p className="text-sm font-semibold text-emerald-300">{selectedFile.name}</p>
                      <p className="text-xs text-slate-400">{(selectedFile.size / (1024 * 1024)).toFixed(2)} MB • Ready to convert</p>
                    </div>
                  ) : (
                    <div className="space-y-1">
                      <p className="text-sm font-medium text-slate-200">
                        Drag and drop your PDF or Image here, or <span className="text-blue-400 underline">browse</span>
                      </p>
                      <p className="text-xs text-slate-500">Supports scanned PDFs & Images (.pdf, .jpg, .png, .webp) up to 10 MiB</p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Options Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                  Primary Language
                </label>
                <select
                  name="language"
                  defaultValue="eng"
                  disabled={busy}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none disabled:opacity-50"
                >
                  <option value="eng">English (eng)</option>
                  <option value="hin">Hindi (hin)</option>
                  <option value="eng+hin">Hindi + English (eng+hin)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                  OCR Engine Mode
                </label>
                <div className="flex items-center h-10 px-3 bg-slate-950 border border-slate-700 rounded-lg">
                  <label className="inline-flex items-center gap-2 cursor-pointer text-xs text-slate-300">
                    <input
                      type="checkbox"
                      name="force_ocr"
                      value="true"
                      disabled={busy}
                      className="w-4 h-4 rounded border-slate-700 bg-slate-900 text-blue-600 focus:ring-blue-500"
                    />
                    <span>Force Full OCR (Rasterize All Pages)</span>
                  </label>
                </div>
              </div>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={busy || !selectedFile}
              className="w-full py-3.5 px-4 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-semibold rounded-xl shadow-lg shadow-blue-500/25 transition-all duration-200 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none"
            >
              {busy ? (
                <>
                  <svg className="animate-spin -ml-1 mr-2 h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span>Digitizing PDF & Extracting Text...</span>
                </>
              ) : (
                <span>Digitize & View PDF / JSON Preview</span>
              )}
            </button>
          </form>

          {/* Status / Alert Banner */}
          {message && (
            <div
              className={`p-4 rounded-xl border flex items-start gap-3 text-sm transition-all ${statusType === 'error'
                ? 'bg-rose-500/10 border-rose-500/30 text-rose-300'
                : statusType === 'success'
                  ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                  : 'bg-blue-500/10 border-blue-500/30 text-blue-300'
                }`}
            >
              <div className="mt-0.5">
                {statusType === 'error' && (
                  <svg className="w-5 h-5 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                )}
                {statusType === 'success' && (
                  <svg className="w-5 h-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                )}
                {statusType === 'idle' && (
                  <svg className="w-5 h-5 text-blue-400 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                )}
              </div>
              <div className="flex-1 space-y-2">
                <p className="font-medium">{message}</p>

                {/* If ocrmypdf binary error */}
                {statusType === 'error' && message.includes('OCRmyPDF') && (
                  <div className="mt-2 text-xs bg-slate-950/80 p-3 rounded border border-rose-950 text-slate-300 font-mono">
                    <p className="text-amber-400 font-semibold mb-1">Fix: Run this command on your server terminal:</p>
                    <code>sudo apt update && sudo apt install -y ocrmypdf tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin</code>
                  </div>
                )}

                {/* Re-open popup button */}
                {statusType === 'success' && (pdfPreviewUrl || extractedJson) && (
                  <div className="flex items-center gap-3 pt-1">
                    <button
                      type="button"
                      onClick={() => setShowModal(true)}
                      className="px-3 py-1.5 bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/30 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                      </svg>
                      Open PDF & JSON Modal Preview
                    </button>

                    {zipBlobUrl && (
                      <a
                        href={zipBlobUrl}
                        download={`digitized_${selectedFile?.name || 'document'}.zip`}
                        className="text-xs text-slate-400 hover:text-slate-200 underline flex items-center gap-1"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                        </svg>
                        Download ZIP
                      </a>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

        </div>
      </div>

      {/* Interactive Modal Popup for PDF & JSON Preview */}
      {showModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-4 sm:p-6 animate-in fade-in duration-200">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-5xl h-[88vh] flex flex-col shadow-2xl overflow-hidden">

            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-slate-800 flex flex-wrap items-center justify-between gap-4 bg-slate-950/60">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-500/10 border border-blue-500/20 text-blue-400 rounded-lg">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
                    <span>Document Digitized Result</span>
                    {extractedJson?.pages && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-medium">
                        {extractedJson.pages.length} Page(s)
                      </span>
                    )}
                  </h3>
                  <p className="text-xs text-slate-400">
                    {selectedFile?.name} • Ready to inspect search layer and extracted JSON
                  </p>
                </div>
              </div>

              {/* Action Toolbar */}
              <div className="flex items-center gap-2">
                {extractedJson && (
                  <button
                    type="button"
                    onClick={handleCopyJson}
                    className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-all"
                  >
                    <svg className="w-3.5 h-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                    </svg>
                    <span>{copiedJson ? 'Copied!' : 'Copy JSON'}</span>
                  </button>
                )}

                {zipBlobUrl && (
                  <a
                    href={zipBlobUrl}
                    download={`digitized_${selectedFile?.name || 'document'}.zip`}
                    className="px-3 py-1.5 bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/30 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-all"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    <span>Download ZIP</span>
                  </a>
                )}

                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="p-1.5 text-slate-400 hover:text-slate-100 hover:bg-slate-800 rounded-lg transition-all"
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Navigation Tabs Bar */}
            <div className="px-6 bg-slate-950/40 border-b border-slate-800 flex gap-2">
              <button
                type="button"
                onClick={() => setActiveTab('pdf')}
                className={`py-3 px-4 text-xs font-semibold flex items-center gap-2 border-b-2 transition-all ${activeTab === 'pdf'
                  ? 'border-blue-500 text-blue-400 bg-blue-500/5'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
                  }`}
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                </svg>
                <span>Searchable PDF Viewer</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab('json')}
                className={`py-3 px-4 text-xs font-semibold flex items-center gap-2 border-b-2 transition-all ${activeTab === 'json'
                  ? 'border-blue-500 text-blue-400 bg-blue-500/5'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
                  }`}
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                </svg>
                <span>Raw Extracted JSON</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab('pages')}
                className={`py-3 px-4 text-xs font-semibold flex items-center gap-2 border-b-2 transition-all ${activeTab === 'pages'
                  ? 'border-blue-500 text-blue-400 bg-blue-500/5'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
                  }`}
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                </svg>
                <span>Pages Text Inspector</span>
              </button>
            </div>

            {/* Modal Body Container */}
            <div className="flex-1 bg-slate-950 overflow-hidden relative">

              {/* Tab 1: PDF Viewer */}
              {activeTab === 'pdf' && (
                <div className="w-full h-full">
                  {pdfPreviewUrl ? (
                    <iframe
                      src={pdfPreviewUrl}
                      className="w-full h-full border-0 bg-slate-900"
                      title="Searchable PDF Preview"
                    />
                  ) : (
                    <div className="w-full h-full flex flex-col items-center justify-center text-slate-500 space-y-2">
                      <p className="text-sm">No PDF preview available.</p>
                    </div>
                  )}
                </div>
              )}

              {/* Tab 2: Raw Extracted JSON */}
              {activeTab === 'json' && (
                <div className="w-full h-full p-6 overflow-auto bg-slate-950 font-mono text-xs">
                  {extractedJson ? (
                    <pre className="text-emerald-400 whitespace-pre-wrap break-all leading-relaxed">
                      {JSON.stringify(extractedJson, null, 2)}
                    </pre>
                  ) : (
                    <p className="text-slate-500">No JSON manifest extracted.</p>
                  )}
                </div>
              )}

              {/* Tab 3: Pages Text Inspector */}
              {activeTab === 'pages' && (
                <div className="w-full h-full p-6 overflow-auto bg-slate-950 space-y-6">
                  {extractedJson?.pages && extractedJson.pages.length > 0 ? (
                    extractedJson.pages.map((p) => {
                      const isEmpty = !p.text || !p.text.trim();
                      return (
                        <div
                          key={p.page_number}
                          className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 space-y-3"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-blue-400 uppercase tracking-wider bg-blue-500/10 border border-blue-500/20 px-2.5 py-1 rounded-md">
                              Page {p.page_number}
                            </span>
                            {isEmpty ? (
                              <span className="text-xs px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/20 text-amber-400">
                                ⚠️ Empty Text Layer
                              </span>
                            ) : (
                              <span className="text-xs text-slate-400">
                                {p.text.length} characters
                              </span>
                            )}
                          </div>
                          <div className="bg-slate-950 rounded-lg p-4 text-xs font-mono text-slate-300 leading-relaxed whitespace-pre-wrap border border-slate-800/60 max-h-60 overflow-auto">
                            {isEmpty ? (
                              <em className="text-slate-600">No text detected on this page.</em>
                            ) : (
                              p.text
                            )}
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <p className="text-slate-500">No page data available.</p>
                  )}
                </div>
              )}

            </div>

          </div>
        </div>
      )}

    </main>
  );
}