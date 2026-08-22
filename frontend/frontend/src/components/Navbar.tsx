"use client";

import Link from "next/link";

export default function Navbar({ onMenuToggle }: { onMenuToggle: () => void }) {
  return (
    <nav className="fixed top-0 right-0 left-0 h-16 bg-card border-b border-border flex items-center px-5 gap-3 z-50 shadow-sm">
      <button
        onClick={onMenuToggle}
        className="text-muted text-xl cursor-pointer p-1 rounded-md hover:bg-bg-page hover:text-text transition-colors lg:hidden"
        aria-label="نوار کناری"
      >
        ☰
      </button>
      <Link href="/dashboard" className="text-[16px] font-bold text-purple whitespace-nowrap">
        مرکز جراحی — مدیریت
      </Link>
      <div className="me-auto flex items-center gap-3">
        <span className="text-muted text-sm">آیان رحمتی</span>
        <button className="text-muted text-[13px] border border-border px-3.5 py-[5px] rounded-md cursor-pointer hover:bg-bg-page hover:border-purple hover:text-purple transition-colors">
          خروج
        </button>
      </div>
    </nav>
  );
}
