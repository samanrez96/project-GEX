"use client";

import { useEffect, useState } from "react";
import { get, type PaginatedResponse, type Transaction } from "@/lib/api";
import { formatCurrency, formatDate, toPersianDigits, getPaymentStatusLabel, getPaymentStatusColor } from "@/lib/utils";

const TYPE_MAP: Record<string, { cls: string; label: string }> = {
  income: { cls: "bg-green-bg text-green", label: "درآمد" },
  expense: { cls: "bg-red-bg text-red", label: "هزینه" },
};

const PAGE_SIZE = 20;

export default function TransactionsList() {
  const [items, setItems] = useState<Transaction[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [paymentFilter, setPaymentFilter] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (search) params.set("search", search);
    if (typeFilter) params.set("transaction_type", typeFilter);
    if (paymentFilter) params.set("payment_status", paymentFilter);
    get<PaginatedResponse<Transaction>>(`/finance/transactions/?${params}`)
      .then((d) => { setItems(d.results || []); setCount(d.count); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [page, search, typeFilter, paymentFilter]);

  const totalPages = Math.ceil(count / PAGE_SIZE);

  return (
    <div dir="rtl">
      <div className="flex items-start justify-between gap-4 mb-7 flex-wrap">
        <div className="flex-1 min-w-0">
          <span className="block text-[11px] font-bold text-purple tracking-widest uppercase mb-1 opacity-85">مالی</span>
          <h1 className="text-[26px] font-bold text-text leading-tight m-0">تراکنش‌ها</h1>
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
            placeholder="توضیحات..."
          />
        </div>
        <div className="flex flex-col gap-1 min-w-0">
          <label className="text-[11px] font-semibold text-muted">نوع</label>
          <select
            value={typeFilter}
            onChange={(e) => { setTypeFilter(e.target.value); setPage(1); }}
            className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-card outline-none focus:border-purple focus:shadow-[0_0_0_3px_rgba(0,102,179,.12)] transition-all"
          >
            <option value="">همه</option>
            <option value="income">درآمد</option>
            <option value="expense">هزینه</option>
          </select>
        </div>
        <div className="flex flex-col gap-1 min-w-0">
          <label className="text-[11px] font-semibold text-muted">وضعیت پرداخت</label>
          <select
            value={paymentFilter}
            onChange={(e) => { setPaymentFilter(e.target.value); setPage(1); }}
            className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-card outline-none focus:border-purple focus:shadow-[0_0_0_3px_rgba(0,102,179,.12)] transition-all"
          >
            <option value="">همه</option>
            <option value="pending">در انتظار پرداخت</option>
            <option value="partial">پرداخت ناقص</option>
            <option value="paid">پرداخت شده</option>
            <option value="cancelled">لغو شده</option>
          </select>
        </div>
      </div>

      <div className="bg-card border border-border rounded-2xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                {["تاریخ", "دسته‌بندی", "توضیحات", "مبلغ", "نوع", "وضعیت پرداخت"].map((h) => (
                  <th key={h} className="bg-bg-page px-4 py-2.5 text-[11px] font-bold text-muted text-right tracking-[.4px] uppercase border-b-2 border-border whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} className="text-center py-7 text-muted text-sm">در حال بارگذاری…</td></tr>
              ) : items.length === 0 ? (
                <tr><td colSpan={6} className="text-center py-7 text-muted text-sm">تراکنشی یافت نشد</td></tr>
              ) : (
                items.map((t) => {
                  const tp = TYPE_MAP[t.transaction_type] || { cls: "bg-gray-100 text-gray-600", label: t.transaction_type_display || t.transaction_type };
                  const pay = getPaymentStatusColor(t.payment_status);
                  return (
                    <tr key={t.id} className="hover:bg-bg-page">
                      <td className="px-4 py-3 text-sm text-text border-b border-border/55">{formatDate(t.transaction_date)}</td>
                      <td className="px-4 py-3 text-sm text-text border-b border-border/55">{t.category_name || t.category || "—"}</td>
                      <td className="px-4 py-3 text-sm text-text border-b border-border/55 max-w-[300px] truncate">{t.description || "—"}</td>
                      <td className="px-4 py-3 text-sm text-text border-b border-border/55 text-left font-bold" dir="ltr">{formatCurrency(parseFloat(t.amount || "0"))}</td>
                      <td className="px-4 py-3 border-b border-border/55">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${tp.cls}`}>{tp.label}</span>
                      </td>
                      <td className="px-4 py-3 border-b border-border/55">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${pay.bg} ${pay.text}`}>
                          {getPaymentStatusLabel(t.payment_status)}
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