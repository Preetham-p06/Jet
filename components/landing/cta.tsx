import { ArrowRight, Check, AlertTriangle, FileCheck } from "lucide-react";
import { GlowButton } from "@/components/ui/glow-button";
import { Reveal } from "@/components/ui/reveal";
import { FlightDefs, FlightPath } from "@/components/ui/flight-path";
import { CONTACT_HREF } from "@/lib/demo-data";

const PATHS = [
  "M-40 420 C 260 420, 480 140, 1240 110",
  "M-40 500 C 320 500, 560 240, 1240 200",
  "M-40 330 C 200 330, 420 60, 1240 30",
];

const POINTS = [
  [8, 22],
  [18, 68],
  [31, 14],
  [46, 80],
  [63, 20],
  [78, 72],
  [91, 34],
];

const FRAGMENTS = [
  { icon: Check, text: "Confidence 97%", tone: "text-green", pos: "left-[7%] top-[24%]", float: "animate-float-a" },
  { icon: AlertTriangle, text: "Positioning $1,200 detected", tone: "text-amber", pos: "right-[8%] top-[30%]", float: "animate-float-b" },
  { icon: FileCheck, text: "Proposal ready", tone: "text-cyan", pos: "left-[14%] bottom-[22%]", float: "animate-float-c" },
];

export function Cta() {
  return (
    <section id="cta" className="relative overflow-hidden py-32 sm:py-44">
      {/* glow */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute left-1/2 top-1/2 h-[640px] w-[1200px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(ellipse_at_center,rgba(91,140,255,0.26)_0%,rgba(89,217,255,0.1)_35%,transparent_68%)] blur-3xl"
      />

      {/* flight paths */}
      <svg
        viewBox="0 0 1200 560"
        preserveAspectRatio="xMidYMid slice"
        className="pointer-events-none absolute inset-0 h-full w-full opacity-40"
        aria-hidden="true"
      >
        <FlightDefs id="cta" />
        {PATHS.map((d, i) => (
          <FlightPath key={i} d={d} defsId="cta" strokeWidth={1} glow={false} dots={1} dotDuration={11 + i * 3} delay={i * 0.3} />
        ))}
      </svg>

      {/* sparse telemetry points */}
      {POINTS.map(([x, y], i) => (
        <span
          key={i}
          aria-hidden="true"
          className="pointer-events-none absolute h-1 w-1 rounded-full bg-ice/70 shadow-[0_0_8px_rgba(221,248,255,0.8)]"
          style={{ left: `${x}%`, top: `${y}%`, opacity: 0.35 + (i % 3) * 0.2 }}
        />
      ))}

      {/* floating UI fragments */}
      {FRAGMENTS.map((f) => {
        const Icon = f.icon;
        return (
          <span
            key={f.text}
            aria-hidden="true"
            className={`glass pointer-events-none absolute hidden items-center gap-2 rounded-full px-3 py-1.5 font-mono text-[10.5px] text-fg-muted shadow-card lg:inline-flex ${f.pos} ${f.float} motion-reduce:animate-none`}
          >
            <Icon className={`h-3 w-3 ${f.tone}`} />
            {f.text}
          </span>
        );
      })}

      <Reveal className="container-x relative flex flex-col items-center text-center">
        <p className="eyebrow">Early access</p>
        <h2 className="mt-5 max-w-[16ch] text-[2.4rem] font-semibold leading-[1.04] tracking-[-0.04em] text-gradient-ice sm:text-[3.4rem] lg:text-[4rem]">
          Turn the next 20 operator replies into one decision.
        </h2>
        <p className="mt-6 max-w-xl text-base text-fg-muted sm:text-lg">
          Spend less time assembling quotes. Spend more time closing trips.
        </p>
        <div className="mt-9">
          <GlowButton size="lg" href={CONTACT_HREF} icon={<ArrowRight className="h-4 w-4" />}>
            Request early access
          </GlowButton>
        </div>
        <p className="mt-5 font-mono text-[11px] tracking-[0.14em] text-fg-dim">
          PILOT PARTNERS COMING SOON · NO OPERATOR PORTAL REQUIRED
        </p>
      </Reveal>
    </section>
  );
}
