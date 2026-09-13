// size is its own prop because two Tailwind width classes on one element resolve by stylesheet order, not by which came last
export default function Chevron({ open, size = "w-4 h-4", className = "" }: { open: boolean; size?: string; className?: string }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={`${size} shrink-0 transition-transform duration-200 ${open ? "rotate-180" : ""} ${className}`}
    >
      <path d="M5 7.5 10 12.5 15 7.5" />
    </svg>
  );
}
