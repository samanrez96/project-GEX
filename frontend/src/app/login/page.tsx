"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const { user, loading: authLoading, login } = useAuth();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  // Already authenticated → skip straight to dashboard
  useEffect(() => {
    if (!authLoading && user) {
      router.replace("/dashboard");
    }
  }, [authLoading, user, router]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");

    if (!username.trim()) {
      setError("نام کاربری را وارد کنید.");
      return;
    }
    if (!password) {
      setError("رمز عبور را وارد کنید.");
      return;
    }

    setSubmitting(true);
    try {
      await login(username.trim(), password);
      router.replace("/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setError("نام کاربری یا رمز عبور نادرست است.");
        } else if (err.status === 400) {
          setError("اطلاعات ورودی نامعتبر است.");
        } else {
          setError(`خطا در ورود (کد ${err.status}).`);
        }
      } else {
        setError("خطا در ارتباط با سرور. لطفاً دوباره تلاش کنید.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg-page">
        <div className="w-10 h-10 border-4 border-purple/20 border-t-purple rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div dir="rtl" className="min-h-screen bg-bg-page flex items-center justify-center p-4">
      <div className="w-full max-w-[420px]">
        {/* Logo / brand */}
        <div className="flex flex-col items-center mb-7">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-purple to-[#3385CC] flex items-center justify-center shadow-lg shadow-purple/30 mb-3">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round">
              <path d="M11 2a2 2 0 0 0-2 2v5H4a2 2 0 0 0-2 2v2c0 1.1.9 2 2 2h5v5c0 1.1.9 2 2 2h2a2 2 0 0 0 2-2v-5h5a2 2 0 0 0 2-2v-2a2 2 0 0 0-2-2h-5V4a2 2 0 0 0-2-2h-2z" />
            </svg>
          </div>
          <h1 className="text-[22px] font-bold text-text-strong m-0">مرکز جراحی</h1>
          <p className="text-[13px] text-muted mt-1">سامانه مدیریت یکپارچه</p>
        </div>

        {/* Card */}
        <div className="bg-card border border-border rounded-2xl shadow-sm p-7">
          <h2 className="text-[18px] font-bold text-text mb-1">ورود به سامانه</h2>
          <p className="text-[12.5px] text-muted mb-5">برای ادامه، اطلاعات حساب خود را وارد کنید.</p>

          {error && (
            <div className="mb-4 bg-red-bg border border-red/30 text-red rounded-xl px-4 py-3 text-[13px]">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="username" className="text-xs font-semibold text-muted">
                نام کاربری
              </label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                autoFocus
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={submitting}
                className="h-[42px] px-3.5 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple focus:shadow-[0_0_0_3px_rgba(0,102,179,.12)] transition-all disabled:opacity-60"
                placeholder="admin"
                dir="ltr"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="password" className="text-xs font-semibold text-muted">
                رمز عبور
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={submitting}
                  className="w-full h-[42px] px-3.5 pr-3.5 pl-11 border border-border rounded-xl text-sm text-text bg-bg-page outline-none focus:border-purple focus:shadow-[0_0_0_3px_rgba(0,102,179,.12)] transition-all disabled:opacity-60"
                  placeholder="••••••••"
                  dir="ltr"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute left-2 top-1/2 -translate-y-1/2 p-2 text-muted hover:text-purple transition-colors cursor-pointer"
                  aria-label={showPassword ? "پنهان کردن رمز" : "نمایش رمز"}
                  tabIndex={-1}
                >
                  {showPassword ? (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                      <line x1="1" y1="1" x2="23" y2="23" />
                    </svg>
                  ) : (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full h-[44px] rounded-xl text-sm font-semibold bg-purple text-white shadow-[0_1px_3px_rgba(0,102,179,.28)] hover:shadow-[0_3px_10px_rgba(0,102,179,.32)] transition-shadow disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer flex items-center justify-center gap-2"
            >
              {submitting && (
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              )}
              {submitting ? "در حال ورود…" : "ورود"}
            </button>
          </form>

          <div className="mt-5 pt-5 border-t border-border text-center">
            <p className="text-[12.5px] text-muted">
              حساب کاربری ندارید؟{" "}
              <a href="/register" className="text-purple font-semibold hover:underline">
                راهنمای دریافت حساب
              </a>
            </p>
          </div>
        </div>

        <p className="text-center text-[11.5px] text-muted/70 mt-6">
          © {new Date().getFullYear()} — سامانه مدیریت مرکز جراحی
        </p>
      </div>
    </div>
  );
}