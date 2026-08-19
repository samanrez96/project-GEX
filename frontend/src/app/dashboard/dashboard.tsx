"use client";

import { useEffect, useState } from "react";
import { get, type BalanceReport, type PaginatedResponse, type SurgeryHistory } from "@/lib/api";
import { formatCurrency, toPersianDigits, formatDate } from "@/lib/utils";

const STATUS_MAP: Record<string, { cls: string; label: string }> = {
  planned: { cls: "bg-purple-light text-purple", label: "برنامه‌ریزی شده" },
  in_progress: { cls: "bg-amber-bg text-amber", label: "در حال انجام" },
  completed: { cls: "bg-green-bg text-green", label: "انجام شده" },
  cancelled: { cls: "bg-red-bg text-red", label: "لغو شده" },
};

function StatusBadge({ status, display }: { status: string; display?: string }) {
  const info = STATUS_MAP[status] || { cls: "bg-gray-100 text-gray-600", label: display || status || "—" };
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${info.cls}`}>
      {info.label}
    </span>
  );
}

function MetricCard({
  label,
  value,
  helper,
  icon,
  color,
  borderColor,
}: {
  label: string;
  value: string;
  helper: string;
  icon: React.ReactNode;
  color: string;
  borderColor: string;
}) {
  return (
    <div className="bg-card border border-border rounded-2xl p-[18px] shadow-sm hover:shadow-md transition-shadow relative overflow-hidden" style={{ borderTop: `3px solid ${borderColor}` }}>
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-medium text-muted tracking-normal">{label}</span>
        <div className="w-[34px] h-[34px] rounded-[9px] flex items-center justify-center shrink-0" style={{ background: color + "18", color }}>
          {icon}
        </div>
      </div>
      <div className="text-[23px] font-extrabold leading-[1.25] tracking-tight text-text-strong whitespace-nowrap overflow-hidden text-ellipsis text-left" dir="ltr">
        {value}
      </div>
      <div className="text-[11.5px] text-muted mt-1.5">{helper}</div>
    </div>
  );
}

function CostBreakdownBar({ label, value, pct, color }: { label: string; value: string; pct: number; color: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex justify-between items-center">
        <span className="text-xs font-medium text-[#36424F]">{label}</span>
        <span className="text-xs font-bold text-text-strong text-left" dir="ltr">{value}</span>
      </div>
      <div className="h-2 bg-[#EDF1F6] rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-[width] duration-600" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [balance, setBalance] = useState<BalanceReport | null>(null);
  const [surgeries, setSurgeries] = useState<SurgeryHistory[]>([]);
  const [surgeryCount, setSurgeryCount] = useState<number | null>(null);

  useEffect(() => {
    get<BalanceReport>("/finance/reports/balance/").then(setBalance).catch(() => {});

    const now = new Date();
    const y = now.getFullYear();
    const m = now.getMonth() + 1;
    const pad = (n: number) => String(n).padStart(2, "0");
    const firstDay = `${y}-${pad(m)}-01`;
    const lastDay = `${y}-${pad(m)}-${pad(new Date(y, m, 0).getDate())}`;
    get<PaginatedResponse<SurgeryHistory>>(
      `/surgeries/history/?surgery_date_from=${firstDay}&surgery_date_to=${lastDay}&page_size=1`
    )
      .then((d) => setSurgeryCount(d.count))
      .catch(() => {});

    get<PaginatedResponse<SurgeryHistory>>("/surgeries/history/?page_size=8&ordering=-surgery_date")
      .then((d) => setSurgeries(d.results || []))
      .catch(() => {});
  }, []);

  const totalExp = balance?.total_expense || 0;
  const equipment = balance?.total_equipment_cost || 0;
  const medicine = balance?.total_medicine_cost || 0;
  const employee = balance?.total_employee_cost || 0;
  const other = Math.max(0, totalExp - equipment - medicine - employee);
  const grandTotal = equipment + medicine + employee + other;
  const pct = (v: number) => (grandTotal > 0 ? (v / grandTotal) * 100 : 0);

  return (
    <div dir="rtl">
      <div className="flex items-start justify-between gap-4 mb-7 flex-wrap">
        <div className="flex-1 min-w-0">
          <span className="block text-[11px] font-bold text-purple tracking-widest uppercase mb-1 opacity-85">نمای کلی مرکز</span>
          <h1 className="text-[26px] font-bold text-text leading-tight tracking-tight m-0">داشبورد اصلی</h1>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 mb-3.5">
        <MetricCard label="مجموع درآمد" value={formatCurrency(balance?.total_income)} helper="ریال" borderColor="#1E9E6A" color="#1E9E6A"
          icon={<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>} />
        <MetricCard label="مجموع هزینه" value={formatCurrency(balance?.total_expense)} helper="ریال" borderColor="#EB2D4B" color="#EB2D4B"
          icon={<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M23 18 13.5 8.5 8.5 13.5 1 6"/><polyline points="17 18 23 18 23 12"/></svg>} />
        <MetricCard label="سود خالص" value={formatCurrency(balance?.final_balance)} helper="ریال" borderColor="#0066B3" color="#0066B3"
          icon={<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M3 12h18M3 18h18"/></svg>} />
        <MetricCard label="عمل‌های این ماه" value={surgeryCount !== null ? toPersianDigits(surgeryCount) : "—"} helper="عمل ثبت‌شده" borderColor="#7c3aed" color="#7c3aed"
          icon={<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 12h6M12 9v6"/></svg>} />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 mb-3.5">
        <MetricCard label="هزینه حقوق کارکنان" value={formatCurrency(balance?.total_employee_cost)} helper="ریال" borderColor="#6366f1" color="#6366f1"
          icon={<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>} />
        <MetricCard label="هزینه تجهیزات" value={formatCurrency(balance?.total_equipment_cost)} helper="ریال" borderColor="#ea580c" color="#ea580c"
          icon={<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>} />
        <MetricCard label="هزینه دارو" value={formatCurrency(balance?.total_medicine_cost)} helper="ریال" borderColor="#0891b2" color="#0891b2"
          icon={<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m10.5 20H4a2 2 0 0 1-2-2V5c0-1.1.9-2 2-2h3.93a2 2 0 0 1 1.66.9l.82 1.2a2 2 0 0 0 1.66.9H20a2 2 0 0 1 2 2v3"/><circle cx="18" cy="18" r="4"/><path d="M18 14v8M14 18h8"/></svg>} />
        <MetricCard label="درآمد کمیسیون مرکز" value={formatCurrency(balance?.center_commission_income)} helper="ریال" borderColor="#65a30d" color="#65a30d"
          icon={<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.6fr] gap-3.5 mt-3.5">
        <div className="bg-card border border-border rounded-2xl shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-border">
            <h3 className="text-sm font-semibold text-text m-0">ترکیب هزینه‌ها</h3>
          </div>
          <div className="flex flex-col gap-4 p-4 pt-1 pb-5">
            <CostBreakdownBar label="تجهیزات" value={formatCurrency(equipment)} pct={pct(equipment)} color="#ea580c" />
            <CostBreakdownBar label="دارو" value={formatCurrency(medicine)} pct={pct(medicine)} color="#0891b2" />
            <CostBreakdownBar label="حقوق کارکنان" value={formatCurrency(employee)} pct={pct(employee)} color="#6366f1" />
            <CostBreakdownBar label="سایر" value={formatCurrency(other)} pct={pct(other)} color="#97A4B5" />
          </div>
        </div>

        <div className="bg-card border border-border rounded-2xl shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-border">
            <h3 className="text-sm font-semibold text-text m-0">آخرین عمل های جراحی</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  {["بیمار", "نوع عمل", "تاریخ", "مبلغ (ریال)", "وضعیت"].map((h) => (
                    <th key={h} className="bg-bg-page px-4 py-2.5 text-[11px] font-bold text-muted text-right tracking-[.4px] uppercase border-b-2 border-border whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {surgeries.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="text-center py-7 text-muted text-sm">هیچ عملی ثبت نشده</td>
                  </tr>
                ) : (
                  surgeries.map((s) => (
                    <tr key={s.id} className="hover:bg-bg-page">
                      <td className="px-4 py-3 text-sm text-text border-b border-border/55">{s.patient_name || "—"}</td>
                      <td className="px-4 py-3 text-sm text-text border-b border-border/55">{s.surgery_type_name || "—"}</td>
                      <td className="px-4 py-3 text-sm text-text border-b border-border/55">{formatDate(s.surgery_date)}</td>
                      <td className="px-4 py-3 text-sm text-text border-b border-border/55 text-left" dir="ltr">{formatCurrency(parseFloat(String(s.amount || "0")))}</td>
                      <td className="px-4 py-3 border-b border-border/55"><StatusBadge status={s.status} display={s.status_display} /></td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
