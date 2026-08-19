"use client";

import { useEffect, useState } from "react";
import { get, post, patch, type PaginatedResponse, type PayrollPeriod, type MonthlyWage, type CommissionRule, type Employee, type JobPosition, type SurgeryType, type PayrollReport } from "@/lib/api";
import { formatCurrency, toPersianDigits } from "@/lib/utils";

type Tab = "report" | "wages" | "commission";

const STATUS_LABEL: Record<string, string> = {
  OPEN: "باز",
  CLOSED: "بسته",
  PROCESSED: "پردازش شده",
};

export default function PayrollPage() {
  const [tab, setTab] = useState<Tab>("report");

  // ── Report tab ─────────────────────────────────────────────────────────────
  const [periods, setPeriods] = useState<PayrollPeriod[]>([]);
  const [selectedPeriod, setSelectedPeriod] = useState<PayrollPeriod | null>(null);
  const [report, setReport] = useState<PayrollReport | null>(null);
  const [reportLoading, setReportLoading] = useState(false);

  useEffect(() => {
    get<PaginatedResponse<PayrollPeriod>>("/payroll/periods/?page_size=50")
      .then((d) => setPeriods(d.results || []))
      .catch(() => {});
  }, []);

  const loadReport = (period: PayrollPeriod | null) => {
    setSelectedPeriod(period);
    if (!period) { setReport(null); return; }
    setReportLoading(true);
    const params = new URLSearchParams({ year: String(period.year), month: String(period.month) });
    get<PayrollReport>(`/payroll/report/?${params}`)
      .then((d) => setReport(d))
      .catch(() => setReport(null))
      .finally(() => setReportLoading(false));
  };

  // ── Monthly Wages tab ──────────────────────────────────────────────────────
  const [wages, setWages] = useState<MonthlyWage[]>([]);
  const [wagesLoading, setWagesLoading] = useState(false);
  const [showWageModal, setShowWageModal] = useState(false);
  const [wageForm, setWageForm] = useState({ employee: "", amount: "", start_date: new Date().toISOString().slice(0, 10), notes: "" });
  const [wageSaving, setWageSaving] = useState(false);
  const [wageError, setWageError] = useState("");
  const [wageSuccess, setWageSuccess] = useState("");
  const [allEmployees, setAllEmployees] = useState<Employee[]>([]);

  const fetchWages = () => {
    setWagesLoading(true);
    get<PaginatedResponse<MonthlyWage>>("/payroll/wages/?page_size=100&is_active=true")
      .then((d) => setWages(d.results || []))
      .catch(() => {})
      .finally(() => setWagesLoading(false));
  };

  useEffect(() => {
    if (tab === "wages") {
      fetchWages();
      get<PaginatedResponse<Employee>>("/employees/?page_size=200&is_active=true")
        .then((d) => setAllEmployees(d.results || []))
        .catch(() => {});
    }
  }, [tab]);

  const handleAddWage = async () => {
    if (!wageForm.employee) { setWageError("کارمند را انتخاب کنید."); return; }
    if (!wageForm.amount || parseFloat(wageForm.amount) <= 0) { setWageError("مبلغ حقوق الزامی است."); return; }
    setWageSaving(true);
    setWageError("");
    try {
      await post("/payroll/wages/", {
        employee: parseInt(wageForm.employee),
        amount: parseFloat(wageForm.amount),
        start_date: wageForm.start_date,
        is_active: true,
        notes: wageForm.notes.trim(),
      });
      setShowWageModal(false);
      setWageForm({ employee: "", amount: "", start_date: new Date().toISOString().slice(0, 10), notes: "" });
      setWageSuccess("حقوق ثبت شد.");
      fetchWages();
      setTimeout(() => setWageSuccess(""), 3000);
    } catch {
      setWageError("خطا در ثبت حقوق. ممکن است این کارمند حقوق فعال دیگری داشته باشد.");
    } finally {
      setWageSaving(false);
    }
  };

  const deactivateWage = async (id: number) => {
    if (!confirm("آیا مطمئن هستید؟ این حقوق غیرفعال می‌شود.")) return;
    try {
      await patch(`/payroll/wages/${id}/`, { is_active: false, end_date: new Date().toISOString().slice(0, 10) });
      fetchWages();
    } catch {}
  };

  // ── Commission Rules tab ───────────────────────────────────────────────────
  const [rules, setRules] = useState<CommissionRule[]>([]);
  const [rulesLoading, setRulesLoading] = useState(false);
  const [showRuleModal, setShowRuleModal] = useState(false);
  const [ruleForm, setRuleForm] = useState({ job_position: "", surgery_type: "", commission_percent: "", start_date: new Date().toISOString().slice(0, 10), notes: "" });
  const [ruleSaving, setRuleSaving] = useState(false);
  const [ruleError, setRuleError] = useState("");
  const [ruleSuccess, setRuleSuccess] = useState("");
  const [allPositions, setAllPositions] = useState<JobPosition[]>([]);
  const [allSurgeryTypes, setAllSurgeryTypes] = useState<SurgeryType[]>([]);

  const fetchRules = () => {
    setRulesLoading(true);
    get<PaginatedResponse<CommissionRule>>("/payroll/commission-rules/?page_size=100&is_active=true")
      .then((d) => setRules(d.results || []))
      .catch(() => {})
      .finally(() => setRulesLoading(false));
  };

  useEffect(() => {
    if (tab === "commission") {
      fetchRules();
      get<PaginatedResponse<JobPosition>>("/employees/positions/?page_size=100&is_active=true")
        .then((d) => setAllPositions(d.results || []))
        .catch(() => {});
      get<PaginatedResponse<SurgeryType>>("/surgeries/types/?page_size=100&is_active=true")
        .then((d) => setAllSurgeryTypes(d.results || []))
        .catch(() => {});
    }
  }, [tab]);

  const handleAddRule = async () => {
    if (!ruleForm.job_position) { setRuleError("سمت شغلی را انتخاب کنید."); return; }
    if (!ruleForm.surgery_type) { setRuleError("نوع عمل را انتخاب کنید."); return; }
    const pct = parseFloat(ruleForm.commission_percent);
    if (isNaN(pct) || pct <= 0 || pct > 100) { setRuleError("درصد کمیسیون باید بین ۱ و ۱۰۰ باشد."); return; }
    setRuleSaving(true);
    setRuleError("");
    try {
      await post("/payroll/commission-rules/", {
        job_position: parseInt(ruleForm.job_position),
        surgery_type: parseInt(ruleForm.surgery_type),
        commission_percent: pct,
        start_date: ruleForm.start_date,
        is_active: true,
        notes: ruleForm.notes.trim(),
      });
      setShowRuleModal(false);
      setRuleForm({ job_position: "", surgery_type: "", commission_percent: "", start_date: new Date().toISOString().slice(0, 10), notes: "" });
      setRuleSuccess("قانون کمیسیون ثبت شد.");
      fetchRules();
      setTimeout(() => setRuleSuccess(""), 3000);
    } catch {
      setRuleError("خطا در ثبت قانون کمیسیون. ممکن است ترکیب تکراری باشد.");
    } finally {
      setRuleSaving(false);
    }
  };

  const deactivateRule = async (id: number) => {
    if (!confirm("آیا مطمئن هستید؟ این قانون غیرفعال می‌شود.")) return;
    try {
      await patch(`/payroll/commission-rules/${id}/`, { is_active: false });
      fetchRules();
    } catch {}
  };

  return (
    <div dir="rtl">
      <div className="flex items-start justify-between gap-4 mb-6 flex-wrap">
        <div className="flex-1 min-w-0">
          <span className="block text-[11px] font-bold text-purple tracking-widest uppercase mb-1 opacity-85">کارمندان</span>
          <h1 className="text-[26px] font-bold text-text leading-tight m-0">حقوق و دستمزد</h1>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-bg-page border border-border rounded-xl p-1 mb-6 w-fit">
        {([["report", "گزارش حقوقی"], ["wages", "حقوق ثابت"], ["commission", "قوانین کمیسیون"]] as [Tab, string][]).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors cursor-pointer ${tab === key ? "bg-card text-purple shadow-sm" : "text-muted hover:text-text"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── Report Tab ── */}
      {tab === "report" && (
        <>
          <div className="bg-card border border-border rounded-2xl p-4 shadow-sm mb-4 flex gap-3 items-end flex-wrap">
            <div className="flex flex-col gap-1 min-w-0">
              <label className="text-[11px] font-semibold text-muted">دوره حقوقی</label>
              <select
                value={selectedPeriod?.id || ""}
                onChange={(e) => {
                  const p = periods.find((p) => p.id === parseInt(e.target.value)) || null;
                  loadReport(p);
                }}
                className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-card outline-none focus:border-purple focus:shadow-[0_0_0_3px_rgba(0,102,179,.12)] transition-all"
              >
                <option value="">انتخاب دوره</option>
                {periods.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.display_name || `${toPersianDigits(p.year)}/${toPersianDigits(String(p.month).padStart(2, "0"))}`}
                    {" — "}{STATUS_LABEL[p.status] || p.status}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {report && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 mb-5">
              <div className="bg-card border border-border rounded-2xl p-5 shadow-sm">
                <div className="text-xs font-bold text-muted mb-2">حقوق ثابت</div>
                <div className="text-lg font-extrabold text-text-strong" dir="ltr">{formatCurrency(parseFloat(report.total_fixed_salary || "0"))}</div>
              </div>
              <div className="bg-card border border-border rounded-2xl p-5 shadow-sm">
                <div className="text-xs font-bold text-muted mb-2">کمیسیون</div>
                <div className="text-lg font-extrabold text-text-strong" dir="ltr">{formatCurrency(parseFloat(report.total_commission || "0"))}</div>
              </div>
              <div className="bg-card border border-border rounded-2xl p-5 shadow-sm">
                <div className="text-xs font-bold text-muted mb-2">کل هزینه نیروی انسانی</div>
                <div className="text-lg font-extrabold text-purple" dir="ltr">{formatCurrency(parseFloat(report.total_labor_cost || "0"))}</div>
              </div>
              <div className="bg-card border border-border rounded-2xl p-5 shadow-sm">
                <div className="text-xs font-bold text-muted mb-2">تعداد کارمندان</div>
                <div className="text-lg font-extrabold text-text-strong">{toPersianDigits(report.employee_count)}</div>
              </div>
            </div>
          )}

          <div className="bg-card border border-border rounded-2xl shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    {["کارمند", "سمت", "حقوق ثابت", "کمیسیون", "مجموع"].map((h) => (
                      <th key={h} className="bg-bg-page px-4 py-2.5 text-[11px] font-bold text-muted text-right tracking-[.4px] uppercase border-b-2 border-border whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {reportLoading ? (
                    <tr><td colSpan={5} className="text-center py-7 text-muted text-sm">در حال بارگذاری…</td></tr>
                  ) : !selectedPeriod ? (
                    <tr><td colSpan={5} className="text-center py-7 text-muted text-sm">یک دوره حقوقی انتخاب کنید</td></tr>
                  ) : !report || report.employees.length === 0 ? (
                    <tr><td colSpan={5} className="text-center py-7 text-muted text-sm">داده‌ای برای این دوره یافت نشد</td></tr>
                  ) : (
                    report.employees.map((r) => (
                      <tr key={r.employee_id} className="hover:bg-bg-page">
                        <td className="px-4 py-3 text-sm font-semibold text-text border-b border-border/55">{r.employee_name}</td>
                        <td className="px-4 py-3 text-sm text-muted border-b border-border/55">{r.job_position || "—"}</td>
                        <td className="px-4 py-3 text-sm text-text border-b border-border/55 text-left" dir="ltr">{formatCurrency(parseFloat(r.fixed_salary || "0"))}</td>
                        <td className="px-4 py-3 text-sm text-green font-bold border-b border-border/55 text-left" dir="ltr">{formatCurrency(parseFloat(r.total_commission || "0"))}</td>
                        <td className="px-4 py-3 text-sm text-purple font-bold border-b border-border/55 text-left" dir="ltr">{formatCurrency(parseFloat(r.total_payment || "0"))}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* ── Monthly Wages Tab ── */}
      {tab === "wages" && (
        <>
          {wageSuccess && <div className="mb-4 bg-green-bg border border-green/30 text-green rounded-xl px-4 py-3 text-sm">{wageSuccess}</div>}
          <div className="flex justify-between items-center mb-4">
            <div className="text-sm font-semibold text-text">حقوق ثابت ماهیانه فعال</div>
            <button
              onClick={() => { setWageForm({ employee: "", amount: "", start_date: new Date().toISOString().slice(0, 10), notes: "" }); setWageError(""); setShowWageModal(true); }}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium bg-purple text-white cursor-pointer hover:shadow-[0_3px_8px_rgba(0,102,179,.30)] transition-shadow"
            >
              + افزودن حقوق
            </button>
          </div>
          <div className="bg-card border border-border rounded-2xl shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    {["کارمند", "مبلغ ماهیانه (تومان)", "تاریخ شروع", "عملیات"].map((h) => (
                      <th key={h} className="bg-bg-page px-4 py-2.5 text-[11px] font-bold text-muted text-right tracking-[.4px] uppercase border-b-2 border-border whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {wagesLoading ? (
                    <tr><td colSpan={4} className="text-center py-7 text-muted text-sm">در حال بارگذاری…</td></tr>
                  ) : wages.length === 0 ? (
                    <tr><td colSpan={4} className="text-center py-7 text-muted text-sm">حقوق ثابتی تعریف نشده</td></tr>
                  ) : (
                    wages.map((w) => (
                      <tr key={w.id} className="hover:bg-bg-page">
                        <td className="px-4 py-3 text-sm font-semibold text-text border-b border-border/55">{w.employee_name}</td>
                        <td className="px-4 py-3 text-sm font-bold text-text border-b border-border/55 text-left" dir="ltr">{formatCurrency(parseFloat(w.amount || "0"))}</td>
                        <td className="px-4 py-3 text-sm text-muted border-b border-border/55">{w.start_date || "—"}</td>
                        <td className="px-4 py-3 border-b border-border/55">
                          <button onClick={() => deactivateWage(w.id)} className="text-xs text-red hover:text-red/80 cursor-pointer">غیرفعال</button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {showWageModal && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
              <div className="bg-card border border-border rounded-2xl shadow-xl w-full max-w-md" dir="rtl">
                <div className="flex items-center justify-between px-6 py-4 border-b border-border">
                  <h2 className="text-base font-bold text-text">افزودن حقوق ثابت</h2>
                  <button onClick={() => setShowWageModal(false)} className="text-muted hover:text-text text-xl cursor-pointer">×</button>
                </div>
                <div className="px-6 py-5 space-y-4">
                  {wageError && <div className="bg-red-bg border border-red/30 text-red rounded-xl px-3 py-2.5 text-sm">{wageError}</div>}
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-muted">کارمند <span className="text-red">*</span></label>
                    <select value={wageForm.employee} onChange={(e) => setWageForm({ ...wageForm, employee: e.target.value })}
                      className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all">
                      <option value="">انتخاب کارمند</option>
                      {allEmployees.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
                    </select>
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-muted">مبلغ ماهیانه (تومان) <span className="text-red">*</span></label>
                    <input type="number" min="0" value={wageForm.amount} onChange={(e) => setWageForm({ ...wageForm, amount: e.target.value })}
                      className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all" placeholder="مثال: ۱۵۰۰۰۰۰۰" />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-muted">تاریخ شروع</label>
                    <input type="date" value={wageForm.start_date} onChange={(e) => setWageForm({ ...wageForm, start_date: e.target.value })}
                      className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all" dir="ltr" />
                  </div>
                </div>
                <div className="flex gap-2 px-6 py-4 border-t border-border justify-end">
                  <button onClick={() => setShowWageModal(false)} className="px-4 py-2 rounded-xl text-sm border border-border text-muted hover:bg-bg-page cursor-pointer">انصراف</button>
                  <button onClick={handleAddWage} disabled={wageSaving} className="px-4 py-2 rounded-xl text-sm bg-purple text-white disabled:opacity-60 cursor-pointer">
                    {wageSaving ? "در حال ذخیره…" : "ذخیره"}
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Commission Rules Tab ── */}
      {tab === "commission" && (
        <>
          {ruleSuccess && <div className="mb-4 bg-green-bg border border-green/30 text-green rounded-xl px-4 py-3 text-sm">{ruleSuccess}</div>}
          <div className="flex justify-between items-center mb-4">
            <div className="text-sm font-semibold text-text">قوانین کمیسیون فعال</div>
            <button
              onClick={() => { setRuleForm({ job_position: "", surgery_type: "", commission_percent: "", start_date: new Date().toISOString().slice(0, 10), notes: "" }); setRuleError(""); setShowRuleModal(true); }}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium bg-purple text-white cursor-pointer hover:shadow-[0_3px_8px_rgba(0,102,179,.30)] transition-shadow"
            >
              + افزودن قانون کمیسیون
            </button>
          </div>

          <div className="mb-4 bg-card border border-border rounded-2xl p-4 shadow-sm text-xs text-muted">
            هر قانون درصد کمیسیون را برای ترکیب (سمت شغلی + نوع عمل) مشخص می‌کند. وقتی عمل جراحی ثبت می‌شود، کمیسیون کارمندان به صورت خودکار محاسبه و ثبت می‌شود.
          </div>

          <div className="bg-card border border-border rounded-2xl shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    {["سمت شغلی", "نوع عمل", "درصد کمیسیون", "تاریخ شروع", "عملیات"].map((h) => (
                      <th key={h} className="bg-bg-page px-4 py-2.5 text-[11px] font-bold text-muted text-right tracking-[.4px] uppercase border-b-2 border-border whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rulesLoading ? (
                    <tr><td colSpan={5} className="text-center py-7 text-muted text-sm">در حال بارگذاری…</td></tr>
                  ) : rules.length === 0 ? (
                    <tr><td colSpan={5} className="text-center py-7 text-muted text-sm">قانون کمیسیونی تعریف نشده</td></tr>
                  ) : (
                    rules.map((r) => (
                      <tr key={r.id} className="hover:bg-bg-page">
                        <td className="px-4 py-3 border-b border-border/55">
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-light text-purple">{r.job_position_name}</span>
                        </td>
                        <td className="px-4 py-3 text-sm text-text border-b border-border/55">{r.surgery_type_name}</td>
                        <td className="px-4 py-3 border-b border-border/55">
                          <span className="text-sm font-bold text-green">{toPersianDigits(parseFloat(r.commission_percent || "0").toString())}٪</span>
                        </td>
                        <td className="px-4 py-3 text-sm text-muted border-b border-border/55">{r.start_date || "—"}</td>
                        <td className="px-4 py-3 border-b border-border/55">
                          <button onClick={() => deactivateRule(r.id)} className="text-xs text-red hover:text-red/80 cursor-pointer">غیرفعال</button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {showRuleModal && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
              <div className="bg-card border border-border rounded-2xl shadow-xl w-full max-w-md" dir="rtl">
                <div className="flex items-center justify-between px-6 py-4 border-b border-border">
                  <h2 className="text-base font-bold text-text">افزودن قانون کمیسیون</h2>
                  <button onClick={() => setShowRuleModal(false)} className="text-muted hover:text-text text-xl cursor-pointer">×</button>
                </div>
                <div className="px-6 py-5 space-y-4">
                  {ruleError && <div className="bg-red-bg border border-red/30 text-red rounded-xl px-3 py-2.5 text-sm">{ruleError}</div>}
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-muted">سمت شغلی <span className="text-red">*</span></label>
                    <select value={ruleForm.job_position} onChange={(e) => setRuleForm({ ...ruleForm, job_position: e.target.value })}
                      className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all">
                      <option value="">انتخاب سمت</option>
                      {allPositions.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-muted">نوع عمل <span className="text-red">*</span></label>
                    <select value={ruleForm.surgery_type} onChange={(e) => setRuleForm({ ...ruleForm, surgery_type: e.target.value })}
                      className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all">
                      <option value="">انتخاب نوع عمل</option>
                      {allSurgeryTypes.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                    </select>
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-muted">درصد کمیسیون (۱–۱۰۰) <span className="text-red">*</span></label>
                    <input type="number" min="1" max="100" step="0.01" value={ruleForm.commission_percent} onChange={(e) => setRuleForm({ ...ruleForm, commission_percent: e.target.value })}
                      className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all" placeholder="مثال: ۱۵" />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-muted">تاریخ شروع اعتبار</label>
                    <input type="date" value={ruleForm.start_date} onChange={(e) => setRuleForm({ ...ruleForm, start_date: e.target.value })}
                      className="h-[38px] px-3 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple transition-all" dir="ltr" />
                  </div>
                </div>
                <div className="flex gap-2 px-6 py-4 border-t border-border justify-end">
                  <button onClick={() => setShowRuleModal(false)} className="px-4 py-2 rounded-xl text-sm border border-border text-muted hover:bg-bg-page cursor-pointer">انصراف</button>
                  <button onClick={handleAddRule} disabled={ruleSaving} className="px-4 py-2 rounded-xl text-sm bg-purple text-white disabled:opacity-60 cursor-pointer">
                    {ruleSaving ? "در حال ذخیره…" : "ذخیره"}
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
