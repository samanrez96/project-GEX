"use client";

import { useEffect, useState } from "react";
import { get, type PaginatedResponse } from "@/lib/api";
import { toPersianDigits } from "@/lib/utils";

interface Contact {
  id: number;
  full_name: string;
  phone_number: string;
  specialty: number;
  specialty_name: string;
  email: string;
  address: string;
  notes: string;
}

const PAGE_SIZE = 20;

export default function ContactsList() {
  const [items, setItems] = useState<Contact[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (search) params.set("search", search);
    get<PaginatedResponse<Contact>>(`/contacts/doctors/?${params}`)
      .then((d) => { setItems(d.results || []); setCount(d.count); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [page, search]);

  const totalPages = Math.ceil(count / PAGE_SIZE);

  return (
    <div dir="rtl">
      <div className="flex items-start justify-between gap-4 mb-7 flex-wrap">
        <div className="flex-1 min-w-0">
          <span className="block text-[11px] font-bold text-purple tracking-widest uppercase mb-1 opacity-85">تماس‌ها</span>
          <h1 className="text-[26px] font-bold text-text leading-tight m-0">دفترچه تماس</h1>
        </div>
        <div className="flex gap-2 items-center shrink-0 pt-1.5">
          <button className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl text-sm font-medium bg-purple text-white border border-purple shadow-[0_1px_3px_rgba(0,102,179,.28)] hover:shadow-[0_3px_8px_rgba(0,102,179,.30)] transition-shadow cursor-pointer">
            + افزودن تماس
          </button>
        </div>
      </div>

      <div className="bg-card border border-border rounded-2xl p-4 shadow-sm mb-4 flex gap-3 items-end flex-wrap">
        <div className="flex flex-col gap-1 min-w-0">
          <label className="text-[11px] font-semibold text-muted">جستجو</label>
          <input
            type="text"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-card outline-none focus:border-purple focus:shadow-[0_0_0_3px_rgba(0,102,179,.12)] transition-all"
            placeholder="نام، تلفن، تخصص..."
          />
        </div>
      </div>

      <div className="bg-card border border-border rounded-2xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                {["نام", "تلفن", "تخصص", "ایمیل"].map((h) => (
                  <th key={h} className="bg-bg-page px-4 py-2.5 text-[11px] font-bold text-muted text-right tracking-[.4px] uppercase border-b-2 border-border whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={4} className="text-center py-7 text-muted text-sm">در حال بارگذاری…</td></tr>
              ) : items.length === 0 ? (
                <tr><td colSpan={4} className="text-center py-7 text-muted text-sm">مخاطبی یافت نشد</td></tr>
              ) : (
                items.map((c) => (
                  <tr key={c.id} className="hover:bg-bg-page">
                    <td className="px-4 py-3 text-sm font-semibold text-text border-b border-border/55">{c.full_name || "—"}</td>
                    <td className="px-4 py-3 text-sm text-text border-b border-border/55 text-left" dir="ltr">{c.phone_number || "—"}</td>
                    <td className="px-4 py-3 border-b border-border/55">
                      {c.specialty_name ? (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-light text-purple">{c.specialty_name}</span>
                      ) : "—"}
                    </td>
                    <td className="px-4 py-3 text-sm text-text border-b border-border/55 text-left" dir="ltr">{c.email || "—"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-2.5 border-t border-border text-xs text-muted">
            <span>صفحه {toPersianDigits(page)} از {toPersianDigits(totalPages)}</span>
            <div className="flex gap-1">
              <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="px-3 py-1 rounded-lg border border-border disabled:opacity-40 cursor-pointer hover:bg-bg-page transition-colors">قبلی</button>
              <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} className="px-3 py-1 rounded-lg border border-border disabled:opacity-40 cursor-pointer hover:bg-bg-page transition-colors">بعدی</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}