export function toPersianDigits(n: string | number): string {
  return String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
}

export function formatCurrency(num: number | null | undefined): string {
  if (num === null || num === undefined) return "—";
  const abs = Math.abs(num);
  const formatted = abs.toLocaleString("en-US", { maximumFractionDigits: 0 });
  const persian = toPersianDigits(formatted);
  return num < 0 ? persian + "−" : persian;
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  return toPersianDigits(dateStr.slice(0, 10));
}
