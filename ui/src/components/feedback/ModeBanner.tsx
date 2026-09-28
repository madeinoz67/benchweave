import "./ModeBanner.css";

/** The contract's mode-banner modes and FIXED wording (§D.1). The `simulated`
 *  string is pinned by existing SDK console, TUI and test output and must not
 *  drift — byte-exact. */
export const MODE_BANNER_MODES = ["simulated", "no-gateway", "no-lease", "no-policy"] as const;

export type ModeBannerMode = (typeof MODE_BANNER_MODES)[number];

export const MODE_BANNER_WORDING: Record<ModeBannerMode, string> = {
  simulated: "SIMULATED PRESENTATION DATA",
  "no-gateway": "NO GATEWAY · LOCAL PRESENTATION ONLY",
  "no-lease": "NO CONTROLLER LEASE · ACTIONS CANNOT BE AUTHORISED",
  "no-policy": "NO POLICY ENGINE · POLICY CHECKS UNAVAILABLE",
};

export interface ModeBannerProps {
  /** Active modes; rendered in the contract's fixed order regardless of input
   *  order. An empty list renders nothing — absence of the banner asserts
   *  full-authority presentation. */
  modes: readonly ModeBannerMode[];
}

/** Contract §D: a persistent, non-dismissible banner, first element of the
 *  page's main region — one entry per active mode, fixed wording, fixed order,
 *  advisory tone. There is no dismiss affordance to remove. */
export function ModeBanner({ modes }: ModeBannerProps) {
  const active = MODE_BANNER_MODES.filter((mode) => modes.includes(mode));
  if (active.length === 0) return null;
  return (
    <section className="bw-mode-banner" data-bw-mode-banner="" role="region" aria-label="Presentation mode">
      {active.map((mode) => (
        <span key={mode} className="bw-mode-banner__entry" data-bw-mode={mode}>
          {MODE_BANNER_WORDING[mode]}
        </span>
      ))}
    </section>
  );
}
