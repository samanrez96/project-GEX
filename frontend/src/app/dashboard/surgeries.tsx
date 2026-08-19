"use client";

import { useEffect, useState } from "react";
import { get, post, type PaginatedResponse, type SurgeryHistory, type SurgeryType, type Doctor, type Patient } from "@/lib/api";
import { formatCurrency, formatDate, toPersianDigits } from "@/lib/utils";

const STATUS_MAP: Record<string, { cls: string; label: string }> = {
  planned:     { cls: "bg-purple-light text-purple", label: "برنامه‌ریزی شده" },
  in_progress: { cls: "bg-amber-bg text-amber",     label: "در حال انجام" },
  completed:   { cls: "bg-green-bg text-green",     label: "انجام شده" },
  cancelled:   { cls: "bg-red-bg text-red",         label: "لغو شده" },
};

const PAYMENT_STATUS_MAP: Record<string, { cls: string; label: string }> = {
  PENDING: { cls: "bg-amber-bg text-amber", label: "در انتظار پرداخت" },
  PARTIAL: { cls: "bg-purple-light text-purple", label: "پرداخت ناقص" },
  PAID:    { cls: "bg-green-bg text-green",  label: "پرداخت شده" },
};

const PAGE_SIZE = 20;

interface SurgeryForm {
  patient_id: string;
  patient_name_new: string;
  case_code_new: string;
  phone_new: string;
  surgery_type: string;
  doctor_or_therapist: string;
  surgery_date: string;
  amount: string;
  payment_status: "PENDING" | "PARTIAL" | "PAID";
  center_commission_percent: string;
  description: string;
  status: "PLANNED" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED";
  use_new_patient: boolean;
}

const EMPTY_FORM: SurgeryForm = {
  patient_id: "",
  patient_name_new: "",
  case_code_new: "",
  phone_new: "",
  surgery_type: "",
  doctor_or_therapist: "",
  surgery_date: new Date().toISOString().slice(0, 10) + "T00:00",
  amount: "0",
  payment_status: "PENDING",
  center_commission_percent: "",
  description: "",
  status: "PLANNED",
  use_new_patient: false,
};

export default function SurgeriesPage() {
  const [items, setItems] = useState<SurgeryHistory[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);

  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<SurgeryForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [surgeryTypes, setSurgeryTypes] = useState<SurgeryType[]>([]);
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [patientSearch, setPatientSearch] = useState("");

  const fetchSurgeries = () => {
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE), ordering: "-surgery_date" });
    if (search) params.set("search", search);
    if (statusFilter) params.set("status", statusFilter);
    get<PaginatedResponse<SurgeryHistory>>(`/surgeries/history/?${params}`)
      .then((d) => { setItems(d.results || []); setCount(d.count); })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchSurgeries(); }, [page, search, statusFilter]);

  const openModal = () => {
    setForm(EMPTY_FORM);
    setError("");
    setPatientSearch("");
    setShowModal(true);
    // Load dropdowns
    get<PaginatedResponse<SurgeryType>>("/surgeries/types/?page_size=100&is_active=true")
      .then((d) => setSurgeryTypes(d.results || []))
      .catch(() => {});
    get<PaginatedResponse<Doctor>>("/contacts/doctors/?page_size=200&is_active=true")
      .then((d) => setDoctors(d.results || []))
      .catch(() => {});
    get<PaginatedResponse<Patient>>("/surgeries/patients/?page_size=100")
      .then((d) => setPatients(d.results || []))
      .catch(() => {});
  };

  const closeModal = () => { setShowModal(false); setError(""); };

  const searchPatients = (q: string) => {
    setPatientSearch(q);
    if (!q.trim()) return;
    get<PaginatedResponse<Patient>>(`/surgeries/patients/?search=${encodeURIComponent(q)}&page_size=20`)
      .then((d) => setPatients(d.results || []))
      .catch(() => {});
  };

  const handleSubmit = async () => {
    if (!form.surgery_type) { setError("نوع عمل الزامی است."); return; }
    if (!form.amount || parseFloat(form.amount) < 0) { setError("مبلغ عمل الزامی است."); return; }
    setSaving(true);
    setError("");
    try {
      let patientId = form.patient_id;

      // Create new patient if needed
      if (form.use_new_patient) {
        if (!form.patient_name_new.trim()) { setError("نام بیمار الزامی است."); setSaving(false); return; }
        if (!form.case_code_new.trim()) { setError("کد پرونده بیمار الزامی است."); setSaving(false); return; }
        const newPat = await post<Patient>("/surgeries/patients/", {
          full_name: form.patient_name_new.trim(),
          case_code: form.case_code_new.trim(),
          phone_number: form.phone_new.trim(),
        });
        patientId = String(newPat.id);
      } else if (!patientId) {
        setError("بیمار را انتخاب کنید یا بیمار جدید اضافه کنید."); setSaving(false); return;
      }

      const payload: Record<string, unknown> = {
        patient: parseInt(patientId),
        surgery_type: parseInt(form.surgery_type),
        surgery_date: form.surgery_date.includes("T") ? form.surgery_date : form.surgery_date + "T00:00:00",
        amount: parseFloat(form.amount),
        payment_status: form.payment_status,
        status: form.status,
        description: form.description.trim(),
      };
      if (form.doctor_or_therapist) payload.doctor_or_therapist = parseInt(form.doctor_or_therapist);
      if (form.center_commission_percent) payload.center_commission_percent = parseFloat(form.center_commission_percent);

      await post("/surgeries/history/", payload);
      setSuccess("عمل جراحی با موفقیت ثبت شد.");
      closeModal();
      setPage(1);
      fetchSurgeries();
      setTimeout(() => setSuccess(""), 4000);
    } catch {
      setError("خطا در ثبت عمل جراحی. لطفاً اطلاعات را بررسی کنید.");
    } finally {
      setSaving(false);
    }
  };

  const totalPages = Math.ceil(count / PAGE_SIZE);

  return (
    <div dir="rtl">
      <div className="flex items-start justify-between gap-4 mb-7 flex-wrap">
        <div className="flex-1 min-w-0">
          <span className="block text-[11px] font-bold text-purple tracking-widest uppercase mb-1 opacity-85">جراحی‌ها</span>
          <h1 className="text-[26px] font-bold text-text leading-tight m-0">عمل‌های جراحی</h1>
        </div>
        <div className="flex gap-2 items-center shrink-0 pt-1.5">
          <button
            onClick={openModal}
            className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl text-sm font-medium bg-purple text-white border border-purple shadow-[0_1px_3px_rgba(0,102,179,.28)] hover:shadow-[0_3px_8px_rgba(0,102,179,.30)] transition-shadow cursor-pointer"
          >
            + ثبت عمل جراحی
          </button>
        </div>
      </div>

      {success && (
        <div className="mb-4 bg-green-bg border border-green/30 text-green rounded-xl px-4 py-3 text-sm">{success}</div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 mb-5">
        <div className="bg-card border border-border rounded-2xl p-5 shadow-sm">
          <div className="text-xs font-bold text-muted tracking-[.6px] uppercase mb-2">کل عمل‌ها</div>
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
            placeholder="نام بیمار..."
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
            <option value="PLANNED">برنامه‌ریزی شده</option>
            <option value="IN_PROGRESS">در حال انجام</option>
            <option value="COMPLETED">انجام شده</option>
            <option value="CANCELLED">لغو شده</option>
          </select>
        </div>
      </div>

      <div className="bg-card border border-border rounded-2xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                {["بیمار", "نوع عمل", "پزشک / درمانگر", "تاریخ", "مبلغ", "وضعیت"].map((h) => (
                  <th key={h} className="bg-bg-page px-4 py-2.5 text-[11px] font-bold text-muted text-right tracking-[.4px] uppercase border-b-2 border-border whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} className="text-center py-7 text-muted text-sm">در حال بارگذاری…</td></tr>
              ) : items.length === 0 ? (
                <tr><td colSpan={6} className="text-center py-7 text-muted text-sm">عمل جراحی‌ای یافت نشد</td></tr>
              ) : (
                items.map((s) => {
                  const stKey = (s.status || "").toLowerCase();
                  const st = STATUS_MAP[stKey] || { cls: "bg-gray-100 text-gray-600", label: s.status_display || s.status };
                  return (
                    <tr key={s.id} className="hover:bg-bg-page">
                      <td className="px-4 py-3 text-sm font-semibold text-text border-b border-border/55">{s.patient_name || "—"}</td>
                      <td className="px-4 py-3 text-sm text-text border-b border-border/55">{s.surgery_type_name || "—"}</td>
                      <td className="px-4 py-3 text-sm text-muted border-b border-border/55">{s.doctor_name || "—"}</td>
                      <td className="px-4 py-3 text-sm text-text border-b border-border/55">{formatDate(s.surgery_date)}</td>
                      <td className="px-4 py-3 text-sm font-bold text-text border-b border-border/55 text-left" dir="ltr">{formatCurrency(parseFloat(s.amount || "0"))}</td>
                      <td className="px-4 py-3 border-b border-border/55">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${st.cls}`}>{st.label}</span>
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

      {/* Add Surgery Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-card border border-border rounded-2xl shadow-xl w-full max-w-xl max-h-[90vh] overflow-y-auto" dir="rtl">
            <div className="flex items-center justify-between px-6 py-4 border-b border-border">
              <h2 className="text-lg font-bold text-text">ثبت عمل جراحی جدید</h2>
              <button onClick={closeModal} className="text-muted hover:text-text transition-colors text-xl cursor-pointer">×</button>
            </div>
            <div className="px-6 py-5 space-y-4">
              {error && (
                <div className="bg-red-bg border border-red/30 text-red rounded-xl px-4 py-3 text-sm">{error}</div>
              )}

              {/* Patient Section */}
              <div className="text-xs font-bold text-purple uppercase tracking-widest">اطلاعات بیمار</div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setForm({ ...form, use_new_patient: false })}
                  className={`flex-1 py-2 rounded-xl text-sm font-medium cursor-pointer transition-colors ${!form.use_new_patient ? "bg-purple text-white" : "border border-border text-muted hover:bg-bg-page"}`}
                >
                  بیمار موجود
                </button>
                <button
                  type="button"
                  onClick={() => setForm({ ...form, use_new_patient: true, patient_id: "" })}
                  className={`flex-1 py-2 rounded-xl text-sm font-medium cursor-pointer transition-colors ${form.use_new_patient ? "bg-purple text-white" : "border border-border text-muted hover:bg-bg-page"}`}
                >
                  بیمار جدید
                </button>
              </div>

              {!form.use_new_patient ? (
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-semibold text-muted">جستجو و انتخاب بیمار</label>
                  <input
                    type="text"
                    value={patientSearch}
                    onChange={(e) => searchPatients(e.target.value)}
                    className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all mb-1"
                    placeholder="نام بیمار یا کد پرونده..."
                  />
                  <select
                    value={form.patient_id}
                    onChange={(e) => setForm({ ...form, patient_id: e.target.value })}
                    className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all"
                  >
                    <option value="">انتخاب بیمار</option>
                    {patients.map((p) => (
                      <option key={p.id} value={p.id}>{p.full_name} — {p.case_code}</option>
                    ))}
                  </select>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="flex flex-col gap-1">
                      <label className="text-xs font-semibold text-muted">نام بیمار <span className="text-red">*</span></label>
                      <input type="text" value={form.patient_name_new} onChange={(e) => setForm({ ...form, patient_name_new: e.target.value })}
                        className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all" placeholder="نام کامل" />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-xs font-semibold text-muted">کد پرونده <span className="text-red">*</span></label>
                      <input type="text" value={form.case_code_new} onChange={(e) => setForm({ ...form, case_code_new: e.target.value })}
                        className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all" placeholder="کد یکتا" dir="ltr" />
                    </div>
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-muted">شماره تماس بیمار</label>
                    <input type="text" value={form.phone_new} onChange={(e) => setForm({ ...form, phone_new: e.target.value })}
                      className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all" placeholder="۰۹۱۲..." dir="ltr" />
                  </div>
                </div>
              )}

              {/* Surgery Details */}
              <div className="border-t border-border pt-4">
                <div className="text-xs font-bold text-purple uppercase tracking-widest mb-3">جزئیات عمل</div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-muted">نوع عمل <span className="text-red">*</span></label>
                    <select value={form.surgery_type} onChange={(e) => setForm({ ...form, surgery_type: e.target.value })}
                      className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all">
                      <option value="">انتخاب نوع عمل</option>
                      {surgeryTypes.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                    </select>
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-muted">پزشک / درمانگر</label>
                    <select value={form.doctor_or_therapist} onChange={(e) => setForm({ ...form, doctor_or_therapist: e.target.value })}
                      className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all">
                      <option value="">انتخاب پزشک / درمانگر</option>
                      {doctors.map((d) => (
                        <option key={d.id} value={d.id}>{d.full_name}{d.specialty_name ? ` — ${d.specialty_name}` : ""}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4 mt-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-muted">تاریخ پرداخت <span className="text-red">*</span></label>
                    <input type="datetime-local" value={form.surgery_date} onChange={(e) => setForm({ ...form, surgery_date: e.target.value })}
                      className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all" dir="ltr" />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-muted">وضعیت عمل</label>
                    <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as SurgeryForm["status"] })}
                      className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all">
                      <option value="PLANNED">برنامه‌ریزی شده</option>
                      <option value="IN_PROGRESS">در حال انجام</option>
                      <option value="COMPLETED">انجام شده</option>
                      <option value="CANCELLED">لغو شده</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Financial Info */}
              <div className="border-t border-border pt-4">
                <div className="text-xs font-bold text-purple uppercase tracking-widest mb-3">اطلاعات مالی</div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-muted">مبلغ عمل (تومان) <span className="text-red">*</span></label>
                    <input type="number" min="0" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })}
                      className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all" placeholder="۰" />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-muted">وضعیت پرداخت</label>
                    <select value={form.payment_status} onChange={(e) => setForm({ ...form, payment_status: e.target.value as SurgeryForm["payment_status"] })}
                      className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all">
                      <option value="PENDING">در انتظار پرداخت</option>
                      <option value="PARTIAL">پرداخت ناقص</option>
                      <option value="PAID">پرداخت شده</option>
                    </select>
                  </div>
                </div>
                <div className="mt-3 flex flex-col gap-1">
                  <label className="text-xs font-semibold text-muted">درصد کمیسیون مرکز (اختیاری)</label>
                  <input type="number" min="0" max="100" step="0.01" value={form.center_commission_percent} onChange={(e) => setForm({ ...form, center_commission_percent: e.target.value })}
                    className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all" placeholder="مثال: ۱۰" />
                </div>
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-muted">توضیحات</label>
                <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
                  rows={2}
                  className="px-3 py-2 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all resize-none"
                  placeholder="یادداشت یا توضیح (اختیاری)" />
              </div>
            </div>
            <div className="flex gap-2 px-6 py-4 border-t border-border justify-end">
              <button onClick={closeModal} className="px-5 py-2 rounded-xl text-sm font-medium border border-border text-muted hover:bg-bg-page transition-colors cursor-pointer">انصراف</button>
              <button onClick={handleSubmit} disabled={saving} className="px-5 py-2 rounded-xl text-sm font-medium bg-purple text-white disabled:opacity-60 hover:shadow-[0_3px_8px_rgba(0,102,179,.30)] transition-shadow cursor-pointer">
                {saving ? "در حال ثبت…" : "ثبت عمل جراحی"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
