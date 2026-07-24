"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const navSections = [
  {
    key: "dashboard",
    label: "داشبورد",
    links: [
      { href: "/dashboard", label: "داشبورد اصلی" },
      { href: "/finance/dashboard", label: "داشبورد مالی" },
    ],
  },
  {
    key: "inventory",
    label: "موجودی",
    links: [
      { href: "/inventory/products", label: "محصولات" },
      { href: "/inventory/vendors", label: "تامین‌کنندگان" },
      { href: "/inventory/purchases", label: "خریدها" },
    ],
  },
  {
    key: "employees",
    label: "کارمندان",
    links: [
      { href: "/employees", label: "کارمندان" },
      { href: "/payroll", label: "حقوق و دستمزد" },
    ],
  },
  {
    key: "finance",
    label: "مالی",
    links: [
      { href: "/finance/dashboard", label: "داشبورد مالی" },
      { href: "/finance/transactions", label: "تراکنش‌ها" },
    ],
  },
  {
    key: "surgeries",
    label: "جراحی‌ها",
    links: [
      { href: "/surgeries", label: "عمل‌های جراحی" },
    ],
  },
  {
    key: "contacts",
    label: "تماس‌ها",
    links: [
      { href: "/contacts", label: "دفترچه تماس" },
    ],
  },
];

export default function Sidebar({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const [openSections, setOpenSections] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {};
    for (const sec of navSections) {
      if (sec.links.some((l) => pathname.startsWith(l.href))) {
        initial[sec.key] = true;
      }
    }
    return initial;
  });

  const toggle = (key: string) => {
    setOpenSections((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-40 lg:hidden"
          onClick={onClose}
        />
      )}
      <aside
        className={`fixed top-16 right-0 bottom-0 w-[260px] bg-sidebar-bg border-l border-white/6 overflow-y-auto z-50 transition-transform duration-200 lg:sticky lg:top-16 lg:translate-x-0 lg:z-10 ${
          isOpen ? "translate-x-0" : "translate-x-full lg:translate-x-0"
        }`}
      >
        <div className="flex items-center gap-3 px-4 py-5 border-b border-white/8">
          <div className="w-10 h-10 rounded-[10px] bg-gradient-to-br from-purple to-[#3385CC] flex items-center justify-center shadow-lg shadow-purple/35 shrink-0">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round">
              <path d="M11 2a2 2 0 0 0-2 2v5H4a2 2 0 0 0-2 2v2c0 1.1.9 2 2 2h5v5c0 1.1.9 2 2 2h2a2 2 0 0 0 2-2v-5h5a2 2 0 0 0 2-2v-2a2 2 0 0 0-2-2h-5V4a2 2 0 0 0-2-2h-2z"/>
            </svg>
          </div>
          <div>
            <div className="text-[15px] font-bold text-white tracking-tight">مرکز جراحی</div>
            <div className="text-[10.5px] font-medium text-white/42 mt-px">سامانه مدیریت یکپارچه</div>
          </div>
        </div>

        <nav className="p-2.5 pb-8">
          {navSections.map((sec) => {
            const isOpenSection = !!openSections[sec.key];
            return (
              <div key={sec.key} className="mb-0">
                <button
                  onClick={() => toggle(sec.key)}
                  className="flex items-center w-full px-3 py-2.5 text-white/55 text-xs font-semibold tracking-tight rounded-lg hover:text-white/88 hover:bg-white/6 transition-colors"
                >
                  <span>{sec.label}</span>
                  <svg
                    className={`mr-auto w-2 h-2 border-r-[1.5px] border-b-[1.5px] border-current transition-transform duration-200 ${
                      isOpenSection ? "rotate-45 translate-y-[2px]" : "-rotate-45 -translate-y-[2px]"
                    }`}
                    viewBox="0 0 8 8"
                    fill="none"
                  />
                </button>
                <div
                  className={`overflow-hidden transition-[max-height] duration-250 ease-out ${
                    isOpenSection ? "max-h-[320px]" : "max-h-0"
                  }`}
                >
                  {sec.links.map((link) => {
                    const isActive = pathname === link.href;
                    return (
                      <Link
                        key={link.href}
                        href={link.href}
                        onClick={onClose}
                        className={`flex items-center px-6 py-[7px] text-[13.5px] transition-colors border-r-[3px] border-transparent ${
                          isActive
                            ? "bg-purple/25 text-white font-semibold border-r-[#3385CC]"
                            : "text-white/60 hover:bg-white/7 hover:text-white/92"
                        }`}
                      >
                        {link.label}
                      </Link>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </nav>

        <div className="flex items-center gap-2.5 px-4 py-3.5 border-t border-white/8 mt-auto">
          <div className="w-[34px] h-[34px] rounded-full bg-purple/45 flex items-center justify-center text-[14px] font-bold text-white shrink-0">آ</div>
          <div className="min-w-0">
            <div className="text-[13px] font-semibold text-white/85 truncate max-w-[140px]">آیان رحمتی</div>
            <div className="text-[11px] text-white/40 mt-px">مدیر سیستم</div>
          </div>
        </div>
      </aside>
    </>
  );
}
