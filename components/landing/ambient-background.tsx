/**
 * Fixed atmospheric layer: slow-drifting blurred gradient fields, a faint
 * technical grid under the hero, a vignette and a whisper of grain.
 * Pure CSS; transforms only; loops disabled under reduced motion.
 */
export function AmbientBackground() {
  return (
    <div aria-hidden="true" className="noise pointer-events-none fixed inset-0 z-0 overflow-hidden">
      {/* base gradient wash */}
      <div className="absolute inset-0 bg-[radial-gradient(120%_80%_at_50%_-10%,#0e1624_0%,#080b10_55%,#05070a_100%)]" />

      {/* drifting fields */}
      <div className="absolute -left-[10%] -top-[20%] h-[70vh] w-[70vw] rounded-full bg-[radial-gradient(circle,rgba(91,140,255,0.16)_0%,rgba(91,140,255,0)_60%)] blur-3xl animate-drift-a motion-reduce:animate-none" />
      <div className="absolute -right-[15%] top-[5%] h-[60vh] w-[55vw] rounded-full bg-[radial-gradient(circle,rgba(89,217,255,0.10)_0%,rgba(89,217,255,0)_60%)] blur-3xl animate-drift-b motion-reduce:animate-none" />
      <div className="absolute left-[20%] top-[55%] h-[50vh] w-[60vw] rounded-full bg-[radial-gradient(circle,rgba(91,140,255,0.08)_0%,rgba(91,140,255,0)_60%)] blur-3xl animate-drift-c motion-reduce:animate-none" />

      {/* technical grid, masked to the top of the page */}
      <div className="grid-fade absolute inset-x-0 top-0 h-[140vh]" />

      {/* vignette */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_55%,rgba(5,7,10,0.6)_100%)]" />
    </div>
  );
}
