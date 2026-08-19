"use client";

import { useEffect, useState } from "react";
import { get, post, patch, type PaginatedResponse, type Vendor } from "@/lib/api";
import { formatCurrency, toPersianDigits } from "@/lib/utils";

const PAGE_SIZE = 20;

const EMPTY_VENDOR = { name: "", phone_number: "", email: "", address: "", notes: "" };

export default function VendorsPage() {
  const [items, setItems] = useState<Vendor[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  const [showModal, setShowModal] = useState(false);
  const [editTarget, setEditTarget] = useState<Vendor | null>(null);
  const [form, setForm] = useState(EMPTY_VENDOR);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const fetchVendors = () => {
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (search) params.set("search", search);
    get<PaginatedResponse<Vendor>>(`/inventory/vendors/?${params}`)
      .then((d) => { setItems(d.results || []); setCount(d.count); })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchVendors(); }, [page, search]);

  const totalPages = Math.ceil(count / PAGE_SIZE);

  const openAdd = () => {
    setEditTarget(null);
    setForm(EMPTY_VENDOR);
    setError("");
    setShowModal(true);
  };

  const openEdit = (v: Vendor) => {
    setEditTarget(v);
    setForm({
      name: v.name || "",
      phone_number: v.phone_number || "",
      email: v.email || "",
      address: v.address || "",
      notes: v.notes || "",
    });
    setError("");
    setShowModal(true);
  };

  const closeModal = () => { setShowModal(false); setError(""); setEditTarget(null); };

  const handleSubmit = async () => {
    if (!form.name.trim()) { setError("نام تامین‌کننده الزامی است."); return; }
    setSaving(true);
    setError("");
    try {
      const payload = {
        name: form.name.trim(),
        phone_number: form.phone_number.trim(),
        email: form.email.trim() || null,
        address: form.address.trim(),
        notes: form.notes.trim(),
      };
      if (editTarget) {
        await patch(`/inventory/vendors/${editTarget.id}/`, payload);
        setSuccess("تامین‌کننده ویرایش شد.");
      } else {
        await post("/inventory/vendors/", payload);
        setSuccess("تامین‌کننده افزوده شد.");
      }
      closeModal();
      setPage(1);
      fetchVendors();
      setTimeout(() => setSuccess(""), 3000);
    } catch {
      setError("خطا در ذخیره اطلاعات.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div dir="rtl">
      <div className="flex items-start justify-between gap-4 mb-7 flex-wrap">
        <div className="flex-1 min-w-0">
          <span className="block text-[11px] font-bold text-purple tracking-widest uppercase mb-1 opacity-85">موجودی</span>
          <h1 className="text-[26px] font-bold text-text leading-tight m-0">تامین‌کنندگان</h1>
        </div>
        <div className="flex gap-2 items-center shrink-0 pt-1.5">
          <button
            onClick={openAdd}
            className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl text-sm font-medium bg-purple text-white border border-purple shadow-[0_1px_3px_rgba(0,102,179,.28)] hover:shadow-[0_3px_8px_rgba(0,102,179,.30)] transition-shadow cursor-pointer"
          >
            + افزودن تامین‌کننده
          </button>
        </div>
      </div>

      {success && (
        <div className="mb-4 bg-green-bg border border-green/30 text-green rounded-xl px-4 py-3 text-sm">{success}</div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 mb-5">
        <div className="bg-card border border-border rounded-2xl p-5 shadow-sm">
          <div className="text-xs font-bold text-muted tracking-[.6px] uppercase mb-2">کل تامین‌کنندگان</div>
          <div className="text-[22px] font-extrabold text-text-strong">{toPersianDigits(count)}</div>
        </div>
      </div>

      <div className="bg-card border border-border rounded-2xl p-4 shadow-sm mb-4">
        <div className="flex flex-col gap-1 min-w-0 max-w-xs">
          <label className="text-[11px] font-semibold text-muted">جستجو</label>
          <input
            type="text"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-card outline-none focus:border-purple focus:shadow-[0_0_0_3px_rgba(0,102,179,.12)] transition-all"
            placeholder="نام، تلفن، ایمیل..."
          />
        </div>
      </div>

      <div className="bg-card border border-border rounded-2xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                {["نام تامین‌کننده", "شماره تماس", "ایمیل", "آدرس", "عملیات"].map((h) => (
                  <th key={h} className="bg-bg-page px-4 py-2.5 text-[11px] font-bold text-muted text-right tracking-[.4px] uppercase border-b-2 border-border whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5} className="text-center py-7 text-muted text-sm">در حال بارگذاری…</td></tr>
              ) : items.length === 0 ? (
                <tr><td colSpan={5} className="text-center py-7 text-muted text-sm">تامین‌کننده‌ای یافت نشد</td></tr>
              ) : (
                items.map((v) => (
                  <tr key={v.id} className="hover:bg-bg-page">
                    <td className="px-4 py-3 text-sm font-semibold text-text border-b border-border/55">{v.name}</td>
                    <td className="px-4 py-3 text-sm text-text border-b border-border/55 text-left" dir="ltr">{v.phone_number || "—"}</td>
                    <td className="px-4 py-3 text-sm text-text border-b border-border/55 text-left" dir="ltr">{v.email || "—"}</td>
                    <td className="px-4 py-3 text-sm text-muted border-b border-border/55 max-w-[200px] truncate">{v.address || "—"}</td>
                    <td className="px-4 py-3 border-b border-border/55">
                      <button
                        onClick={() => openEdit(v)}
                        className="text-xs text-purple hover:text-purple/80 font-medium cursor-pointer"
                      >
                        ویرایش
                      </button>
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

      {/* Add/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-card border border-border rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto" dir="rtl">
            <div className="flex items-center justify-between px-6 py-4 border-b border-border">
              <h2 className="text-lg font-bold text-text">{editTarget ? "ویرایش تامین‌کننده" : "افزودن تامین‌کننده جدید"}</h2>
              <button onClick={closeModal} className="text-muted hover:text-text transition-colors text-xl cursor-pointer">×</button>
            </div>
            <div className="px-6 py-5 space-y-4">
              {error && (
                <div className="bg-red-bg border border-red/30 text-red rounded-xl px-4 py-3 text-sm">{error}</div>
              )}
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-muted">نام تامین‌کننده <span className="text-red">*</span></label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple focus:shadow-[0_0_0_3px_rgba(0,102,179,.12)] transition-all"
                  placeholder="نام شرکت یا فرد"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-muted">شماره تماس</label>
                <input
                  type="text"
                  value={form.phone_number}
                  onChange={(e) => setForm({ ...form, phone_number: e.target.value })}
                  className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple focus:shadow-[0_0_0_3px_rgba(0,102,179,.12)] transition-all"
                  placeholder="۰۹۱۲..."
                  dir="ltr"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-muted">ایمیل (اختیاری)</label>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple focus:shadow-[0_0_0_3px_rgba(0,102,179,.12)] transition-all"
                  placeholder="example@company.com"
                  dir="ltr"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-muted">آدرس (اختیاری)</label>
                <input
                  type="text"
                  value={form.address}
                  onChange={(e) => setForm({ ...form, address: e.target.value })}
                  className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple focus:shadow-[0_0_0_3px_rgba(0,102,179,.12)] transition-all"
                  placeholder="آدرس تامین‌کننده"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-muted">توضیحات (اختیاری)</label>
                <textarea
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                  rows={2}
                  className="px-3 py-2 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple focus:shadow-[0_0_0_3px_rgba(0,102,179,.12)] transition-all resize-none"
                  placeholder="یادداشت"
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
                {saving ? "در حال ذخیره…" : (editTarget ? "ذخیره تغییرات" : "افزودن تامین‌کننده")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
