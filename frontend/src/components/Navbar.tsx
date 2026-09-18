"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth";
import type { AuthUser } from "@/lib/api";

function displayName(u: AuthUser | null): string {
  if (!u) return "";
  const full = `${u.first_name || ""} ${u.last_name || ""}`.trim();
  return full || u.username || u.email || "";
}

function roleLabel(u: AuthUser | null): string {
  if (!u) return "";
  if (u.is_superuser) return "مدیر ارشد";
  if (u.roles?.includes("admin")) return "مدیر";
  if (u.roles?.includes("finance_user")) return "کارشناس مالی";
  if (u.roles?.includes("employee_manager")) return "مدیر کارکنان";
  if (u.roles?.includes("inventory_user")) return "کارشناس انبار";
  if (u.is_staff) return "کارمند";
  return "کاربر";
}

export default function Navbar({ onMenuToggle }: { onMenuToggle: () => void }) {
  const { user, logout } = useAuth();

  return (
    <nav className="fixed top-0 right-0 left-0 h-16 bg-card border-b border-border flex items-center px-5 gap-3 z-50 shadow-sm">
      <button
        onClick={onMenuToggle}
        className="text-muted text-xl cursor-pointer p-1 rounded-md hover:bg-bg-page hover:text-text transition-colors lg:hidden"
        aria-label="نوار کناری"
      >
        ☰
      </button>
      <Link href="/dashboard" className="text-[16px] font-bold text-purple whitespace-nowrap">
        مرکز جراحی — مدیریت
      </Link>
      <div className="me-auto flex items-center gap-3">
        {user && (
          <>
            <span className="text-muted text-sm hidden sm:inline">
              {displayName(user) || "—"}
            </span>
            <span className="hidden sm:inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-purple-light text-purple">
              {roleLabel(user)}
            </span>
          </>
        )}
        <button
          onClick={logout}
          className="text-muted text-[13px] border border-border px-3.5 py-[5px] rounded-md cursor-pointer hover:bg-bg-page hover:border-purple hover:text-purple transition-colors"
        >
          خروج
        </button>
      </div>
    </nav>
  );
}