"use client";

import React, { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import {
  Database,
  Search,
  Plus,
  Trash2,
  Edit3,
  RefreshCw,
  Copy,
  Check,
  ArrowLeft,
  X,
  FileText,
  AlertCircle,
  CheckCircle2,
  Layers,
  Code,
  Sparkles,
  Zap,
  LayoutGrid,
  Table as TableIcon,
  List as ListIcon,
  Tag,
  DollarSign,
  ChevronDown,
  ChevronRight,
  FolderOpen,
  Maximize2,
  Minimize2
} from "lucide-react";

interface CollectionInfo {
  name: string;
  status: string;
  points_count: number;
  vectors_count: number;
  vector_size: number;
  distance: string;
}

interface VectorPoint {
  id: string;
  collection_name: string;
  payload: {
    document_name?: string;
    page_number?: number;
    chunk_index?: number;
    text?: string;
    item_name?: string;
    category?: string;
    subcategory?: string;
    price?: number | string;
    qty?: number | string;
    [key: string]: any;
  };
  vector_dim: number;
  vector_preview: number[];
}

interface ParsedMenuItem {
  pointId: string;
  docName: string;
  pageNo: number;
  category: string;
  subcategory: string;
  itemName: string;
  price: string;
  rawPrice: string;
  vectorDim: number;
  vectorPreview: number[];
  fullText: string;
  originalPoint: VectorPoint;
}

const API_BASE_URL ="http://localhost:8000/api/v1";

type ViewMode = "sections" | "table" | "grid" | "json";

export default function ShowDataPage() {
  const [loadingCollections, setLoadingCollections] = useState<boolean>(true);
  const [loadingPoints, setLoadingPoints] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const [collections, setCollections] = useState<CollectionInfo[]>([]);
  const [selectedCollection, setSelectedCollection] = useState<string>("pdf_knowledge");
  const [points, setPoints] = useState<VectorPoint[]>([]);

  // Default view mode: Categorized Sections (No Accordions)
  const [viewMode, setViewMode] = useState<ViewMode>("sections");

  // Accordion open/close state map (category_name -> boolean)
  const [openAccordions, setOpenAccordions] = useState<Record<string, boolean>>({});

  // Search & Filter
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedDocFilter, setSelectedDocFilter] = useState<string>("all");
  const [selectedCatFilter, setSelectedCatFilter] = useState<string>("all");

  // Copy state
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Edit Modal State (1-by-1 Edit)
  const [editingItem, setEditingItem] = useState<ParsedMenuItem | null>(null);
  const [editItemName, setEditItemName] = useState<string>("");
  const [editCategory, setEditCategory] = useState<string>("");
  const [editSubcategory, setEditSubcategory] = useState<string>("");
  const [editPrice, setEditPrice] = useState<string>("");
  const [editText, setEditText] = useState<string>("");
  const [savingEdit, setSavingEdit] = useState<boolean>(false);

  // Add Modal State (1-by-1 Add)
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [addItemName, setAddItemName] = useState<string>("");
  const [addCategory, setAddCategory] = useState<string>("PIZZA");
  const [addSubcategory, setAddSubcategory] = useState<string>("CHICKEN");
  const [addPrice, setAddPrice] = useState<string>("320");
  const [addText, setAddText] = useState<string>("");
  const [addDocName, setAddDocName] = useState<string>("celebration_cafe_digital_menu.pdf");
  const [addPageNum, setAddPageNum] = useState<number>(1);
  const [savingAdd, setSavingAdd] = useState<boolean>(false);

  // Parse all vector points into structured individual menu items
  const allParsedItems = useMemo(() => {
    const itemList: ParsedMenuItem[] = [];

    points.forEach((point) => {
      const p = point.payload || {};
      const docName = p.document_name || "celebration_cafe_digital_menu.pdf";
      const pageNo = p.page_number || 1;
      const vecDim = point.vector_dim || 1536;
      const vecPrev = point.vector_preview || [];
      const fullText = p.text || JSON.stringify(p);

      // Check if explicit single item payload exists
      if (p.item_name || p.category) {
        const sub = (p.subcategory || "").trim();
        const cleanSub = ["STANDARD", "GENERAL", "NONE", "NULL"].includes(sub.toUpperCase()) ? "" : sub.toUpperCase();

        itemList.push({
          pointId: point.id,
          docName,
          pageNo,
          category: (p.category || "UNCATEGORIZED").toUpperCase(),
          subcategory: cleanSub,
          itemName: p.item_name || "Menu Item",
          price: p.price !== undefined ? `PKR ${p.price}` : "PKR --",
          rawPrice: p.price !== undefined ? String(p.price) : "",
          vectorDim: vecDim,
          vectorPreview: vecPrev,
          fullText,
          originalPoint: point,
        });
        return;
      }

      // Parse multiline text pattern: Category \n Subcategory \n Item Name \n Price
      if (p.text) {
        const lines = p.text
          .split("\n")
          .map((l: string) => l.trim())
          .filter(
            (l: string) =>
              l &&
              !l.startsWith("Document:") &&
              l.toLowerCase() !== "category" &&
              l.toLowerCase() !== "subcategory" &&
              l.toLowerCase() !== "item name" &&
              !l.toLowerCase().includes("price (pkr)") &&
              !l.toLowerCase().includes("price")
          );

        let i = 0;
        let foundAny = false;

        while (i < lines.length) {
          // 4-line tuple: Category, Subcategory, Item Name, Price
          if (i + 3 < lines.length && /^\d+(\.\d+)?$/.test(lines[i + 3])) {
            const sub = lines[i + 1].trim();
            const cleanSub = ["STANDARD", "GENERAL", "NONE", "NULL"].includes(sub.toUpperCase()) ? "" : sub.toUpperCase();

            itemList.push({
              pointId: point.id,
              docName,
              pageNo,
              category: lines[i].toUpperCase(),
              subcategory: cleanSub,
              itemName: lines[i + 2],
              price: `PKR ${lines[i + 3]}`,
              rawPrice: lines[i + 3],
              vectorDim: vecDim,
              vectorPreview: vecPrev,
              fullText,
              originalPoint: point,
            });
            foundAny = true;
            i += 4;
          }
          // 3-line tuple: Category, Item Name, Price (NO SUBCATEGORY)
          else if (i + 2 < lines.length && /^\d+(\.\d+)?$/.test(lines[i + 2])) {
            itemList.push({
              pointId: point.id,
              docName,
              pageNo,
              category: lines[i].toUpperCase(),
              subcategory: "",
              itemName: lines[i + 1],
              price: `PKR ${lines[i + 2]}`,
              rawPrice: lines[i + 2],
              vectorDim: vecDim,
              vectorPreview: vecPrev,
              fullText,
              originalPoint: point,
            });
            foundAny = true;
            i += 3;
          } else {
            i++;
          }
        }

        // Fallback if no 4-line or 3-line numeric pattern matched
        if (!foundAny && lines.length > 0) {
          itemList.push({
            pointId: point.id,
            docName,
            pageNo,
            category: lines[0].toUpperCase(),
            subcategory: "",
            itemName: lines[lines.length - 1],
            price: "PKR --",
            rawPrice: "",
            vectorDim: vecDim,
            vectorPreview: vecPrev,
            fullText,
            originalPoint: point,
          });
        }
      }
    });

    return itemList;
  }, [points]);

  // Fetch all collections
  const fetchCollections = async () => {
    setLoadingCollections(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/testing/qdrant/collections`);
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const json = await res.json();
      const cols = json.collections || json.data || [];
      if (json.success && cols.length > 0) {
        setCollections(cols);
        const bestCollection = cols.find((c: CollectionInfo) => c.points_count > 0) || cols[0];
        if (bestCollection) {
          setSelectedCollection(bestCollection.name);
        }
      }
    } catch (err: any) {
      console.error("Fetch Collections Error:", err);
      setError(err.message || "Failed to load Qdrant collections.");
    } finally {
      setLoadingCollections(false);
    }
  };

  // Fetch points for selected collection
  const fetchPoints = async (collectionName: string) => {
    setLoadingPoints(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/testing/qdrant/collections/${collectionName}/points`);
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const json = await res.json();
      const pts = json.points || json.data || [];
      if (json.success) {
        setPoints(pts);
      }
    } catch (err: any) {
      console.error("Fetch Points Error:", err);
      setError(err.message || "Failed to load vector points.");
    } finally {
      setLoadingPoints(false);
    }
  };

  useEffect(() => {
    fetchCollections();
  }, []);

  useEffect(() => {
    if (selectedCollection) {
      fetchPoints(selectedCollection);
    }
  }, [selectedCollection]);

  // Group items by Category into accordion map
  const categoryGroupedMap = useMemo(() => {
    const map: Record<string, ParsedMenuItem[]> = {};

    allParsedItems.forEach((item) => {
      // Filter check
      if (selectedDocFilter !== "all" && item.docName !== selectedDocFilter) return;
      if (selectedCatFilter !== "all" && item.category !== selectedCatFilter) return;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const nameMatch = item.itemName.toLowerCase().includes(q);
        const catMatch = item.category.toLowerCase().includes(q);
        const subMatch = item.subcategory.toLowerCase().includes(q);
        const idMatch = item.pointId.toLowerCase().includes(q);
        const textMatch = item.fullText.toLowerCase().includes(q);
        if (!nameMatch && !catMatch && !subMatch && !idMatch && !textMatch) return;
      }

      const catKey = item.category || "UNCATEGORIZED";
      if (!map[catKey]) map[catKey] = [];
      map[catKey].push(item);
    });

    return map;
  }, [allParsedItems, selectedDocFilter, selectedCatFilter, searchQuery]);

  // Default open top 3 category accordions
  useEffect(() => {
    const cats = Object.keys(categoryGroupedMap);
    if (cats.length > 0) {
      const initialMap: Record<string, boolean> = {};
      cats.forEach((cat, idx) => {
        initialMap[cat] = idx < 3; // First 3 expanded by default
      });
      setOpenAccordions(initialMap);
    }
  }, [categoryGroupedMap]);

  // Toggle single category accordion open/closed
  const toggleAccordion = (categoryName: string) => {
    setOpenAccordions((prev) => ({
      ...prev,
      [categoryName]: !prev[categoryName],
    }));
  };

  // Expand / Collapse all accordions
  const toggleExpandAll = (expand: boolean) => {
    const updatedMap: Record<string, boolean> = {};
    Object.keys(categoryGroupedMap).forEach((cat) => {
      updatedMap[cat] = expand;
    });
    setOpenAccordions(updatedMap);
  };

  // Copy helper
  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Smart Helper: Replace 1 item inside a multiline chunk text
  const updateChunkItemText = (
    originalText: string,
    targetItemName: string,
    newCat: string,
    newSubcat: string,
    newName: string,
    newPrice: string
  ): string => {
    const lines = originalText.split("\n");
    const newLines: string[] = [];
    let i = 0;
    let replaced = false;

    while (i < lines.length) {
      if (i + 3 < lines.length) {
        const l3 = lines[i + 2].trim();
        const l4 = lines[i + 3].trim();
        if (l3.toLowerCase() === targetItemName.toLowerCase() && /^\d+(\.\d+)?$/.test(l4)) {
          newLines.push(newCat, newSubcat, newName, newPrice);
          i += 4;
          replaced = true;
          continue;
        }
      }
      newLines.push(lines[i]);
      i++;
    }

    if (!replaced) {
      return `${newCat}\n${newSubcat}\n${newName}\n${newPrice}`;
    }
    return newLines.join("\n");
  };

  // Smart Helper: Remove 1 item from a multiline chunk text
  const removeChunkItemText = (originalText: string, targetItemName: string): { updatedText: string; countRemaining: number } => {
    const lines = originalText.split("\n");
    const newLines: string[] = [];
    let i = 0;
    let itemsFound = 0;
    let itemsRemoved = 0;

    while (i < lines.length) {
      if (i + 3 < lines.length) {
        const l3 = lines[i + 2].trim();
        const l4 = lines[i + 3].trim();
        if (/^\d+(\.\d+)?$/.test(l4)) {
          itemsFound++;
          if (l3.toLowerCase() === targetItemName.toLowerCase() && itemsRemoved === 0) {
            i += 4;
            itemsRemoved++;
            continue;
          }
        }
      }
      newLines.push(lines[i]);
      i++;
    }

    return {
      updatedText: newLines.join("\n").trim(),
      countRemaining: itemsFound - itemsRemoved,
    };
  };

  // Delete 1 item individually by Item Name / Point ID
  const handleDeleteItem = async (item: ParsedMenuItem) => {
    if (!confirm(`Are you sure you want to delete '${item.itemName}' (${item.price}) 1-by-1 from Qdrant?`)) return;

    try {
      const { updatedText, countRemaining } = removeChunkItemText(item.fullText, item.itemName);

      if (countRemaining > 0 && updatedText.length > 10) {
        // Update point in Qdrant with remaining items
        const res = await fetch(
          `${API_BASE_URL}/testing/qdrant/collections/${selectedCollection}/points/${item.pointId}`,
          {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              text: updatedText,
              extra_payload: {
                ...item.originalPoint.payload,
                text: updatedText,
              },
            }),
          }
        );
        if (!res.ok) throw new Error("Failed to update vector point after removing item");
      } else {
        // Delete entire point if no items remain
        const res = await fetch(
          `${API_BASE_URL}/testing/qdrant/collections/${selectedCollection}/points/${item.pointId}`,
          {
            method: "DELETE",
          }
        );
        if (!res.ok) throw new Error("Failed to delete point");
      }

      fetchPoints(selectedCollection);
      fetchCollections();
    } catch (err: any) {
      alert("Delete Error: " + err.message);
    }
  };

  // Clear collection
  const handleClearCollection = async () => {
    if (!confirm(`CAUTION: Are you sure you want to clear ALL points in collection '${selectedCollection}'?`)) return;

    try {
      const res = await fetch(`${API_BASE_URL}/testing/qdrant/collections/${selectedCollection}/clear`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("Failed to clear collection");
      const json = await res.json();

      if (json.success) {
        setPoints([]);
        fetchCollections();
      }
    } catch (err: any) {
      alert("Clear Error: " + err.message);
    }
  };

  // Open Edit Modal 1-by-1
  const handleOpenEdit = (item: ParsedMenuItem) => {
    setEditingItem(item);
    setEditItemName(item.itemName);
    setEditCategory(item.category);
    setEditSubcategory(item.subcategory);
    setEditPrice(item.rawPrice);
    setEditText(`${item.category}\n${item.subcategory}\n${item.itemName}\n${item.rawPrice}`);
  };

  // Save Edit Point (1-by-1)
  const handleSaveEdit = async () => {
    if (!editingItem) return;

    setSavingEdit(true);
    try {
      const finalConstructedText = updateChunkItemText(
        editingItem.fullText,
        editingItem.itemName,
        editCategory.trim(),
        editSubcategory.trim(),
        editItemName.trim(),
        editPrice.trim()
      );

      const updatedPayload = {
        ...editingItem.originalPoint.payload,
        item_name: editItemName.trim(),
        category: editCategory.trim(),
        subcategory: editSubcategory.trim(),
        price: editPrice.trim(),
        text: finalConstructedText,
      };

      const res = await fetch(
        `${API_BASE_URL}/testing/qdrant/collections/${selectedCollection}/points/${editingItem.pointId}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: finalConstructedText,
            extra_payload: updatedPayload,
          }),
        }
      );

      if (!res.ok) throw new Error("Failed to update vector point");
      const json = await res.json();

      if (json.success) {
        setEditingItem(null);
        fetchPoints(selectedCollection);
      }
    } catch (err: any) {
      alert("Update Error: " + err.message);
    } finally {
      setSavingEdit(false);
    }
  };

  // Save New Vector Point (1-by-1)
  const handleSaveAdd = async () => {
    if (!addItemName.trim() && !addText.trim()) return;

    setSavingAdd(true);
    try {
      const constructedText = addText.trim() || `${addCategory}\n${addSubcategory}\n${addItemName}\n${addPrice}`;

      const res = await fetch(`${API_BASE_URL}/testing/qdrant/collections/${selectedCollection}/points`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: constructedText,
          document_name: addDocName.trim() || "celebration_cafe_digital_menu.pdf",
          page_number: addPageNum,
          extra_payload: {
            item_name: addItemName.trim(),
            category: addCategory.trim(),
            subcategory: addSubcategory.trim(),
            price: addPrice.trim(),
          },
        }),
      });

      if (!res.ok) throw new Error("Failed to add new vector point");
      const json = await res.json();

      if (json.success) {
        setShowAddModal(false);
        setAddItemName("");
        setAddText("");
        fetchPoints(selectedCollection);
        fetchCollections();
      }
    } catch (err: any) {
      alert("Add Vector Error: " + err.message);
    } finally {
      setSavingAdd(false);
    }
  };

  const docNamesList = useMemo(() => {
    const names = new Set<string>();
    allParsedItems.forEach((i) => {
      if (i.docName) names.add(i.docName);
    });
    return Array.from(names);
  }, [allParsedItems]);

  const categoriesList = useMemo(() => {
    const cats = new Set<string>();
    allParsedItems.forEach((i) => {
      if (i.category) cats.add(i.category);
    });
    return Array.from(cats);
  }, [allParsedItems]);

  const categoryKeys = Object.keys(categoryGroupedMap);
  const totalItemCount = useMemo(() => {
    let count = 0;
    Object.values(categoryGroupedMap).forEach((list) => {
      count += list.length;
    });
    return count;
  }, [categoryGroupedMap]);

  return (
    <div className="min-h-screen bg-[#0b0f19] text-slate-100 p-4 md:p-8 font-sans selection:bg-indigo-500 selection:text-white">
      {/* Background Glow */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute top-[-10%] left-[20%] w-[500px] h-[500px] bg-indigo-600/10 rounded-full blur-[140px]" />
        <div className="absolute bottom-[-10%] right-[10%] w-[400px] h-[400px] bg-purple-600/10 rounded-full blur-[140px]" />
      </div>

      <div className="max-w-7xl mx-auto space-y-6 relative z-10">
        {/* Navigation & Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 glass-card p-5 rounded-2xl border border-slate-800">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="p-2.5 bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700/60 rounded-xl transition text-slate-300 hover:text-white"
            >
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <div className="flex items-center gap-2">
                <span className="px-2.5 py-0.5 text-xs font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30 rounded-full">
                  Category Accordion Explorer
                </span>
                <span className="px-2.5 py-0.5 text-xs font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-full flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  Qdrant Vector DB Active
                </span>
              </div>
              <h1 className="text-2xl font-bold bg-gradient-to-r from-white via-purple-200 to-indigo-300 bg-clip-text text-transparent mt-1">
                Vector Store Data Manager (/get-vector-store-data)
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                fetchCollections();
                if (selectedCollection) fetchPoints(selectedCollection);
              }}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 hover:text-white text-xs font-semibold rounded-xl border border-slate-700 transition flex items-center gap-2 cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingCollections || loadingPoints ? "animate-spin" : ""}`} />
              <span>Refresh Data</span>
            </button>
          </div>
        </div>

        {/* Collection Selector Cards */}
        <div className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Available Qdrant Collections
          </h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {collections.map((col) => {
              const isSelected = selectedCollection === col.name;

              return (
                <button
                  key={`col-card-${col.name}`}
                  onClick={() => setSelectedCollection(col.name)}
                  className={`p-5 rounded-2xl border text-left transition flex flex-col justify-between space-y-4 cursor-pointer ${
                    isSelected
                      ? "glass-card border-indigo-500 bg-indigo-600/10 shadow-lg shadow-indigo-600/10 scale-[1.01]"
                      : "glass-card border-slate-800 hover:border-slate-700 bg-slate-900/40"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Database className={`w-5 h-5 ${isSelected ? "text-indigo-400" : "text-slate-400"}`} />
                      <span className="font-bold text-slate-100 text-base">{col.name}</span>
                    </div>
                    <span className="px-2 py-0.5 text-[11px] font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-md capitalize">
                      {col.status}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-xs pt-2 border-t border-slate-800/80">
                    <span className="text-slate-400">
                      Vectors: <strong className="text-slate-200">{col.points_count}</strong>
                    </span>
                    <span className="font-mono text-[11px] text-indigo-300 bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                      {col.vector_size}-dim ({col.distance})
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Selected Collection Toolbar & Vector Items */}
        {selectedCollection && (
          <div className="space-y-4">
            {/* Toolbar Control Bar */}
            <div className="glass-card p-4 rounded-2xl border border-slate-800 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
              <div className="flex flex-wrap items-center gap-3 flex-1">
                {/* Search Input */}
                <div className="relative min-w-[220px] flex-1">
                  <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Search item name, category, subcategory, price or text..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-10 pr-4 py-2 bg-slate-900/80 border border-slate-700/80 rounded-xl text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition"
                  />
                </div>

                {/* Category Filter */}
                {categoriesList.length > 0 && (
                  <select
                    value={selectedCatFilter}
                    onChange={(e) => setSelectedCatFilter(e.target.value)}
                    className="py-2 px-3 bg-slate-900/80 border border-slate-700/80 rounded-xl text-sm text-slate-200 focus:outline-none focus:border-indigo-500 transition cursor-pointer max-w-[180px]"
                  >
                    <option value="all">All Categories ({categoriesList.length})</option>
                    {categoriesList.map((cat) => (
                      <option key={cat} value={cat}>
                        {cat}
                      </option>
                    ))}
                  </select>
                )}

                {/* Document Name Filter */}
                {docNamesList.length > 0 && (
                  <select
                    value={selectedDocFilter}
                    onChange={(e) => setSelectedDocFilter(e.target.value)}
                    className="py-2 px-3 bg-slate-900/80 border border-slate-700/80 rounded-xl text-sm text-slate-200 focus:outline-none focus:border-indigo-500 transition cursor-pointer max-w-[180px]"
                  >
                    <option value="all">All Documents ({docNamesList.length})</option>
                    {docNamesList.map((name) => (
                      <option key={name} value={name}>
                        {name}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {/* Right View Switcher & Action Buttons */}
              <div className="flex items-center gap-2 flex-wrap">
                {/* View Mode Toggle Buttons */}
                <div className="flex items-center bg-slate-950 p-1 rounded-xl border border-slate-800">
                  <button
                    onClick={() => setViewMode("sections")}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition cursor-pointer ${
                      viewMode === "sections" ? "bg-indigo-600 text-white shadow" : "text-slate-400 hover:text-white"
                    }`}
                  >
                    <FolderOpen className="w-3.5 h-3.5" />
                    <span>Category Sections</span>
                  </button>
                  <button
                    onClick={() => setViewMode("table")}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition cursor-pointer ${
                      viewMode === "table" ? "bg-indigo-600 text-white shadow" : "text-slate-400 hover:text-white"
                    }`}
                  >
                    <TableIcon className="w-3.5 h-3.5" />
                    <span>Table</span>
                  </button>
                  <button
                    onClick={() => setViewMode("grid")}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition cursor-pointer ${
                      viewMode === "grid" ? "bg-indigo-600 text-white shadow" : "text-slate-400 hover:text-white"
                    }`}
                  >
                    <LayoutGrid className="w-3.5 h-3.5" />
                    <span>Grid</span>
                  </button>
                  <button
                    onClick={() => setViewMode("json")}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition cursor-pointer ${
                      viewMode === "json" ? "bg-indigo-600 text-white shadow" : "text-slate-400 hover:text-white"
                    }`}
                  >
                    <Code className="w-3.5 h-3.5" />
                    <span>JSON</span>
                  </button>
                </div>

                <button
                  onClick={() => setShowAddModal(true)}
                  className="px-4 py-2 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white text-xs font-semibold rounded-xl shadow-lg shadow-indigo-600/20 transition flex items-center gap-1.5 cursor-pointer"
                >
                  <Plus className="w-4 h-4" />
                  <span>Add Point</span>
                </button>

                <button
                  onClick={handleClearCollection}
                  className="px-3 py-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 rounded-xl text-xs font-semibold transition flex items-center gap-1.5 cursor-pointer"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Clear Collection</span>
                </button>
              </div>
            </div>

            {/* Info Banner */}
            <div className="flex items-center justify-between text-xs text-slate-400 px-1">
              <span>
                Found <strong className="text-slate-200">{categoryKeys.length}</strong> categories containing{" "}
                <strong className="text-slate-200">{totalItemCount}</strong> menu items in collection{" "}
                <strong className="text-indigo-400">{selectedCollection}</strong>
              </span>
            </div>

            {/* Loading state */}
            {loadingPoints ? (
              <div className="glass-card p-12 text-center text-slate-400 rounded-2xl border border-slate-800 flex items-center justify-center gap-3">
                <RefreshCw className="w-5 h-5 animate-spin text-indigo-400" />
                <span>Fetching vector points from Qdrant...</span>
              </div>
            ) : categoryKeys.length === 0 ? (
              <div className="glass-card p-12 text-center text-slate-400 rounded-2xl border border-slate-800">
                No menu items or vector points found matching your filter criteria.
              </div>
            ) : (
              <>
                {/* 1. CATEGORY SECTIONS VIEW (PERMANENTLY OPEN - NO ACCORDIONS) */}
                {viewMode === "sections" && (
                  <div className="space-y-6">
                    {categoryKeys.map((categoryName) => {
                      const categoryItems = categoryGroupedMap[categoryName] || [];

                      return (
                        <div
                          key={`cat-section-${categoryName}`}
                          className="glass-card rounded-2xl border border-slate-800 overflow-hidden shadow-xl transition-all"
                        >
                          {/* Permanent Category Header */}
                          <div className="w-full px-5 py-4 bg-slate-900/90 flex items-center justify-between border-b border-slate-800">
                            <div className="flex items-center gap-3">
                              <div className="p-2 bg-indigo-500/20 border border-indigo-500/30 rounded-xl text-indigo-400">
                                <FolderOpen className="w-5 h-5" />
                              </div>
                              <div className="text-left">
                                <div className="flex items-center gap-2">
                                  <h3 className="font-bold text-base text-slate-100 tracking-wide">
                                    {categoryName}
                                  </h3>
                                  <span className="px-2.5 py-0.5 text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 rounded-full">
                                    {categoryItems.length} items
                                  </span>
                                </div>
                              </div>
                            </div>
                          </div>

                          {/* Section Content Table (Always Open) */}
                          <div className="p-4 bg-slate-950/40">
                            <div className="overflow-x-auto rounded-xl border border-slate-800">
                                <table className="w-full text-left text-xs border-collapse">
                                  <thead>
                                    <tr className="bg-slate-900/90 text-slate-400 border-b border-slate-800 uppercase tracking-wider font-semibold">
                                      <th className="py-3 px-4">Subcategory</th>
                                      <th className="py-3 px-4">Item Name</th>
                                      <th className="py-3 px-4">Price (PKR)</th>
                                      <th className="py-3 px-4">Point ID & Vector Embedding Sample</th>
                                      <th className="py-3 px-4 text-right">Actions (1 by 1)</th>
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-slate-800/60 font-sans">
                                    {categoryItems.map((item, idx) => (
                                      <tr
                                        key={`acc-item-${item.pointId}-${idx}`}
                                        className="hover:bg-slate-900/60 transition-colors group"
                                      >
                                        {/* Subcategory */}
                                        <td className="py-3.5 px-4 whitespace-nowrap">
                                          {item.subcategory ? (
                                            <span className="px-2.5 py-1 text-xs font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30 rounded-md">
                                              {item.subcategory}
                                            </span>
                                          ) : (
                                            <span className="text-slate-600 font-mono text-xs">-</span>
                                          )}
                                        </td>

                                        {/* Item Name */}
                                        <td className="py-3.5 px-4 max-w-sm">
                                          <span className="font-bold text-slate-100 text-sm block">
                                            {item.itemName}
                                          </span>
                                        </td>

                                        {/* Price */}
                                        <td className="py-3.5 px-4 whitespace-nowrap">
                                          <span className="px-2.5 py-1 text-xs font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-md font-mono">
                                            {item.price}
                                          </span>
                                        </td>

                                        {/* Point ID & Vector Sample */}
                                        <td className="py-3.5 px-4 max-w-xs">
                                          <div className="space-y-1">
                                            <span className="font-mono text-[10px] text-slate-400 block truncate" title={item.pointId}>
                                              ID: {item.pointId}
                                            </span>
                                            {item.vectorPreview && item.vectorPreview.length > 0 && (
                                              <span className="text-[10px] font-mono text-indigo-300 bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800 block truncate">
                                                Vector Embedding Sample: [{item.vectorPreview.join(", ")}, ...]
                                              </span>
                                            )}
                                          </div>
                                        </td>

                                        {/* Actions (1-by-1 Edit / Delete) */}
                                        <td className="py-3.5 px-4 whitespace-nowrap text-right">
                                          <div className="flex items-center justify-end gap-1.5">
                                            <button
                                              onClick={() => handleCopy(item.pointId, item.fullText)}
                                              className="p-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-slate-300 hover:text-white transition cursor-pointer"
                                              title="Copy Text Chunk"
                                            >
                                              {copiedId === item.pointId ? (
                                                <Check className="w-3.5 h-3.5 text-emerald-400" />
                                              ) : (
                                                <Copy className="w-3.5 h-3.5" />
                                              )}
                                            </button>

                                            <button
                                              onClick={() => handleOpenEdit(item)}
                                              className="p-1.5 bg-indigo-600/80 hover:bg-indigo-500 text-white rounded-lg transition cursor-pointer"
                                              title="Edit Item 1-by-1"
                                            >
                                              <Edit3 className="w-3.5 h-3.5" />
                                            </button>

                                            <button
                                              onClick={() => handleDeleteItem(item)}
                                              className="p-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 rounded-lg transition cursor-pointer"
                                              title="Delete Point 1-by-1"
                                            >
                                              <Trash2 className="w-3.5 h-3.5" />
                                            </button>
                                          </div>
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* 2. FLAT TABLE VIEW */}
                {viewMode === "table" && (
                  <div className="glass-card rounded-2xl border border-slate-800 overflow-hidden shadow-2xl">
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs border-collapse">
                        <thead>
                          <tr className="bg-slate-900/90 text-slate-300 border-b border-slate-800 uppercase tracking-wider font-semibold">
                            <th className="py-3.5 px-4">Category</th>
                            <th className="py-3.5 px-4">Subcategory</th>
                            <th className="py-3.5 px-4">Item Name</th>
                            <th className="py-3.5 px-4">Price (PKR)</th>
                            <th className="py-3.5 px-4">Vector Embedding Sample</th>
                            <th className="py-3.5 px-4 text-right">Actions (1-by-1)</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60 font-sans">
                          {allParsedItems.map((item, idx) => (
                            <tr
                              key={`tbl-flat-${item.pointId}-${idx}`}
                              className="hover:bg-slate-900/60 transition-colors group"
                            >
                              <td className="py-3.5 px-4 whitespace-nowrap font-semibold text-indigo-300">
                                {item.category}
                              </td>
                              <td className="py-3.5 px-4 whitespace-nowrap text-purple-300">
                                {item.subcategory ? (
                                  <span className="px-2.5 py-1 text-xs font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30 rounded-md">
                                    {item.subcategory}
                                  </span>
                                ) : (
                                  <span className="text-slate-600 font-mono text-xs">-</span>
                                )}
                              </td>
                              <td className="py-3.5 px-4 max-w-xs font-bold text-slate-100">
                                {item.itemName}
                              </td>
                              <td className="py-3.5 px-4 whitespace-nowrap font-bold text-emerald-400 font-mono">
                                {item.price}
                              </td>
                              <td className="py-3.5 px-4 max-w-xs text-[11px] font-mono text-slate-400">
                                [{item.vectorPreview.join(", ")}, ...]
                              </td>
                              <td className="py-3.5 px-4 whitespace-nowrap text-right">
                                <div className="flex items-center justify-end gap-1.5">
                                  <button
                                    onClick={() => handleOpenEdit(item)}
                                    className="p-1.5 bg-indigo-600/80 hover:bg-indigo-500 text-white rounded-lg transition cursor-pointer"
                                  >
                                    <Edit3 className="w-3.5 h-3.5" />
                                  </button>
                                  <button
                                    onClick={() => handleDeleteItem(item)}
                                    className="p-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 rounded-lg transition cursor-pointer"
                                  >
                                    <Trash2 className="w-3.5 h-3.5" />
                                  </button>
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* 3. GRID VIEW */}
                {viewMode === "grid" && (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {allParsedItems.map((item, idx) => (
                      <div
                        key={`grd-${item.pointId}-${idx}`}
                        className="glass-card p-5 rounded-2xl border border-slate-800 hover:border-slate-700 transition flex flex-col justify-between space-y-3"
                      >
                        <div className="space-y-2">
                          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                            <span className="font-bold text-slate-100 text-sm truncate max-w-[160px]">
                              {item.itemName}
                            </span>
                            <span className="text-xs font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                              {item.price}
                            </span>
                          </div>

                          <div className="flex items-center gap-1.5 text-xs">
                            <span className="bg-indigo-500/20 text-indigo-300 px-2 py-0.5 rounded font-semibold">
                              {item.category}
                            </span>
                            <span className="bg-purple-500/20 text-purple-300 px-2 py-0.5 rounded font-medium">
                              {item.subcategory}
                            </span>
                          </div>

                          <div className="p-3 bg-slate-950 border border-slate-800/80 rounded-xl text-xs text-slate-100 font-sans leading-relaxed max-h-36 overflow-y-auto whitespace-pre-line">
                            {item.fullText}
                          </div>
                        </div>

                        <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
                          <button
                            onClick={() => handleOpenEdit(item)}
                            className="p-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg cursor-pointer"
                          >
                            <Edit3 className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleDeleteItem(item)}
                            className="p-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 rounded-lg cursor-pointer"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* 4. JSON VIEW */}
                {viewMode === "json" && (
                  <div className="glass-card p-5 rounded-2xl border border-slate-800">
                    <pre className="text-xs font-mono text-emerald-400 bg-slate-950 p-4 rounded-xl border border-slate-800/80 overflow-x-auto max-h-[600px]">
                      {JSON.stringify(allParsedItems, null, 2)}
                    </pre>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {/* EDIT VECTOR POINT MODAL (1-by-1) */}
      {editingItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-fade-in">
          <div className="glass-card w-full max-w-xl rounded-2xl border border-slate-700 shadow-2xl overflow-hidden flex flex-col space-y-4 p-6">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-bold text-slate-100 text-base flex items-center gap-2">
                <Edit3 className="w-5 h-5 text-indigo-400" />
                Edit Item Payload & Re-Embed Vector (1-by-1)
              </h3>
              <button
                onClick={() => setEditingItem(null)}
                className="p-1 rounded-lg bg-slate-800 text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium text-slate-400">Point ID</label>
                <input
                  type="text"
                  disabled
                  value={editingItem.pointId}
                  className="w-full mt-1 p-2 bg-slate-950 border border-slate-800 rounded-xl font-mono text-xs text-slate-400"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-slate-400">Item Name</label>
                  <input
                    type="text"
                    value={editItemName}
                    onChange={(e) => setEditItemName(e.target.value)}
                    className="w-full mt-1 p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-400">Price (PKR)</label>
                  <input
                    type="text"
                    value={editPrice}
                    onChange={(e) => setEditPrice(e.target.value)}
                    className="w-full mt-1 p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-slate-400">Category</label>
                  <input
                    type="text"
                    value={editCategory}
                    onChange={(e) => setEditCategory(e.target.value)}
                    className="w-full mt-1 p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-400">Subcategory</label>
                  <input
                    type="text"
                    value={editSubcategory}
                    onChange={(e) => setEditSubcategory(e.target.value)}
                    className="w-full mt-1 p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-slate-400">
                  Full Payload Text (Will be embedded with OpenAI text-embedding-3-small)
                </label>
                <textarea
                  rows={4}
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  className="w-full mt-1 p-3 bg-slate-950 border border-slate-800 rounded-xl text-sm text-slate-100 focus:border-indigo-500 focus:outline-none font-sans"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
              <button
                onClick={() => setEditingItem(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-xl cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveEdit}
                disabled={savingEdit}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-xl cursor-pointer flex items-center gap-2 disabled:opacity-50"
              >
                {savingEdit ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                <span>Save & Re-Embed Vector</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ADD NEW VECTOR POINT MODAL (1-by-1) */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-fade-in">
          <div className="glass-card w-full max-w-xl rounded-2xl border border-slate-700 shadow-2xl overflow-hidden flex flex-col space-y-4 p-6">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-bold text-slate-100 text-base flex items-center gap-2">
                <Plus className="w-5 h-5 text-purple-400" />
                Add New Item / Vector Point to '{selectedCollection}'
              </h3>
              <button
                onClick={() => setShowAddModal(false)}
                className="p-1 rounded-lg bg-slate-800 text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-slate-400">Item Name</label>
                  <input
                    type="text"
                    placeholder='e.g. Chicken Lovers Pizza (Small 6")'
                    value={addItemName}
                    onChange={(e) => setAddItemName(e.target.value)}
                    className="w-full mt-1 p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-400">Price (PKR)</label>
                  <input
                    type="text"
                    placeholder="e.g. 320"
                    value={addPrice}
                    onChange={(e) => setAddPrice(e.target.value)}
                    className="w-full mt-1 p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-slate-400">Category</label>
                  <input
                    type="text"
                    placeholder="e.g. PIZZA"
                    value={addCategory}
                    onChange={(e) => setAddCategory(e.target.value)}
                    className="w-full mt-1 p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-400">Subcategory</label>
                  <input
                    type="text"
                    placeholder="e.g. CHICKEN"
                    value={addSubcategory}
                    onChange={(e) => setAddSubcategory(e.target.value)}
                    className="w-full mt-1 p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-slate-400">Additional Text Chunk (Optional)</label>
                <textarea
                  rows={3}
                  placeholder="Optional custom text chunk..."
                  value={addText}
                  onChange={(e) => setAddText(e.target.value)}
                  className="w-full mt-1 p-3 bg-slate-950 border border-slate-800 rounded-xl text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-xl cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveAdd}
                disabled={savingAdd}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold rounded-xl cursor-pointer flex items-center gap-2 disabled:opacity-50"
              >
                {savingAdd ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                <span>Embed & Add to Qdrant</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
