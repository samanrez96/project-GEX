"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      const next = typeof window !== "undefined"
        ? window.location.pathname + window.location.search
        : "/dashboard";
      router.replace(`/login?next=${encodeURIComponent(next)}`);
    }
  }, [loading, user, router]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg-page">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-4 border-purple/20 border-t-purple rounded-full animate-spin" />
          <div className="text-[13px] text-muted">در حال بارگذاری…</div>
        </div>
      </div>
    );
  }

  if (!user) return null;

  return <>{children}</>;
}