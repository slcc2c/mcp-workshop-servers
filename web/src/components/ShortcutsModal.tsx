import { Keyboard, X } from "lucide-react";

const SHORTCUT_GROUPS: Array<{
  title: string;
  items: Array<{ keys: string[]; desc: string }>;
}> = [
  {
    title: "Global",
    items: [
      { keys: ["⌘", "K"], desc: "Open Quick Jump palette (Presets, Tools, Prompts, Servers)" },
      { keys: ["/"], desc: "Focus search filter in current view" },
      { keys: ["?"], desc: "Toggle this keyboard shortcuts reference" },
      { keys: ["Esc"], desc: "Close active palette, modal, or trace drawer" },
    ],
  },
  {
    title: "Navigation (press g then key)",
    items: [
      { keys: ["g", "o"], desc: "Overview" },
      { keys: ["g", "p"], desc: "Playground & Agent" },
      { keys: ["g", "t"], desc: "Traces" },
      { keys: ["g", "e"], desc: "Evals & Datasets" },
      { keys: ["g", "r"], desc: "Registry & Skills" },
      { keys: ["g", "u"], desc: "Upstreams & Profiles" },
      { keys: ["g", "c"], desc: "Clients" },
      { keys: ["g", "l"], desc: "Toggle Live Activity drawer" },
    ],
  },
  {
    title: "Playground & Traces",
    items: [
      { keys: ["⌘", "Enter"], desc: "Run active tool in Playground" },
      { keys: ["j"], desc: "Inspect next trace (while Trace Drawer is open)" },
      { keys: ["k"], desc: "Inspect previous trace (while Trace Drawer is open)" },
    ],
  },
];

export function ShortcutsModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label="Keyboard shortcuts"
        className="w-full max-w-lg rounded-xl border border-[var(--border-strong)] bg-[var(--bg-surface)] shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-4 py-3 border-b border-[var(--border-hairline)] flex items-center justify-between">
          <div className="flex items-center gap-2 font-semibold text-[13.5px]">
            <Keyboard className="w-4 h-4 text-[var(--accent)]" />
            Keyboard Shortcuts
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close shortcuts"
            className="p-1 rounded-md text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)] cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-4 space-y-4 max-h-[75vh] overflow-y-auto">
          {SHORTCUT_GROUPS.map((grp) => (
            <div key={grp.title} className="space-y-2">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                {grp.title}
              </div>
              <div className="divide-y divide-[var(--border-hairline)] rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-subtle)]">
                {grp.items.map((item) => (
                  <div
                    key={item.desc}
                    className="px-3 py-2 flex items-center justify-between gap-3 text-[12.5px]"
                  >
                    <span className="text-[var(--text-secondary)]">{item.desc}</span>
                    <span className="inline-flex items-center gap-1 shrink-0">
                      {item.keys.map((k, idx) => (
                        <kbd
                          key={`${k}-${idx}`}
                          className="px-1.5 py-0.5 rounded border border-[var(--border-strong)] bg-[var(--bg-surface)] font-mono text-[11px] text-[var(--text-primary)]"
                        >
                          {k}
                        </kbd>
                      ))}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
