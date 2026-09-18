"use client";

import { useEffect, useState } from "react";
import { get, type BalanceReport, type FinanceTrend } from "@/lib/api";
import { formatCurrency, toPersianDigits } from "@/lib/utils";

export default function FinanceDashboard() {
  const [balance, setBalance] = useState<BalanceReport | null>(null);
  const [trend, setTrend] = useState<FinanceTrend[]>([]);

  useEffect(() => {
    get<BalanceReport>("/finance/reports/balance/").then(setBalance).catch(() => {});
    get<FinanceTrend[]>("/finance/reports/trend/").then(setTrend).catch(() => {});
  }, []);

  return (
    <div dir="rtl">
      <div className="mb-7">
        <span className="block text-[11px] font-bold text-purple tracking-widest uppercase mb-1 opacity-85">مالی</span>
        <h1 className="text-[26px] font-bold text-text leading-tight m-0">داشبورد مالی</h1>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 mb-5">
        {[
          { label: "مجموع درآمد", value: balance?.total_income_period, color: "#1E9E6A" },
          { label: "مجموع هزینه", value: balance?.total_expense_period, color: "#EB2D4B" },
          { label: "سود خالص", value: balance?.final_balance_cumulative, color: "#0066B3" },
          { label: "کمیسیون مرکز", value: balance?.center_commission_income_period, color: "#65a30d" },
        ].map((item) => (
          <div
            key={item.label}
            className="bg-card border border-border rounded-2xl p-5 shadow-sm hover:shadow-md transition-shadow"
            style={{ borderTop: `3px solid ${item.color}` }}
          >
            <div className="text-xs font-bold text-muted tracking-[.6px] uppercase mb-2.5">{item.label}</div>
            <div className="text-[22px] font-extrabold tracking-tight leading-[1.1] text-left" dir="ltr">{formatCurrency(item.value)}</div>
          </div>
        ))}
      </div>

      {trend.length > 0 && (
        <div className="bg-card border border-border rounded-2xl shadow-sm overflow-hidden mb-5">
          <div className="px-5 py-3.5 border-b border-border">
            <h3 className="text-[15px] font-bold m-0">روند درآمد و هزینه</h3>
          </div>
          <div className="p-5">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {trend.map((t) => (
                <div key={t.month} className="flex items-center justify-between p-3 rounded-xl bg-bg-page">
                  <span className="text-sm font-semibold text-text">{toPersianDigits(t.month)}</span>
                  <div className="text-left text-xs" dir="ltr">
                    <span className="text-green font-bold">{formatCurrency(t.income)}</span>
                    <span className="text-muted mx-1">/</span>
                    <span className="text-red font-bold">{formatCurrency(t.expense)}</span>
                    {t.cumulative_balance !== undefined && (
                      <span className="block text-xs text-purple font-medium mt-0.5">
                        موجودی: {formatCurrency(t.cumulative_balance)}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}