import { useEffect, useRef, useState } from "react";
import { DayPicker, type ChevronProps, type Matcher } from "react-day-picker";
import { formatDate } from "../time";

function toDate(day: string): Date {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function toDay(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function Arrow({ orientation, className }: ChevronProps) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden className={className}>
      <path d={orientation === "left" ? "M12.5 5 7.5 10l5 5" : "M7.5 5l5 5-5 5"} />
    </svg>
  );
}

const CLASS_NAMES = {
  root: "text-sm text-gray-900",
  months: "relative",
  month_caption: "flex h-8 items-center px-1",
  caption_label: "text-sm font-medium text-gray-800",
  nav: "absolute right-0 top-0 flex gap-1",
  button_previous: "inline-flex h-8 w-8 items-center justify-center rounded text-gray-500 hover:bg-gray-100 hover:text-gray-900 aria-disabled:opacity-30 aria-disabled:hover:bg-transparent aria-disabled:cursor-default",
  button_next: "inline-flex h-8 w-8 items-center justify-center rounded text-gray-500 hover:bg-gray-100 hover:text-gray-900 aria-disabled:opacity-30 aria-disabled:hover:bg-transparent aria-disabled:cursor-default",
  chevron: "h-4 w-4",
  month_grid: "mt-2 border-collapse",
  weekday: "h-8 w-9 text-xs font-normal text-gray-500",
  day: "p-0 text-center",
  day_button:
    "h-9 w-9 rounded text-sm hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:text-gray-300 disabled:hover:bg-transparent disabled:cursor-not-allowed",
  selected: "[&>button]:bg-brand-600 [&>button]:text-white [&>button:hover]:bg-brand-700",
  today: "[&>button]:font-semibold",
  outside: "[&>button]:text-gray-400",
};

export default function DateField({
  value,
  onChange,
  min,
  max,
  disabled = false,
  label,
}: {
  value: string;
  onChange: (day: string) => void;
  min?: string;
  max?: string;
  disabled?: boolean;
  label: string;
}) {
  const [open, setOpen] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const outside = (e: MouseEvent) => {
      if (!wrapper.current?.contains(e.target as Node)) setOpen(false);
    };
    const escape = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      field.current?.focus();
    };
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  const unavailable: Matcher[] = [];
  if (min) unavailable.push({ before: toDate(min) });
  if (max) unavailable.push({ after: toDate(max) });
  const selected = value ? toDate(value) : undefined;

  return (
    <div ref={wrapper} className="relative">
      <button
        ref={field}
        type="button"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={value ? `${label}, ${formatDate(`${value}T00:00:00Z`)}` : label}
        className="w-full bg-gray-100 border border-gray-300 rounded px-3 py-2 text-sm text-left text-gray-900 focus:outline-none focus:border-brand-500 disabled:text-gray-500 disabled:cursor-not-allowed"
      >
        {/* a no-break space keeps an empty field the same height as a filled one */}
        {value ? formatDate(`${value}T00:00:00Z`) : "\u00a0"}
      </button>

      {open && (
        <div role="dialog" aria-label={label} className="absolute left-0 top-full z-30 mt-1 rounded-lg border border-gray-200 bg-white p-3 shadow-sm">
          <DayPicker
            mode="single"
            selected={selected}
            onSelect={(date) => {
              if (!date) return;
              onChange(toDay(date));
              setOpen(false);
              field.current?.focus();
            }}
            defaultMonth={selected ?? (max ? toDate(max) : undefined)}
            disabled={unavailable}
            startMonth={min ? toDate(min) : undefined}
            endMonth={max ? toDate(max) : undefined}
            showOutsideDays
            autoFocus
            classNames={CLASS_NAMES}
            components={{ Chevron: Arrow }}
          />
        </div>
      )}
    </div>
  );
}
