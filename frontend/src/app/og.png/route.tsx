import { ImageResponse } from "next/og";

export const dynamic = "force-static";

/** The picture of a shared link. */
export function GET() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: 90,
          background: "#0b1220",
          color: "white",
        }}
      >
        <div style={{ display: "flex", fontSize: 40, color: "#7cb4f0" }}>whileisleep</div>
        <div style={{ display: "flex", marginTop: 28, fontSize: 104, letterSpacing: -3 }}>AI answers.</div>
        <div style={{ display: "flex", fontSize: 104, letterSpacing: -3, color: "#7cb4f0" }}>While you sleep.</div>
        <div style={{ display: "flex", marginTop: 36, fontSize: 36, color: "#b6c2d4" }}>Open-source customer chat with an AI agent</div>
      </div>
    ),
    { width: 1200, height: 630 },
  );
}
