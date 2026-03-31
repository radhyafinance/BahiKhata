import { ChevronLeft, ChevronRight } from "lucide-react";
import { MONTHS } from "./utils";

export function MonthNav({ month, onChange }) {
  const [y, m] = month.split("-").map(Number);
  const prev = () => {
    const d = new Date(y, m - 2, 1);
    onChange(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  };
  const next = () => {
    const d = new Date(y, m, 1);
    onChange(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  };
  return (
    <div className="flex items-center gap-2">
      <button onClick={prev} className="p-1.5 rounded-lg hover:bg-muted transition-colors">
        <ChevronLeft size={16} />
      </button>
      <span className="text-sm font-bold min-w-[90px] text-center">
        {MONTHS[m - 1]} {y}
      </span>
      <button onClick={next} className="p-1.5 rounded-lg hover:bg-muted transition-colors">
        <ChevronRight size={16} />
      </button>
    </div>
  );
}
