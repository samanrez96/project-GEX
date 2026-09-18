"use client";

import Link from "next/link";

export default function RegisterPage() {
  return (
    <div dir="rtl" className="min-h-screen bg-bg-page flex items-center justify-center p-4">
      <div className="w-full max-w-[480px]">
        <div className="flex flex-col items-center mb-7">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-purple to-[#3385CC] flex items-center justify-center shadow-lg shadow-purple/30 mb-3">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round">
              <path d="M11 2a2 2 0 0 0-2 2v5H4a2 2 0 0 0-2 2v2c0 1.1.9 2 2 2h5v5c0 1.1.9 2 2 2h2a2 2 0 0 0 2-2v-5h5a2 2 0 0 0 2-2v-2a2 2 0 0 0-2-2h-5V4a2 2 0 0 0-2-2h-2z" />
            </svg>
          </div>
          <h1 className="text-[22px] font-bold text-text-strong m-0">مرکز جراحی</h1>
          <p className="text-[13px] text-muted mt-1">سامانه مدیریت یکپارچه</p>
        </div>

        <div className="bg-card border border-border rounded-2xl shadow-sm p-7">
          <div className="flex items-start gap-3 mb-4">
            <div className="w-10 h-10 rounded-full bg-purple-light flex items-center justify-center shrink-0">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#0066B3" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="16" x2="12" y2="12" />
                <line x1="12" y1="8" x2="12.01" y2="8" />
              </svg>
            </div>
            <div>
              <h2 className="text-[17px] font-bold text-text m-0">ثبت‌نام آزاد غیرفعال است</h2>
              <p className="text-[12.5px] text-muted mt-1">
                حساب‌های کاربری این سامانه توسط مدیر سیستم ساخته می‌شوند.
              </p>
            </div>
          </div>

          <div className="bg-bg-page border border-border rounded-xl p-4 mb-5 space-y-2.5">
            <div className="text-[12.5px] font-bold text-text">برای دریافت حساب کاربری:</div>
            <ol className="text-[12.5px] text-muted space-y-2 pr-1">
              <li className="flex gap-2">
                <span className="text-purple font-bold shrink-0">۱.</span>
                <span>با مدیر سیستم مرکز تماس بگیرید و درخواست ایجاد حساب دهید.</span>
              </li>
              <li className="flex gap-2">
                <span className="text-purple font-bold shrink-0">۲.</span>
                <span>پس از ایجاد حساب، نام کاربری و رمز عبور اولیه برای شما ارسال خواهد شد.</span>
              </li>
              <li className="flex gap-2">
                <span className="text-purple font-bold shrink-0">۳.</span>
                <span>در اولین ورود، توصیه می‌شود رمز عبور خود را تغییر دهید.</span>
              </li>
            </ol>
          </div>

          <Link
            href="/login"
            className="w-full h-[44px] rounded-xl text-sm font-semibold bg-purple text-white shadow-[0_1px_3px_rgba(0,102,179,.28)] hover:shadow-[0_3px_10px_rgba(0,102,179,.32)] transition-shadow cursor-pointer flex items-center justify-center gap-2"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round">
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </svg>
            بازگشت به صفحه‌ی ورود
          </Link>
        </div>

        <p className="text-center text-[11.5px] text-muted/70 mt-6">
          © {new Date().getFullYear()} — سامانه مدیریت مرکز جراحی
        </p>
      </div>
    </div>
  );
}