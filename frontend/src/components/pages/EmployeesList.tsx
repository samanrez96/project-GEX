"use client";

import { useEffect, useState } from "react";
import { get, post, patch, type PaginatedResponse, type Employee, type JobPosition, type MonthlyWage } from "@/lib/api";
import { toPersianDigits } from "@/lib/utils";

const PAGE_SIZE = 20;

interface EmployeeForm {
  full_name: string;
  national_id: string;
  gender: "male" | "female" | "other";
  job_position: string;
  start_date: string;
  personal_phone: string;
  email: string;
  address: string;
  description: string;
  wage_type: "none" | "fixed" | "commission";
  monthly_amount: string;
}

const EMPTY_FORM: EmployeeForm = {
  full_name: "",
  national_id: "",
  gender: "male",
  job_position: "",
  start_date: new Date().toISOString().slice(0, 10),
  personal_phone: "",
  email: "",
  address: "",
  description: "",
  wage_type: "none",
  monthly_amount: "",
};

export default function EmployeesList() {
  const [items, setItems] = useState<Employee[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [positions, setPositions] = useState<JobPosition[]>([]);

  const [showModal, setShowModal] = useState(false);
  const [editTarget, setEditTarget] = useState<Employee | null>(null);
  const [form, setForm] = useState<EmployeeForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const fetchEmployees = () => {
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (search) params.set("search", search);
    get<PaginatedResponse<Employee>>(`/employees/?${params}`)
      .then((d) => { setItems(d.results || []); setCount(d.count); })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchEmployees(); }, [page, search]);

  useEffect(() => {
    get<PaginatedResponse<JobPosition>>("/employees/positions/?page_size=100&is_active=true")
      .then((d) => setPositions(d.results || []))
      .catch(() => {});
  }, []);

  const totalPages = Math.ceil(count / PAGE_SIZE);

  const openAdd = () => {
    setEditTarget(null);
    setForm(EMPTY_FORM);
    setError("");
    setShowModal(true);
  };

  const openEdit = (emp: Employee) => {
    setEditTarget(emp);
    setForm({
      full_name: emp.full_name || "",
      national_id: emp.national_id || "",
      gender: (emp.gender as "male" | "female" | "other") || "male",
      job_position: emp.job_position ? String(emp.job_position) : "",
      start_date: emp.start_date || new Date().toISOString().slice(0, 10),
      personal_phone: emp.personal_phone || "",
      email: emp.email || "",
      address: "",
      description: "",
      wage_type: "none",
      monthly_amount: "",
    });
    setError("");
    setShowModal(true);
  };

  const closeModal = () => { setShowModal(false); setError(""); setEditTarget(null); };

  const handleSubmit = async () => {
    if (!form.full_name.trim()) { setError("نام کامل الزامی است."); return; }
    if (!form.national_id.trim()) { setError("کد ملی الزامی است."); return; }
    setSaving(true);
    setError("");
    try {
      const payload: Record<string, unknown> = {
        full_name: form.full_name.trim(),
        national_id: form.national_id.trim(),
        gender: form.gender,
        start_date: form.start_date,
        personal_phone: form.personal_phone.trim(),
        email: form.email.trim() || null,
        address: form.address.trim(),
        description: form.description.trim(),
        is_active: true,
      };
      if (form.job_position) payload.job_position = parseInt(form.job_position);

      let empId: number;
      if (editTarget) {
        const updated = await patch<Employee>(`/employees/${editTarget.id}/`, payload);
        empId = updated.id;
      } else {
        const created = await post<Employee>("/employees/", payload);
        empId = created.id;
      }

      // Handle payroll setup (only for new employees)
      if (!editTarget && form.wage_type !== "none") {
        try {
          const config = await get<{ id: number; has_monthly_wage: boolean; has_commission: boolean }>(
            `/payroll/configs/by_employee/?employee=${empId}`
          );
          await patch(`/payroll/configs/${config.id}/`, {
            has_monthly_wage: form.wage_type === "fixed",
            has_commission: form.wage_type === "commission",
          });
          if (form.wage_type === "fixed" && form.monthly_amount) {
            await post("/payroll/wages/", {
              employee: empId,
              amount: parseFloat(form.monthly_amount),
              start_date: form.start_date,
              is_active: true,
            });
          }
        } catch {
          setSuccess(editTarget ? "کارمند ویرایش شد." : "کارمند افزوده شد (تنظیمات حقوقی ممکن است کامل نشده باشد).");
          closeModal();
          setPage(1);
          fetchEmployees();
          return;
        }
      }

      setSuccess(editTarget ? "کارمند ویرایش شد." : "کارمند با موفقیت افزوده شد.");
      closeModal();
      setPage(1);
      fetchEmployees();
      setTimeout(() => setSuccess(""), 3000);
    } catch (err) {
      setError("خطا در ذخیره اطلاعات کارمند.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div dir="rtl">
      <div className="flex items-start justify-between gap-4 mb-7 flex-wrap">
        <div className="flex-1 min-w-0">
          <span className="block text-[11px] font-bold text-purple tracking-widest uppercase mb-1 opacity-85">کارمندان</span>
          <h1 className="text-[26px] font-bold text-text leading-tight m-0">کارمندان</h1>
        </div>
        <div className="flex gap-2 items-center shrink-0 pt-1.5">
          <button
            onClick={openAdd}
            className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl text-sm font-medium bg-purple text-white border border-purple shadow-[0_1px_3px_rgba(0,102,179,.28)] hover:shadow-[0_3px_8px_rgba(0,102,179,.30)] transition-shadow cursor-pointer"
          >
            + افزودن کارمند
          </button>
        </div>
      </div>

      {success && (
        <div className="mb-4 bg-green-bg border border-green/30 text-green rounded-xl px-4 py-3 text-sm">{success}</div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 mb-5">
        <div className="bg-card border border-border rounded-2xl p-5 shadow-sm">
          <div className="text-xs font-bold text-muted tracking-[.6px] uppercase mb-2">کل کارمندان</div>
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
            placeholder="نام کارمند..."
          />
        </div>
      </div>

      <div className="bg-card border border-border rounded-2xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                {["نام", "سمت", "تلفن", "وضعیت", "عملیات"].map((h) => (
                  <th key={h} className="bg-bg-page px-4 py-2.5 text-[11px] font-bold text-muted text-right tracking-[.4px] uppercase border-b-2 border-border whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5} className="text-center py-7 text-muted text-sm">در حال بارگذاری…</td></tr>
              ) : items.length === 0 ? (
                <tr><td colSpan={5} className="text-center py-7 text-muted text-sm">کارمندی یافت نشد</td></tr>
              ) : (
                items.map((e) => (
                  <tr key={e.id} className="hover:bg-bg-page">
                    <td className="px-4 py-3 text-sm font-semibold text-text border-b border-border/55">{e.full_name || "—"}</td>
                    <td className="px-4 py-3 border-b border-border/55">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-light text-purple">
                        {e.job_position_name || "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-text border-b border-border/55 text-left" dir="ltr">{e.personal_phone || "—"}</td>
                    <td className="px-4 py-3 border-b border-border/55">
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${e.is_active ? "bg-green-bg text-green" : "bg-red-bg text-red"}`}>
                        {e.is_active ? "فعال" : "غیرفعال"}
                      </span>
                    </td>
                    <td className="px-4 py-3 border-b border-border/55">
                      <button onClick={() => openEdit(e)} className="text-xs text-purple hover:text-purple/80 font-medium cursor-pointer">ویرایش</button>
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

      {/* Add/Edit Employee Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-card border border-border rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto" dir="rtl">
            <div className="flex items-center justify-between px-6 py-4 border-b border-border">
              <h2 className="text-lg font-bold text-text">{editTarget ? "ویرایش کارمند" : "افزودن کارمند جدید"}</h2>
              <button onClick={closeModal} className="text-muted hover:text-text transition-colors text-xl cursor-pointer">×</button>
            </div>
            <div className="px-6 py-5 space-y-4">
              {error && (
                <div className="bg-red-bg border border-red/30 text-red rounded-xl px-4 py-3 text-sm">{error}</div>
              )}

              <div className="text-xs font-bold text-purple uppercase tracking-widest mb-1">اطلاعات شخصی</div>

              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-muted">نام و نام خانوادگی <span className="text-red">*</span></label>
                <input
                  type="text"
                  value={form.full_name}
                  onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                  className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all"
                  placeholder="نام کامل"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-semibold text-muted">کد ملی <span className="text-red">*</span></label>
                  <input
                    type="text"
                    value={form.national_id}
                    onChange={(e) => setForm({ ...form, national_id: e.target.value })}
                    className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all"
                    placeholder="۱۰ رقم"
                    dir="ltr"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-semibold text-muted">جنسیت</label>
                  <select
                    value={form.gender}
                    onChange={(e) => setForm({ ...form, gender: e.target.value as "male" | "female" | "other" })}
                    className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all"
                  >
                    <option value="male">مرد</option>
                    <option value="female">زن</option>
                    <option value="other">سایر</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-semibold text-muted">سمت شغلی</label>
                  <select
                    value={form.job_position}
                    onChange={(e) => setForm({ ...form, job_position: e.target.value })}
                    className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all"
                  >
                    <option value="">انتخاب سمت</option>
                    {positions.map((p) => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-semibold text-muted">تاریخ شروع به کار</label>
                  <input
                    type="date"
                    value={form.start_date}
                    onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                    className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all"
                    dir="ltr"
                  />
                </div>
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-muted">تلفن همراه</label>
                <input
                  type="text"
                  value={form.personal_phone}
                  onChange={(e) => setForm({ ...form, personal_phone: e.target.value })}
                  className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all"
                  placeholder="۰۹۱۲..."
                  dir="ltr"
                />
              </div>

              {!editTarget && (
                <>
                  <div className="border-t border-border pt-4">
                    <div className="text-xs font-bold text-purple uppercase tracking-widest mb-3">تنظیمات حقوق و دستمزد</div>
                    <div className="flex flex-col gap-1 mb-3">
                      <label className="text-xs font-semibold text-muted">نوع دستمزد</label>
                      <select
                        value={form.wage_type}
                        onChange={(e) => setForm({ ...form, wage_type: e.target.value as "none" | "fixed" | "commission" })}
                        className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all"
                      >
                        <option value="none">بعداً تنظیم می‌شود</option>
                        <option value="fixed">حقوق ثابت ماهیانه</option>
                        <option value="commission">کمیسیونی</option>
                      </select>
                    </div>
                    {form.wage_type === "fixed" && (
                      <div className="flex flex-col gap-1">
                        <label className="text-xs font-semibold text-muted">مبلغ حقوق ماهیانه (تومان) <span className="text-red">*</span></label>
                        <input
                          type="number"
                          min="0"
                          value={form.monthly_amount}
                          onChange={(e) => setForm({ ...form, monthly_amount: e.target.value })}
                          className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all"
                          placeholder="مثال: ۱۵۰۰۰۰۰۰"
                        />
                      </div>
                    )}
                    {form.wage_type === "commission" && (
                      <div className="bg-amber-bg/30 border border-amber/30 rounded-xl px-3 py-2.5 text-xs text-amber">
                        قوانین کمیسیون را از منوی حقوق و دستمزد تنظیم کنید.
                      </div>
                    )}
                  </div>
                </>
              )}
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
                {saving ? "در حال ذخیره…" : (editTarget ? "ذخیره تغییرات" : "افزودن کارمند")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}