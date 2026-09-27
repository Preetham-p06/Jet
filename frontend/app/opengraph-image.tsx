import { ImageResponse } from "next/og";

export const alt = "JetStream AI — Quote Intelligence for Private Aviation";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 72,
          background:
            "radial-gradient(90% 70% at 20% 0%, #14213a 0%, #080b10 55%, #05070a 100%)",
          color: "#F5F7FA",
          fontFamily: "sans-serif",
          position: "relative",
        }}
      >
        {/* glow */}
        <div
          style={{
            position: "absolute",
            right: -120,
            top: -160,
            width: 620,
            height: 620,
            borderRadius: 9999,
            background:
              "radial-gradient(circle, rgba(89,217,255,0.22) 0%, rgba(91,140,255,0.10) 40%, rgba(0,0,0,0) 70%)",
          }}
        />
        {/* flight path */}
        <svg
          width="1200"
          height="630"
          viewBox="0 0 1200 630"
          style={{ position: "absolute", left: 0, top: 0 }}
        >
          <path
            d="M-20 520 C 300 520, 520 180, 1240 140"
            stroke="url(#og)"
            strokeWidth="2"
            fill="none"
            opacity="0.7"
          />
          <path
            d="M-20 570 C 340 570, 560 260, 1240 220"
            stroke="url(#og)"
            strokeWidth="1"
            fill="none"
            opacity="0.3"
          />
          <defs>
            <linearGradient id="og" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stopColor="#5B8CFF" stopOpacity="0" />
              <stop offset="0.5" stopColor="#59D9FF" />
              <stop offset="1" stopColor="#DDF8FF" stopOpacity="0.4" />
            </linearGradient>
          </defs>
        </svg>

        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <svg width="44" height="44" viewBox="0 0 24 24" fill="none">
            <path d="M3 18C9.5 18 11 7 21 6" stroke="#59D9FF" strokeWidth="2.2" strokeLinecap="round" />
            <path d="M3 13.6C6.6 13.6 8 10.6 10.6 9.6" stroke="#5B8CFF" strokeWidth="1.6" strokeLinecap="round" opacity="0.6" />
            <circle cx="21" cy="6" r="1.7" fill="#DDF8FF" />
          </svg>
          <div style={{ fontSize: 30, fontWeight: 600, letterSpacing: -0.5 }}>JetStream</div>
          <div
            style={{
              fontSize: 14,
              letterSpacing: 3,
              color: "#9AA6B2",
              border: "1px solid rgba(255,255,255,0.14)",
              borderRadius: 8,
              padding: "4px 8px",
            }}
          >
            AI
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 22, maxWidth: 900 }}>
          <div style={{ fontSize: 16, letterSpacing: 5, color: "#9AA6B2" }}>
            PRIVATE AVIATION · AI QUOTE INTELLIGENCE
          </div>
          <div style={{ fontSize: 72, fontWeight: 600, lineHeight: 1.04, letterSpacing: -2.5 }}>
            Turn every charter quote into a clear decision.
          </div>
          <div style={{ fontSize: 26, color: "#9AA6B2", lineHeight: 1.4 }}>
            Operator PDFs, emails and messages — extracted, normalized, verified and compared.
          </div>
        </div>
      </div>
    ),
    { ...size },
  );
}
