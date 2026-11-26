import { tokenizePromptTemplate } from "../lib/format";
import { CopyButton } from "./CopyButton";

export function PromptRenderer({
  template,
  title,
  version,
  commitMessage,
}: {
  template: string;
  title?: string;
  version?: string | number | null;
  commitMessage?: string | null;
}) {
  const tokens = tokenizePromptTemplate(template);

  return (
    <div className="space-y-3">
      {(title || commitMessage) && (
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="min-w-0">
            {title && (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono font-semibold text-[13.5px] text-[var(--text-primary)]">
                  {title}
                </span>
                {version !== undefined && version !== null && (
                  <span className="px-2 py-0.5 rounded-md text-[11px] font-mono font-medium bg-[var(--accent-soft)] text-[var(--accent)]">
                    v{String(version)}
                  </span>
                )}
              </div>
            )}
            {commitMessage && (
              <p className="text-[12px] text-[var(--text-secondary)] mt-1 whitespace-pre-wrap">
                {commitMessage}
              </p>
            )}
          </div>
          <CopyButton text={template} label="Copy template" compact />
        </div>
      )}

      <div
        data-testid="prompt-rendered-body"
        className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] p-4 font-mono text-[12.5px] leading-relaxed text-[var(--text-primary)] whitespace-pre-wrap break-words"
      >
        {tokens.map((tok, idx) =>
          tok.type === "variable" ? (
            <span
              key={idx}
              className="inline-block px-1.5 py-0.5 mx-0.5 rounded bg-[var(--accent-soft)] text-[var(--accent)] border border-[color-mix(in_srgb,var(--accent)_30%,transparent)] font-semibold"
            >
              {tok.value}
            </span>
          ) : (
            <span key={idx}>{tok.value}</span>
          ),
        )}
      </div>
    </div>
  );
}
