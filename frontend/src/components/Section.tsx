import { useState, type ReactNode } from "react";
import Chevron from "./Chevron";

// keep the title style in step with FormSection in CreateWorkflowPage
export default function Section({
  title,
  defaultOpen = true,
  bodyClassName = "px-5 pb-5",
  className = "mb-4",
  children,
}: {
  title: ReactNode;
  defaultOpen?: boolean;
  // padding for the content; a full-bleed map passes "" and pads its own controls
  bodyClassName?: string;
  className?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className={`${className} bg-white border border-gray-200 rounded-lg overflow-hidden`}>
      <h2>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="w-full px-5 py-4 flex items-center justify-between text-left text-sm font-medium text-gray-800 hover:bg-gray-50 transition-colors"
        >
          {title}
          <Chevron open={open} className="text-gray-500" />
        </button>
      </h2>
      {open && <div className={bodyClassName}>{children}</div>}
    </section>
  );
}
