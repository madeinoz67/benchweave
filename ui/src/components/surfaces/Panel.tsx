import type { PropsWithChildren } from "react";

import "./Panel.css";

export interface PanelProps extends PropsWithChildren {
  title: string;
  eyebrow?: string;
  recessed?: boolean;
}

export function Panel({ title, eyebrow, recessed = false, children }: PanelProps) {
  return (
    <section
      className="bw-panel"
      data-surface={recessed ? "recessed" : "raised"}
      aria-label={title}
    >
      <header className="bw-panel__header">
        {eyebrow ? <span className="bw-panel__eyebrow">{eyebrow}</span> : null}
        <h2 className="bw-panel__title">{title}</h2>
      </header>
      <div className="bw-panel__body">{children}</div>
    </section>
  );
}
