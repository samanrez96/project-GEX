"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { get, patch, post, del, type ProductDetail, type ProductVendorLink, type Vendor, type PaginatedResponse } from "@/lib/api";
import { formatCurrency, toPersianDigits } from "@/lib/utils";

const STOCK_STATUS_STYLE: Record<string, string> = {
  "موجود":     "bg-green-bg text-green",
  "کم‌موجودی": "bg-amber-bg text-amber",
  "ناموجود":   "bg-red-bg text-red",
};

export default function ProductsDetail({ id }: { id?: string }) {
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [vendors, setVendors] = useState<ProductVendorLink[]>([]);
  const [allVendors, setAllVendors] = useState<Vendor[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [editForm, setEditForm] = useState<Partial<ProductDetail>>({});

  const [showAddVendor, setShowAddVendor] = useState(false);
  const [newVendorId, setNewVendorId] = useState("");
  const [newVendorPrice, setNewVendorPrice] = useState("0");
  const [addVendorError, setAddVendorError] = useState("");
  const [addingVendor, setAddingVendor] = useState(false);

  const [showAdjust, setShowAdjust] = useState(false);
  const [adjustQty, setAdjustQty] = useState("0");
  const [adjustType, setAdjustType] = useState<"IN" | "OUT">("IN");
  const [adjustNote, setAdjustNote] = useState("");
  const [adjusting, setAdjusting] = useState(false);

  const productId = id ? parseInt(id) : null;

  const fetchProduct = async () => {
    if (!productId) return;
    try {
      const p = await get<ProductDetail>(`/inventory/products/${productId}/`);
      setProduct(p);
      setEditForm({
        name: p.name,
        internal_code: p.internal_code,
        product_type: p.product_type,
        purchase_price: p.purchase_price,
        minimum_stock: p.minimum_stock,
        internal_notes: p.internal_notes || "",
      });
    } catch {
      setError("خطا در بارگذاری محصول.");
    }
  };

  const fetchVendors = async () => {
    if (!productId) return;
    try {
      const pv = await get<PaginatedResponse<ProductVendorLink>>(`/inventory/product-vendors/?product=${productId}&page_size=50`);
      setVendors(pv.results || []);
    } catch {}
  };

  const fetchAllVendors = async () => {
    try {
      const v = await get<PaginatedResponse<Vendor>>("/inventory/vendors/?page_size=200&is_active=true");
      setAllVendors(v.results || []);
    } catch {}
  };

  useEffect(() => {
    if (!productId) {
      setLoading(false);
      return;
    }
    Promise.all([fetchProduct(), fetchVendors(), fetchAllVendors()])
      .finally(() => setLoading(false));
  }, [productId]);

  if (loading) {
    return <div dir="rtl" className="py-10 text-center text-muted text-sm">در حال بارگذاری…</div>;
  }

  if (!product || !productId) {
    return (
      <div dir="rtl" className="py-10 text-center">
        <div className="text-muted text-sm mb-4">محصول یافت نشد.</div>
        <Link href="/inventory/products" className="text-purple text-sm hover:underline">← بازگشت به محصولات</Link>
      </div>
    );
  }

  const handleSave = async () => {
    setError("");
    setSaving(true);
    try {
      const updated = await patch<ProductDetail>(`/inventory/products/${productId}/`, editForm);
      setProduct(updated);
      setEditing(false);
      setSuccess("محصول با موفقیت ذخیره شد.");
      setTimeout(() => setSuccess(""), 3000);
    } catch {
      setError("خطا در ذخیره محصول.");
    } finally {
      setSaving(false);
    }
  };

  const handleAddVendor = async () => {
    if (!newVendorId) { setAddVendorError("تامین‌کننده را انتخاب کنید."); return; }
    setAddingVendor(true);
    setAddVendorError("");
    try {
      await post("/inventory/product-vendors/", {
        product: productId,
        vendor: parseInt(newVendorId),
        unit_price: newVendorPrice || "0",
        is_primary: vendors.length === 0,
        is_active: true,
      });
      setShowAddVendor(false);
      setNewVendorId("");
      setNewVendorPrice("0");
      await fetchVendors();
    } catch {
      setAddVendorError("خطا در افزودن تامین‌کننده. ممکن است قبلاً اضافه شده باشد.");
    } finally {
      setAddingVendor(false);
    }
  };

  const handleRemoveVendor = async (pvId: number) => {
    if (!confirm("آیا مطمئن هستید؟")) return;
    try {
      await del(`/inventory/product-vendors/${pvId}/`);
      await fetchVendors();
    } catch {
      setError("خطا در حذف تامین‌کننده.");
    }
  };

  const handleAdjust = async () => {
    const qty = parseFloat(adjustQty || "0");
    if (qty <= 0) { return; }
    setAdjusting(true);
    try {
      await post("/inventory/stock-movements/", {
        product: productId,
        quantity: qty,
        unit: product?.unit || "عدد",
        movement_type: adjustType,
        source_type: "MANUAL_ADJUSTMENT",
        description: adjustNote || "تنظیم دستی موجودی",
      });
      setShowAdjust(false);
      setAdjustQty("0");
      setAdjustNote("");
      await fetchProduct();
      setSuccess("موجودی به‌روزرسانی شد.");
      setTimeout(() => setSuccess(""), 3000);
    } catch {
      setError("خطا در تنظیم موجودی.");
    } finally {
      setAdjusting(false);
    }
  };

  const stockStatus = product.is_out_of_stock ? "ناموجود" : product.is_low_stock ? "کم‌موجودی" : "موجود";

  return (
    <div dir="rtl">
      <div className="flex items-center gap-2 mb-5 text-sm text-muted">
        <Link href="/inventory/products" className="hover:text-purple transition-colors">محصولات</Link>
        <span>/</span>
        <span className="text-text font-medium">{product.name}</span>
      </div>

      {success && (
        <div className="mb-4 bg-green-bg border border-green/30 text-green rounded-xl px-4 py-3 text-sm">{success}</div>
      )}
      {error && (
        <div className="mb-4 bg-red-bg border border-red/30 text-red rounded-xl px-4 py-3 text-sm">{error}</div>
      )}

      <div className="flex items-start justify-between gap-4 mb-6 flex-wrap">
        <div>
          <span className="block text-[11px] font-bold text-purple tracking-widest uppercase mb-1 opacity-85">
            {product.product_type === "medicine" ? "دارو" : "تجهیزات"}
          </span>
          <h1 className="text-[24px] font-bold text-text leading-tight m-0">{product.name}</h1>
          <div className="text-sm text-muted mt-1 font-mono">{product.internal_code}</div>
        </div>
        <div className="flex gap-2 items-center shrink-0">
          <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold ${STOCK_STATUS_STYLE[stockStatus]}`}>
            {stockStatus}
          </span>
          {!editing ? (
            <button
              onClick={() => { setEditing(true); setError(""); }}
              className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl text-sm font-medium bg-purple text-white border border-purple shadow-[0_1px_3px_rgba(0,102,179,.28)] hover:shadow-[0_3px_8px_rgba(0,102,179,.30)] transition-shadow cursor-pointer"
            >
              ویرایش محصول
            </button>
          ) : (
            <div className="flex gap-2">
              <button
                onClick={() => { setEditing(false); setError(""); }}
                className="px-4 py-2 rounded-xl text-sm font-medium border border-border text-muted hover:bg-bg-page transition-colors cursor-pointer"
              >
                انصراف
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-4 py-2 rounded-xl text-sm font-medium bg-purple text-white disabled:opacity-60 hover:shadow-[0_3px_8px_rgba(0,102,179,.30)] transition-shadow cursor-pointer"
              >
                {saving ? "در حال ذخیره…" : "ذخیره"}
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <div className="bg-card border border-border rounded-2xl p-5 shadow-sm">
            <h2 className="text-sm font-bold text-text mb-4">اطلاعات کلی</h2>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="text-xs font-semibold text-muted mb-1">کد داخلی</div>
                {editing ? (
                  <input
                    type="text"
                    value={editForm.internal_code || ""}
                    onChange={(e) => setEditForm({ ...editForm, internal_code: e.target.value })}
                    className="w-full h-[36px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all"
                  />
                ) : (
                  <div className="text-sm font-mono text-text">{product.internal_code || "—"}</div>
                )}
              </div>
              <div>
                <div className="text-xs font-semibold text-muted mb-1">نوع محصول</div>
                {editing ? (
                  <select
                    value={editForm.product_type || product.product_type}
                    onChange={(e) => setEditForm({ ...editForm, product_type: e.target.value as "medicine" | "equipment" })}
                    className="w-full h-[36px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all"
                  >
                    <option value="medicine">دارو</option>
                    <option value="equipment">تجهیزات</option>
                  </select>
                ) : (
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${product.product_type === "medicine" ? "bg-purple-light text-purple" : "bg-amber-bg text-amber"}`}>
                    {product.product_type === "medicine" ? "دارو" : "تجهیزات"}
                  </span>
                )}
              </div>
              <div className="col-span-2">
                <div className="text-xs font-semibold text-muted mb-1">نام محصول</div>
                {editing ? (
                  <input
                    type="text"
                    value={editForm.name || ""}
                    onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                    className="w-full h-[36px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all"
                  />
                ) : (
                  <div className="text-sm font-semibold text-text">{product.name}</div>
                )}
              </div>
              <div>
                <div className="text-xs font-semibold text-muted mb-1">قیمت خرید (تومان)</div>
                {editing ? (
                  <input
                    type="number"
                    min="0"
                    value={editForm.purchase_price || ""}
                    onChange={(e) => setEditForm({ ...editForm, purchase_price: e.target.value })}
                    className="w-full h-[36px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all"
                  />
                ) : (
                  <div className="text-sm font-bold text-text">{formatCurrency(parseFloat(product.purchase_price || "0"))}</div>
                )}
              </div>
              <div>
                <div className="text-xs font-semibold text-muted mb-1">حداقل موجودی</div>
                {editing ? (
                  <input
                    type="number"
                    min="0"
                    value={editForm.minimum_stock || ""}
                    onChange={(e) => setEditForm({ ...editForm, minimum_stock: e.target.value })}
                    className="w-full h-[36px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all"
                  />
                ) : (
                  <div className="text-sm text-text">{toPersianDigits(parseFloat(product.minimum_stock || "0").toString())}</div>
                )}
              </div>
              {(editing || product.internal_notes) && (
                <div className="col-span-2">
                  <div className="text-xs font-semibold text-muted mb-1">توضیحات داخلی</div>
                  {editing ? (
                    <textarea
                      value={editForm.internal_notes || ""}
                      onChange={(e) => setEditForm({ ...editForm, internal_notes: e.target.value })}
                      rows={2}
                      className="w-full px-3 py-2 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all resize-none"
                    />
                  ) : (
                    <div className="text-sm text-muted">{product.internal_notes}</div>
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="bg-card border border-border rounded-2xl p-5 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-bold text-text">تامین‌کنندگان</h2>
              <button
                onClick={() => { setShowAddVendor(true); setAddVendorError(""); }}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-purple/10 text-purple hover:bg-purple/20 transition-colors cursor-pointer"
              >
                + افزودن تامین‌کننده
              </button>
            </div>
            {vendors.length === 0 ? (
              <div className="text-sm text-muted text-center py-4">هیچ تامین‌کننده‌ای تعریف نشده</div>
            ) : (
              <div className="space-y-2">
                {vendors.map((pv) => (
                  <div key={pv.id} className="flex items-center justify-between px-3 py-2.5 bg-bg-page rounded-xl border border-border/60">
                    <div className="flex items-center gap-3">
                      {pv.is_primary && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-light text-purple">اصلی</span>
                      )}
                      <span className="text-sm font-semibold text-text">{pv.vendor_name}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-sm text-muted" dir="ltr">{formatCurrency(parseFloat(pv.unit_price || "0"))}</span>
                      <button
                        onClick={() => handleRemoveVendor(pv.id)}
                        className="text-xs text-red hover:text-red/80 cursor-pointer"
                      >
                        حذف
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {showAddVendor && (
              <div className="mt-4 p-4 bg-bg-page rounded-xl border border-border space-y-3">
                <div className="text-xs font-bold text-text">افزودن تامین‌کننده</div>
                {addVendorError && <div className="text-xs text-red">{addVendorError}</div>}
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-muted">تامین‌کننده</label>
                    <select
                      value={newVendorId}
                      onChange={(e) => setNewVendorId(e.target.value)}
                      className="h-[34px] px-2 border border-border rounded-lg text-sm text-text bg-card outline-none focus:border-purple transition-all"
                    >
                      <option value="">انتخاب کنید</option>
                      {allVendors.filter(v => !vendors.some(pv => pv.vendor === v.id)).map((v) => (
                        <option key={v.id} value={v.id}>{v.name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-muted">قیمت واحد</label>
                    <input
                      type="number"
                      min="0"
                      value={newVendorPrice}
                      onChange={(e) => setNewVendorPrice(e.target.value)}
                      className="h-[34px] px-2 border border-border rounded-lg text-sm text-text bg-card outline-none focus:border-purple transition-all"
                    />
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => setShowAddVendor(false)} className="px-3 py-1.5 rounded-lg text-xs border border-border text-muted hover:bg-bg-page cursor-pointer">انصراف</button>
                  <button onClick={handleAddVendor} disabled={addingVendor} className="px-3 py-1.5 rounded-lg text-xs bg-purple text-white disabled:opacity-60 cursor-pointer">
                    {addingVendor ? "در حال ذخیره…" : "افزودن"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <div className="bg-card border border-border rounded-2xl p-5 shadow-sm">
            <h2 className="text-sm font-bold text-text mb-4">وضعیت موجودی</h2>
            <div className="text-center py-2">
              <div className="text-[42px] font-extrabold text-text-strong leading-none">
                {toPersianDigits(parseFloat(product.current_stock || "0").toString())}
              </div>
              <div className="text-xs text-muted mt-1">تعداد فعلی</div>
            </div>
            <div className="mt-4 pt-4 border-t border-border space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted">حداقل موجودی</span>
                <span className="font-semibold text-text">{toPersianDigits(parseFloat(product.minimum_stock || "0").toString())}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">وضعیت</span>
                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${STOCK_STATUS_STYLE[stockStatus]}`}>{stockStatus}</span>
              </div>
            </div>
            <button
              onClick={() => { setShowAdjust(!showAdjust); setAdjustQty("0"); setAdjustNote(""); }}
              className="mt-4 w-full py-2 rounded-xl text-sm font-medium border border-border text-muted hover:bg-bg-page transition-colors cursor-pointer"
            >
              تنظیم موجودی
            </button>
            {showAdjust && (
              <div className="mt-3 space-y-3">
                <div className="flex gap-2">
                  <button
                    onClick={() => setAdjustType("IN")}
                    className={`flex-1 py-1.5 rounded-lg text-xs font-medium cursor-pointer transition-colors ${adjustType === "IN" ? "bg-green-bg text-green border border-green/30" : "border border-border text-muted hover:bg-bg-page"}`}
                  >
                    ورود موجودی
                  </button>
                  <button
                    onClick={() => setAdjustType("OUT")}
                    className={`flex-1 py-1.5 rounded-lg text-xs font-medium cursor-pointer transition-colors ${adjustType === "OUT" ? "bg-red-bg text-red border border-red/30" : "border border-border text-muted hover:bg-bg-page"}`}
                  >
                    خروج موجودی
                  </button>
                </div>
                <input
                  type="number"
                  min="1"
                  value={adjustQty}
                  onChange={(e) => setAdjustQty(e.target.value)}
                  className="w-full h-[34px] px-3 border border-border rounded-lg text-sm text-text bg-bg-page outline-none focus:border-purple transition-all"
                  placeholder="تعداد"
                />
                <input
                  type="text"
                  value={adjustNote}
                  onChange={(e) => setAdjustNote(e.target.value)}
                  className="w-full h-[34px] px-3 border border-border rounded-lg text-sm text-text bg-bg-page outline-none focus:border-purple transition-all"
                  placeholder="توضیح (اختیاری)"
                />
                <button
                  onClick={handleAdjust}
                  disabled={adjusting}
                  className="w-full py-2 rounded-xl text-sm font-medium bg-purple text-white disabled:opacity-60 cursor-pointer"
                >
                  {adjusting ? "در حال ثبت…" : "ثبت تغییر"}
                </button>
              </div>
            )}
          </div>

          <div className="bg-card border border-border rounded-2xl p-5 shadow-sm">
            <h2 className="text-sm font-bold text-text mb-3">اطلاعات بیشتر</h2>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted">قیمت خرید</span>
                <span className="font-semibold text-text" dir="ltr">{formatCurrency(parseFloat(product.purchase_price || "0"))}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">تاریخ ثبت</span>
                <span className="text-text">{product.created_at?.slice(0, 10) || "—"}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}