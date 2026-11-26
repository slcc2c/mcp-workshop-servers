import { useState } from "react";
import { Check, Copy } from "lucide-react";

export function CopyButton({
  text,
  label = "Copy",
  compact = false,
}: {
  text: string;
  label?: string;
  compact?: boolean;
}) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      // Clipboard blocked in non-HTTPS test contexts
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      title={`Copy ${label}`}
      className={`inline-flex items-center gap-1.5 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:border-[var(--border-strong)] hover:bg-[var(--bg-hover)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors cursor-pointer whitespace-nowrap shrink-0 ${
        compact ? "px-2 py-1 text-[11px]" : "px-2.5 py-1.5 text-[12px]"
      }`}
    >
      {copied ? <Check className="w-3.5 h-3.5 text-[var(--ok)]" /> : <Copy className="w-3.5 h-3.5" />}
      <span>{copied ? "Copied" : label}</span>
    </button>
  );
}
