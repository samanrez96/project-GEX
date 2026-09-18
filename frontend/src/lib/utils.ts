/**
 * تبدیل اعداد انگلیسی به فارسی
 */
export function toPersianDigits(n: string | number): string {
  return String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
}

/**
 * تبدیل اعداد فارسی به انگلیسی (برای ارسال به بک‌اند)
 */
export function toEnglishDigits(s: string): string {
  return s.replace(/[۰-۹]/g, (d) => "0123456789"["۰۱۲۳۴۵۶۷۸۹".indexOf(d)]);
}

/**
 * فرمت‌کننده‌ی اعداد با جداکننده‌ی هزارگان فارسی
 */
export function formatCurrency(num: number | null | undefined): string {
  if (num === null || num === undefined || isNaN(num)) return "—";
  const abs = Math.abs(num);
  const formatted = abs.toLocaleString("en-US", { maximumFractionDigits: 0 });
  const persian = toPersianDigits(formatted);
  return num < 0 ? `−${persian}` : persian;
}

/**
 * فرمت‌کننده‌ی تاریخ میلادی به شمسی (با استفاده از کتابخانه‌ی jalali-moment یا similar)
 * اگر کتابخانه ندارید، از تابع ساده‌ی زیر استفاده کنید (تاریخ ISO را به صورت خام برمی‌گرداند)
 */
export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  // اگر نیاز به تبدیل شمسی دارید، از یک کتابخانه مثل 'moment-jalaali' استفاده کنید
  // فعلاً همان تاریخ میلادی را با فرمت محلی برمی‌گرداند
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr.slice(0, 10);
    return toPersianDigits(d.toLocaleDateString("fa-IR"));
  } catch {
    return dateStr.slice(0, 10);
  }
}

/**
 * تبدیل تاریخ شمسی (Jalali) به فرمت ISO برای ارسال به بک‌اند
 * ورودی: "۱۴۰۴-۰۱-۰۱" یا "1404-01-01"
 * خروجی: "2025-03-21"
 */
export function parseJalaliDate(jalaliStr: string): string {
  // اگر قبلاً میلادی است، همان را برگردان
  if (/^\d{4}-\d{2}-\d{2}$/.test(jalaliStr) && parseInt(jalaliStr) > 1900) {
    return jalaliStr;
  }
  // در غیر این صورت، نیاز به تبدیل دارید
  // اینجا می‌توانید از کتابخانه‌ی moment-jalaali استفاده کنید
  // فعلاً یک پیاده‌سازی ساده: فقط اعداد فارسی را به انگلیسی تبدیل کن و برگردان
  return toEnglishDigits(jalaliStr);
}

/**
 * دریافت وضعیت پرداخت به فارسی
 */
export function getPaymentStatusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: "در انتظار پرداخت",
    partial: "پرداخت ناقص",
    paid: "پرداخت شده",
    cancelled: "لغو شده",
  };
  return map[status] || status;
}

/**
 * دریافت رنگ وضعیت پرداخت
 */
export function getPaymentStatusColor(status: string): {
  bg: string;
  text: string;
} {
  const map: Record<string, { bg: string; text: string }> = {
    pending: { bg: "#FDEAED", text: "#C71F3B" },
    partial: { bg: "#FEF6E7", text: "#B5720C" },
    paid: { bg: "#E6F6EF", text: "#178055" },
    cancelled: { bg: "#EDF1F6", text: "#6B7888" },
  };
  return map[status] || { bg: "#EDF1F6", text: "#6B7888" };
}

/**
 * دریافت وضعیت عمل به فارسی
 */
export function getSurgeryStatusLabel(status: string): string {
  const map: Record<string, string> = {
    PLANNED: "برنامه‌ریزی شده",
    IN_PROGRESS: "در حال انجام",
    COMPLETED: "انجام شده",
    CANCELLED: "لغو شده",
  };
  return map[status] || status;
}

/**
 * دریافت وضعیت خرید به فارسی
 */
export function getPurchaseStatusLabel(status: string): string {
  const map: Record<string, string> = {
    PENDING: "در انتظار تأیید",
    CONFIRMED: "تأیید شده",
    CANCELLED: "لغو شده",
  };
  return map[status] || status;
}