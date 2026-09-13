import { Fragment, type ReactNode } from "react";

export default function DotLine({ parts, className = "" }: { parts: ReactNode[]; className?: string }) {
  const shown = parts.filter((p) => p !== null && p !== undefined && p !== "" && p !== false);
  return (
    <div className={`text-sm text-gray-500 truncate ${className}`}>
      {shown.map((part, i) => (
        <Fragment key={i}>
          {i > 0 && <span className="mx-1.5">·</span>}
          {part}
        </Fragment>
      ))}
    </div>
  );
}
