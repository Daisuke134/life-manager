import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

// Travel-first product demo. All Calendar content is synthetic; no customer schedule or location is embedded.
const INK = "#08111F";
const PANEL = "#101B2A";
const LINE = "#263448";
const FG = "#F3F6FB";
const MUTED = "#A3B2C5";
const BLUE = "#66A8FF";
const GREEN = "#57D99A";

const Phone: React.FC<{ children: React.ReactNode; lift: number }> = ({ children, lift }) => (
  <div
    style={{
      width: 840,
      height: 1060,
      borderRadius: 72,
      background: "linear-gradient(155deg,#172538 0%,#09121E 72%)",
      border: "3px solid #324157",
      boxShadow: "0 48px 130px rgba(0,0,0,.55)",
      transform: `translateY(${lift}px)`,
      overflow: "hidden",
      position: "relative",
      padding: "38px 40px",
      boxSizing: "border-box",
    }}
  >
    {children}
  </div>
);

const CalendarEvent: React.FC<{ time: string; title: string; place: string }> = ({ time, title, place }) => (
  <div style={{ display: "flex", gap: 22, marginBottom: 22 }}>
    <div style={{ width: 92, color: MUTED, fontSize: 29, paddingTop: 18 }}>{time}</div>
    <div style={{ flex: 1, background: "#18345A", border: "1px solid #315A8A", borderRadius: 24, padding: "22px 26px" }}>
      <div style={{ color: FG, fontSize: 34, fontWeight: 700 }}>{title}</div>
      <div style={{ color: "#B9D7FF", fontSize: 26, marginTop: 8 }}>{place}</div>
    </div>
  </div>
);

const TravelBlock: React.FC<{ progress: number }> = ({ progress }) => (
  <div
    style={{
      display: "flex",
      gap: 22,
      margin: "10px 0 22px",
      opacity: progress,
      transform: `translateY(${interpolate(progress, [0, 1], [42, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })}px)`,
    }}
  >
    <div style={{ width: 92, color: GREEN, fontSize: 29, paddingTop: 18 }}>14:15</div>
    <div style={{ flex: 1, background: "#123629", border: "2px solid #2D8F66", borderRadius: 24, padding: "22px 26px" }}>
      <div style={{ color: GREEN, fontSize: 25, letterSpacing: 2, fontWeight: 800 }}>TRAVEL · ADDED</div>
      <div style={{ color: FG, fontSize: 34, fontWeight: 700, marginTop: 5 }}>Leave for your meeting</div>
      <div style={{ color: "#B9EAD1", fontSize: 27, marginTop: 8 }}>40 min route + 5 min buffer</div>
    </div>
  </div>
);

export const LifeManagerCalendar: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const frameAt = (seconds: number) => Math.round(seconds * fps);
  const lift = spring({ frame, fps, config: { damping: 200 } }) * -8;
  const connected = spring({ frame: frame - frameAt(5.2), fps, config: { damping: 180 } });
  const consent = interpolate(frame, [frameAt(3.5), frameAt(3.75), frameAt(4.95), frameAt(5.2)], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const setupOpacity = (1 - consent) * (1 - connected);
  const tap = interpolate(frame, [frameAt(3.0), frameAt(3.2), frameAt(3.45), frameAt(3.7)], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const buttonPress = interpolate(frame, [frameAt(3.25), frameAt(3.38), frameAt(3.62)], [1, 0.96, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const travel = spring({ frame: frame - frameAt(7.0), fps, config: { damping: 170 } });
  const outro = interpolate(frame, [frameAt(11.5), frameAt(12.4)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const hook = frame < frameAt(5.5)
    ? "15:00 meeting.\n40 minutes away."
    : "The trip is already\nin your Calendar.";

  return (
    <AbsoluteFill style={{ background: INK, color: FG, fontFamily: "Arial, Helvetica, sans-serif", alignItems: "center" }}>
      <div style={{ position: "absolute", top: 88, left: 92, right: 92, textAlign: "center" }}>
        <div style={{ color: BLUE, fontSize: 27, fontWeight: 800, letterSpacing: 6 }}>LIFE MANAGER</div>
        <div style={{ whiteSpace: "pre-line", fontSize: 71, lineHeight: 1.08, fontWeight: 800, marginTop: 28 }}>{hook}</div>
        <div style={{ color: MUTED, fontSize: 31, marginTop: 22 }}>Stop checking Maps to work out when to leave.</div>
      </div>

      <div style={{ position: "absolute", top: 470 }}>
        <Phone lift={lift}>
          <div style={{ display: "flex", justifyContent: "space-between", color: MUTED, fontSize: 24, marginBottom: 42 }}>
            <span>09:41</span><span>{frame < frameAt(3.5) ? "aniccaai.com/lm" : frame < frameAt(5.2) ? "Google" : "Calendar"}</span><span>●●●</span>
          </div>
          <div style={{ opacity: connected }}>
            <div style={{ fontSize: 34, color: MUTED, marginBottom: 10 }}>WEDNESDAY · OCT 7</div>
            <div style={{ fontSize: 49, fontWeight: 800, marginBottom: 28 }}>Your schedule</div>
            <CalendarEvent time="13:00" title="Previous meeting" place="Roppongi · ends 14:00" />
            <div style={{ display: "flex", alignItems: "center", gap: 22, margin: "0 0 10px" }}>
              <div style={{ width: 92, color: MUTED, fontSize: 27 }}>15:00</div>
              <div style={{ flex: 1, height: 2, background: LINE }} />
            </div>
            <TravelBlock progress={travel} />
            <CalendarEvent time="15:00" title="Client meeting" place="Shibuya · in person" />
          </div>
          <div
            style={{
              position: "absolute",
              left: 40,
              right: 40,
              top: 92,
              bottom: 38,
              opacity: setupOpacity,
              background: "#0D1826",
              border: "1px solid #31445D",
              borderRadius: 28,
              padding: "46px 34px",
              boxSizing: "border-box",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              textAlign: "center",
              zIndex: 3,
            }}
          >
            <div style={{ color: BLUE, fontSize: 26, fontWeight: 800, letterSpacing: 3 }}>LIFE MANAGER</div>
            <div style={{ color: FG, fontSize: 39, lineHeight: 1.15, fontWeight: 800, marginTop: 30 }}>
              Let your Calendar plan the trip.
            </div>
            <div style={{ color: MUTED, fontSize: 26, lineHeight: 1.35, marginTop: 22 }}>
              Connect once. Your Calendar stays your daily screen.
            </div>
            <div
              style={{
                marginTop: 42,
                width: "100%",
                borderRadius: 22,
                background: BLUE,
                color: INK,
                padding: "25px 16px",
                boxSizing: "border-box",
                fontSize: 29,
                fontWeight: 800,
                transform: `scale(${buttonPress})`,
              }}
            >
              Connect Google Calendar
            </div>
            <div style={{ color: MUTED, fontSize: 22, marginTop: 20 }}>One-time setup · No daily app</div>
            <div
              style={{
                position: "absolute",
                right: 122,
                bottom: 563,
                width: 44,
                height: 44,
                borderRadius: "50%",
                border: "4px solid #FFFFFF",
                boxShadow: "0 0 0 8px rgba(102,168,255,.35)",
                opacity: tap,
                transform: `scale(${interpolate(tap, [0, 1], [1.2, 0.82])})`,
              }}
            />
          </div>
          <div
            style={{
              position: "absolute",
              left: 40,
              right: 40,
              top: 92,
              bottom: 38,
              opacity: consent,
              background: "#0D1826",
              border: "1px solid #31445D",
              borderRadius: 28,
              padding: "46px 34px",
              boxSizing: "border-box",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              textAlign: "center",
              zIndex: 4,
            }}
          >
            <div style={{ width: 76, height: 76, borderRadius: 22, background: "#FFFFFF", color: "#4285F4", fontSize: 52, fontWeight: 800, lineHeight: "76px" }}>G</div>
            <div style={{ color: FG, fontSize: 37, fontWeight: 800, marginTop: 32 }}>Google account</div>
            <div style={{ color: MUTED, fontSize: 25, lineHeight: 1.35, marginTop: 14 }}>Choose your account and allow Calendar access.</div>
            <div style={{ marginTop: 38, width: "100%", borderRadius: 20, background: "#E8F0FE", color: "#174EA6", padding: "23px 16px", boxSizing: "border-box", fontSize: 27, fontWeight: 700 }}>Continue with Google</div>
          </div>
          <div
            style={{
              position: "absolute",
              left: 40,
              right: 40,
              bottom: 38,
              opacity: connected,
              transform: `translateY(${interpolate(connected, [0, 1], [18, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })}px)`,
              background: "#18283A",
              border: "1px solid #31445D",
              borderRadius: 22,
              padding: "18px 22px",
              display: "flex",
              alignItems: "center",
              gap: 16,
              zIndex: 5,
            }}
          >
            <div style={{ width: 28, height: 28, borderRadius: "50%", background: GREEN, color: INK, textAlign: "center", lineHeight: "28px", fontSize: 20, fontWeight: 900 }}>✓</div>
            <div style={{ color: FG, fontSize: 25 }}>Google Calendar connected</div>
          </div>
        </Phone>
      </div>

      <div style={{ position: "absolute", bottom: 105, left: 85, right: 85, textAlign: "center", opacity: outro }}>
        <div style={{ fontSize: 34, fontWeight: 700 }}>Connect Google Calendar</div>
        <div style={{ color: MUTED, fontSize: 28, marginTop: 12 }}>$29/month · No daily app to open</div>
      </div>
    </AbsoluteFill>
  );
};
