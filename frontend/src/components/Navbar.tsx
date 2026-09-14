"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Sparkles,
  FileText,
  Database,
  Mic,
  Home,
  Info,
  Menu,
  X,
  Activity
} from "lucide-react";

export default function Navbar() {
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navLinks = [
    { name: "Home Hub", href: "/", icon: Home },
    { name: "Ocr", href: "/ocr", icon: Mic },

    { name: "Qdrant Vectors", href: "/get-vector-store-data", icon: Database },
    { name: "About", href: "/about", icon: Info },
  ];

  return (
    <nav className="sticky top-0 z-50 w-full backdrop-blur-md bg-slate-950/80 border-b border-slate-800/80 transition-all">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand Logo */}
          <Link href="/" className="flex items-center gap-3 group">
            <div className="p-2 bg-gradient-to-tr from-indigo-600 via-purple-600 to-pink-500 rounded-xl shadow-md shadow-indigo-600/30 group-hover:scale-105 transition">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <span className="font-extrabold text-lg bg-gradient-to-r from-white via-slate-200 to-indigo-300 bg-clip-text text-transparent">
                Spark AI
              </span>
              <span className="text-xs text-indigo-400 block -mt-1 font-mono">Assistant</span>
            </div>
          </Link>

          {/* Desktop Navigation Links */}
          <div className="hidden md:flex items-center gap-1.5 bg-slate-900/60 p-1.5 rounded-2xl border border-slate-800/80">
            {navLinks.map((link) => {
              const Icon = link.icon;
              const isActive = pathname === link.href;

              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all flex items-center gap-2 ${
                    isActive
                      ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
                  }`}
                >
                  <Icon className={`w-3.5 h-3.5 ${isActive ? "text-white" : "text-slate-400"}`} />
                  <span>{link.name}</span>
                </Link>
              );
            })}
          </div>

          {/* Right Status Badge */}
          <div className="hidden md:flex items-center gap-3">
            <div className="px-3 py-1 bg-emerald-500/10 border border-emerald-500/30 rounded-full flex items-center gap-2 text-xs text-emerald-400 font-medium">
              <Activity className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
              <span>FastAPI Online</span>
            </div>
          </div>

          {/* Mobile Menu Toggle Button */}
          <div className="md:hidden flex items-center">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-2 rounded-xl bg-slate-900 border border-slate-800 text-slate-400 hover:text-white transition cursor-pointer"
            >
              {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Drawer Menu */}
      {mobileMenuOpen && (
        <div className="md:hidden glass-card border-b border-slate-800 px-4 pt-2 pb-4 space-y-2 animate-fade-in">
          {navLinks.map((link) => {
            const Icon = link.icon;
            const isActive = pathname === link.href;

            return (
              <Link
                key={`mobile-${link.href}`}
                href={link.href}
                onClick={() => setMobileMenuOpen(false)}
                className={`w-full px-4 py-3 rounded-xl text-sm font-semibold transition flex items-center gap-3 ${
                  isActive
                    ? "bg-indigo-600 text-white shadow-lg"
                    : "text-slate-300 hover:bg-slate-900"
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{link.name}</span>
              </Link>
            );
          })}
        </div>
      )}
    </nav>
  );
}
