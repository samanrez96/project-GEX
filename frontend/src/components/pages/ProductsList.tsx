"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { get, post, type PaginatedResponse, type Product } from "@/lib/api";
import { formatCurrency, toPersianDigits } from "@/lib/utils";

const PAGE_SIZE = 20;

const STOCK_STATUS_STYLE: Record<string, string> = {
  "موجود":     "bg-green-bg text-green",
  "کم‌موجودی": "bg-amber-bg text-amber",
  "ناموجود":   "bg-red-bg text-red",
};

const TYPE_DISPLAY: Record<string, string> = {
  medicine:  "دارو",
  equipment: "تجهیزات",
};

interface AddProductForm {
  internal_code: string;
  name: string;
  product_type: "medicine" | "equipment";
  purchase_price: string;
  minimum_stock: string;
  internal_notes: string;
  initial_quantity: string;
}

const EMPTY_FORM: AddProductForm = {
  internal_code: "",
  name: "",
  product_type: "medicine",
  purchase_price: "0",
  minimum_stock: "0",
  internal_notes: "",
  initial_quantity: "0",
};

export default function ProductsList() {
  const [items, setItems] = useState<Product[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<AddProductForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const fetchProducts = () => {
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (search) params.set("search", search);
    get<PaginatedResponse<Product>>(`/inventory/products/?${params}`)
      .then((d) => { setItems(d.results || []); setCount(d.count); })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchProducts(); }, [page, search]);

  const totalPages = Math.ceil(count / PAGE_SIZE);

  const openModal = () => { setForm(EMPTY_FORM); setError(""); setShowModal(true); };
  const closeModal = () => { setShowModal(false); setError(""); };

  const handleSubmit = async () => {
    if (!form.internal_code.trim()) { setError("کد داخلی الزامی است."); return; }
    if (!form.name.trim()) { setError("نام محصول الزامی است."); return; }
    setSaving(true);
    setError("");
    try {
      const payload: Record<string, unknown> = {
        internal_code: form.internal_code.trim(),
        name: form.name.trim(),
        product_type: form.product_type,
        purchase_price: form.purchase_price || "0",
        minimum_stock: form.minimum_stock || "0",
        internal_notes: form.internal_notes.trim(),
      };
      const created = await post<{ id: number }>("/inventory/products/", payload);
      const initQty = parseFloat(form.initial_quantity || "0");
      if (initQty > 0) {
        // NOTE: `unit` is NOT part of the stock-movement API contract —
        // the backend derives it from the product record.
        await post("/inventory/stock-movements/", {
          product: created.id,
          quantity: initQty,
          movement_type: "IN",
          source_type: "MANUAL_ADJUSTMENT",
          description: "موجودی اولیه",
        }).catch(() => {});
      }
      closeModal();
      setPage(1);
      fetchProducts();
    } catch {
      setError("خطا در ذخیره محصول. لطفاً دوباره تلاش کنید.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div dir="rtl">
      <div className="flex items-start justify-between gap-4 mb-7 flex-wrap">
        <div className="flex-1 min-w-0">
          <span className="block text-[11px] font-bold text-purple tracking-widest uppercase mb-1 opacity-85">موجودی</span>
          <h1 className="text-[26px] font-bold text-text leading-tight m-0">محصولات</h1>
        </div>
        <div className="flex gap-2 items-center shrink-0 pt-1.5">
          <button
            onClick={openModal}
            className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl text-sm font-medium bg-purple text-white border border-purple shadow-[0_1px_3px_rgba(0,102,179,.28)] hover:shadow-[0_3px_8px_rgba(0,102,179,.30)] transition-shadow cursor-pointer"
          >
            + افزودن محصول
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 mb-5">
        <div className="bg-card border border-border rounded-2xl p-5 shadow-sm">
          <div className="text-xs font-bold text-muted tracking-[.6px] uppercase mb-2">کل محصولات</div>
          <div className="text-[22px] font-extrabold text-text-strong">{toPersianDigits(count)}</div>
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
            placeholder="نام یا کد محصول..."
          />
        </div>
      </div>

      <div className="bg-card border border-border rounded-2xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                {["کد داخلی", "نام محصول", "نوع", "تعداد", "قیمت", "وضعیت موجودی"].map((h) => (
                  <th key={h} className="bg-bg-page px-4 py-2.5 text-[11px] font-bold text-muted text-right tracking-[.4px] uppercase border-b-2 border-border whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} className="text-center py-7 text-muted text-sm">در حال بارگذاری…</td></tr>
              ) : items.length === 0 ? (
                <tr><td colSpan={6} className="text-center py-7 text-muted text-sm">محصولی یافت نشد</td></tr>
              ) : (
                items.map((p) => (
                  <tr key={p.id} className="hover:bg-bg-page cursor-pointer">
                    <td className="px-4 py-3 text-sm font-mono text-muted border-b border-border/55">
                      <Link href={`/inventory/products/${p.id}`} className="hover:text-purple transition-colors">
                        {p.internal_code || "—"}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-sm font-semibold text-text border-b border-border/55">
                      <Link href={`/inventory/products/${p.id}`} className="hover:text-purple transition-colors">
                        {p.name}
                      </Link>
                    </td>
                    <td className="px-4 py-3 border-b border-border/55">
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${p.product_type === "medicine" ? "bg-purple-light text-purple" : "bg-amber-bg text-amber"}`}>
                        {p.product_type_display || TYPE_DISPLAY[p.product_type] || p.product_type}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm font-bold text-text border-b border-border/55 text-left" dir="ltr">
                      {toPersianDigits(parseFloat(p.current_stock || "0").toString())}
                    </td>
                    <td className="px-4 py-3 text-sm text-text border-b border-border/55 text-left" dir="ltr">
                      {formatCurrency(parseFloat(p.purchase_price || "0"))}
                    </td>
                    <td className="px-4 py-3 border-b border-border/55">
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${STOCK_STATUS_STYLE[p.stock_status] || "bg-gray-100 text-gray-600"}`}>
                        {p.stock_status}
                      </span>
                    </td>
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

      {/* Add Product Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-card border border-border rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto" dir="rtl">
            <div className="flex items-center justify-between px-6 py-4 border-b border-border">
              <h2 className="text-lg font-bold text-text">افزودن محصول جدید</h2>
              <button onClick={closeModal} className="text-muted hover:text-text transition-colors text-xl cursor-pointer">×</button>
            </div>
            <div className="px-6 py-5 space-y-4">
              {error && (
                <div className="bg-red-bg border border-red/30 text-red rounded-xl px-4 py-3 text-sm">{error}</div>
              )}
              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-semibold text-muted">کد داخلی <span className="text-red">*</span></label>
                  <input
                    type="text"
                    value={form.internal_code}
                    onChange={(e) => setForm({ ...form, internal_code: e.target.value })}
                    className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple focus:shadow-[0_0_0_3px_rgba(0,102,179,.12)] transition-all"
                    placeholder="مثال: MED-001"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-semibold text-muted">نوع محصول <span className="text-red">*</span></label>
                  <select
                    value={form.product_type}
                    onChange={(e) => setForm({ ...form, product_type: e.target.value as "medicine" | "equipment" })}
                    className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple focus:shadow-[0_0_0_3px_rgba(0,102,179,.12)] transition-all"
                  >
                    <option value="medicine">دارو</option>
                    <option value="equipment">تجهیزات</option>
                  </select>
                </div>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-muted">نام محصول <span className="text-red">*</span></label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple focus:shadow-[0_0_0_3px_rgba(0,102,179,.12)] transition-all"
                  placeholder="نام محصول را وارد کنید"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-semibold text-muted">تعداد اولیه</label>
                  <input
                    type="number"
                    min="0"
                    value={form.initial_quantity}
                    onChange={(e) => setForm({ ...form, initial_quantity: e.target.value })}
                    className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple focus:shadow-[0_0_0_3px_rgba(0,102,179,.12)] transition-all"
                    placeholder="۰"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-semibold text-muted">حداقل موجودی</label>
                  <input
                    type="number"
                    min="0"
                    value={form.minimum_stock}
                    onChange={(e) => setForm({ ...form, minimum_stock: e.target.value })}
                    className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple focus:shadow-[0_0_0_3px_rgba(0,102,179,.12)] transition-all"
                    placeholder="۰"
                  />
                </div>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-muted">قیمت خرید (تومان)</label>
                <input
                  type="number"
                  min="0"
                  value={form.purchase_price}
                  onChange={(e) => setForm({ ...form, purchase_price: e.target.value })}
                  className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple focus:shadow-[0_0_0_3px_rgba(0,102,179,.12)] transition-all"
                  placeholder="۰"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-muted">توضیحات داخلی</label>
                <textarea
                  value={form.internal_notes}
                  onChange={(e) => setForm({ ...form, internal_notes: e.target.value })}
                  rows={2}
                  className="px-3 py-2 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple focus:shadow-[0_0_0_3px_rgba(0,102,179,.12)] transition-all resize-none"
                  placeholder="یادداشت داخلی (اختیاری)"
                />
              </div>
            </div>
            <div className="flex gap-2 px-6 py-4 border-t border-border justify-end">
              <button
                onClick={closeModal}
                className="px-5 py-2 rounded-xl text-sm font-medium border border-border text-muted hover:bg-bg-page transition-colors cursor-pointer"
              >
                انصراف
              </button>
              <button
                onClick={handleSubmit}
                disabled={saving}
                className="px-5 py-2 rounded-xl text-sm font-medium bg-purple text-white disabled:opacity-60 hover:shadow-[0_3px_8px_rgba(0,102,179,.30)] transition-shadow cursor-pointer"
              >
                {saving ? "در حال ذخیره…" : "ذخیره محصول"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}