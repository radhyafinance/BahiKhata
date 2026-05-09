export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * Parse CRIF COMBINED-PAYMENT-HISTORY string → { year: { monthIdx: dpd } }
 * Format: "Jan:2025,000|Dec:2024,000|Nov:2024,XXX|..."
 * IOI/CNS variant: "Apr:2026,011/XXX|..."  (DPD/asset-classification — keep DPD only)
 */
export function parsePaymentHistory(raw) {
  if (!raw || typeof raw !== "string") return {};
  const grid = {};
  raw.split("|").forEach((entry) => {
    const trimmed = entry.trim();
    if (!trimmed) return;
    const [monYear, dpdRaw] = trimmed.split(",");
    if (!monYear) return;
    const [mon, year] = monYear.split(":");
    const mi = MONTHS.indexOf((mon || "").slice(0, 3));
    if (mi === -1 || !year) return;
    // CNS variant: "DPD/CLASSIFICATION" — take DPD part only
    let dpd = (dpdRaw ?? "").trim();
    if (dpd.includes("/")) dpd = dpd.split("/")[0].trim();
    if (!grid[year]) grid[year] = {};
    grid[year][mi] = dpd;
  });
  return grid;
}

/** Map DPD value → Tailwind cell classes (matches CRIF report colour scheme) */
export function dpdCellStyle(dpd) {
  if (dpd === undefined || dpd === null || dpd === "" || dpd === "-") {
    return "bg-muted/30 text-muted-foreground";
  }
  const upper = String(dpd).toUpperCase();
  if (upper === "XXX") return "bg-gray-100 text-gray-400";
  const n = parseInt(dpd, 10);
  if (Number.isNaN(n)) return "bg-muted/30 text-muted-foreground";
  if (n === 0)   return "bg-emerald-50 text-emerald-700";
  if (n <= 29)   return "bg-yellow-100 text-yellow-800 font-semibold";
  if (n <= 59)   return "bg-orange-200 text-orange-900 font-semibold";
  if (n <= 89)   return "bg-orange-400 text-white font-bold";
  return "bg-red-500 text-white font-bold";
}
