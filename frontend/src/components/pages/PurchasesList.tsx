"use client";

import { useEffect, useState } from "react";
import { get, type PaginatedResponse, type Purchase } from "@/lib/api";
import { formatCurrency, formatDate, toPersianDigits, getPurchaseStatusLabel } from "@/lib/utils";

const PAGE_SIZE = 20;

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-amber-bg text-amber",
  confirmed: "bg-green-bg text-green",
  cancelled: "bg-red-bg text-red",
};

export default function PurchasesList() {
  const [items, setItems] = useState<Purchase[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (search) params.set("search", search);
    if (statusFilter) params.set("status", statusFilter);
    get<PaginatedResponse<Purchase>>(`/inventory/purchases/?${params}`)
      .then((d) => { setItems(d.results || []); setCount(d.count); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [page, search, statusFilter]);

  const totalPages = Math.ceil(count / PAGE_SIZE);

  return (
    <div dir="rtl">
      <div className="flex items-start justify-between gap-4 mb-7 flex-wrap">
        <div className="flex-1 min-w-0">
          <span className="block text-[11px] font-bold text-purple tracking-widest uppercase mb-1 opacity-85">موجودی</span>
          <h1 className="text-[26px] font-bold text-text leading-tight m-0">خریدها</h1>
        </div>
        <div className="flex gap-2 items-center shrink-0 pt-1.5">
          <button className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl text-sm font-medium bg-purple text-white border border-purple shadow-[0_1px_3px_rgba(0,102,179,.28)] hover:shadow-[0_3px_8px_rgba(0,102,179,.30)] transition-shadow cursor-pointer">
            + افزودن خرید
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
            placeholder="تامین‌کننده..."
          />
        </div>
        <div className="flex flex-col gap-1 min-w-0">
          <label className="text-[11px] font-semibold text-muted">وضعیت</label>
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
            className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-card outline-none focus:border-purple focus:shadow-[0_0_0_3px_rgba(0,102,179,.12)] transition-all"
          >
            <option value="">همه</option>
            <option value="PENDING">در انتظار تأیید</option>
            <option value="CONFIRMED">تأیید شده</option>
            <option value="CANCELLED">لغو شده</option>
          </select>
        </div>
      </div>

      <div className="bg-card border border-border rounded-2xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                {["تامین‌کننده", "تاریخ", "مبلغ کل", "وضعیت"].map((h) => (
                  <th key={h} className="bg-bg-page px-4 py-2.5 text-[11px] font-bold text-muted text-right tracking-[.4px] uppercase border-b-2 border-border whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={4} className="text-center py-7 text-muted text-sm">در حال بارگذاری…</td></tr>
              ) : items.length === 0 ? (
                <tr><td colSpan={4} className="text-center py-7 text-muted text-sm">خریدی یافت نشد</td></tr>
              ) : (
                items.map((p) => {
                  const statusClass = STATUS_STYLES[p.status?.toLowerCase()] || "bg-gray-100 text-gray-600";
                  return (
                    <tr key={p.id} className="hover:bg-bg-page">
                      <td className="px-4 py-3 text-sm font-semibold text-text border-b border-border/55">{p.vendor_name || "—"}</td>
                      <td className="px-4 py-3 text-sm text-text border-b border-border/55">{formatDate(p.purchase_date)}</td>
                      <td className="px-4 py-3 text-sm text-text border-b border-border/55 text-left font-bold" dir="ltr">{formatCurrency(parseFloat(p.total_amount || "0"))}</td>
                      <td className="px-4 py-3 border-b border-border/55">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${statusClass}`}>
                          {getPurchaseStatusLabel(p.status)}
                        </span>
                      </td>
                    </tr>
                  );
                })
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