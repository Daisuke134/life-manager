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
      <div style={{ color: GREEN, fontSize: 25, fontWeight: 800 }}>出発リマインダー</div>
      <div style={{ color: FG, fontSize: 34, fontWeight: 700, marginTop: 5 }}>渋谷へ出発</div>
      <div style={{ color: "#B9EAD1", fontSize: 27, marginTop: 8 }}>移動40分 + 5分の余裕</div>
    </div>
  </div>
);

export const LifeManagerCalendar: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const frameAt = (seconds: number) => Math.round(seconds * fps);
  const lift = spring({ frame, fps, config: { damping: 200 } }) * -8;
  const consent = interpolate(
    frame,
    [frameAt(3.35), frameAt(3.6), frameAt(4.85), frameAt(5.1)],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const trialOffer = interpolate(
    frame,
    [frameAt(5.0), frameAt(5.25), frameAt(8.65), frameAt(9.0)],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const calendar = spring({ frame: frame - frameAt(8.85), fps, config: { damping: 180 } });
  const setup = (1 - consent) * (1 - trialOffer) * (1 - calendar);
  const tap = interpolate(
    frame,
    [frameAt(2.8), frameAt(3.05), frameAt(3.25), frameAt(3.5)],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const buttonPress = interpolate(
    frame,
    [frameAt(3.0), frameAt(3.16), frameAt(3.38)],
    [1, 0.96, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const travel = spring({ frame: frame - frameAt(9.45), fps, config: { damping: 170 } });
  const outro = interpolate(
    frame,
    [frameAt(12.3), frameAt(13.0)],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const hook = frame < frameAt(8.5)
    ? "予定のたびに\n地図を開いていませんか？"
    : "移動時間を\nCalendarへ自動追加";
  const subtitle = frame < frameAt(8.5)
    ? "出発時刻の確認と地図検索の手間を減らします。"
    : "対象の予定を、Google Calendarで確認できます。";
  const screenTitle = frame < frameAt(3.35)
    ? "aniccaai.com/lm"
    : frame < frameAt(5.1)
      ? "Google"
      : frame < frameAt(8.85)
        ? "aniccaai.com/lm"
        : "Google Calendar";

  return (
    <AbsoluteFill style={{ background: INK, color: FG, fontFamily: '"Hiragino Sans", "Noto Sans JP", Arial, sans-serif', alignItems: "center" }}>
      <div style={{ position: "absolute", top: 88, left: 92, right: 92, textAlign: "center" }}>
        <div style={{ color: BLUE, fontSize: 27, fontWeight: 800, letterSpacing: 5 }}>LIFE MANAGER</div>
        <div style={{ whiteSpace: "pre-line", fontSize: 62, lineHeight: 1.12, fontWeight: 800, marginTop: 26 }}>{hook}</div>
        <div style={{ color: MUTED, fontSize: 29, marginTop: 18 }}>{subtitle}</div>
      </div>

      <div style={{ position: "absolute", top: 470 }}>
        <Phone lift={lift}>
          <div style={{ display: "flex", justifyContent: "space-between", color: MUTED, fontSize: 24, marginBottom: 42 }}>
            <span>09:41</span><span>{screenTitle}</span><span>●●●</span>
          </div>

          <div style={{ opacity: calendar }}>
            <div style={{ fontSize: 32, color: MUTED, marginBottom: 12 }}>今日の予定</div>
            <div style={{ fontSize: 47, fontWeight: 800, marginBottom: 28 }}>Google Calendar</div>
            <TravelBlock progress={travel} />
            <CalendarEvent time="15:00" title="対面ミーティング" place="渋谷 · 対面" />
          </div>

          <div
            style={{
              position: "absolute",
              left: 40,
              right: 40,
              top: 92,
              bottom: 38,
              opacity: setup,
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
            <div style={{ color: BLUE, fontSize: 25, fontWeight: 800, letterSpacing: 3 }}>LIFE MANAGER</div>
            <div style={{ color: FG, fontSize: 38, lineHeight: 1.2, fontWeight: 800, marginTop: 26 }}>
              出発時刻を調べる手間を、減らそう。
            </div>
            <div style={{ color: MUTED, fontSize: 25, lineHeight: 1.4, marginTop: 20 }}>
              対象の予定に移動時間を自動で追加します。
            </div>
            <div
              style={{
                marginTop: 38,
                width: "100%",
                borderRadius: 22,
                background: BLUE,
                color: INK,
                padding: "25px 16px",
                boxSizing: "border-box",
                fontSize: 29,
                fontWeight: 800,
                transform: "scale(" + buttonPress + ")",
              }}
            >
              Google Calendarに接続
            </div>
            <div style={{ color: MUTED, fontSize: 21, lineHeight: 1.35, marginTop: 18, whiteSpace: "pre-line" }}>
              Googleアカウント確認とCalendar権限の許可が必要です。
              {"\n"}Life ManagerはGmailを読みません。
            </div>
            <div
              style={{
                position: "absolute",
                right: 126,
                bottom: 565,
                width: 44,
                height: 44,
                borderRadius: "50%",
                border: "4px solid #FFFFFF",
                boxShadow: "0 0 0 8px rgba(102,168,255,.35)",
                opacity: tap,
                transform: "scale(" + interpolate(tap, [0, 1], [1.2, 0.82]) + ")",
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
            <div style={{ color: FG, fontSize: 37, fontWeight: 800, marginTop: 28 }}>Googleアカウント</div>
            <div style={{ color: MUTED, fontSize: 24, lineHeight: 1.4, marginTop: 14, whiteSpace: "pre-line" }}>
              アカウントを選択し、
              {"\n"}Calendarへのアクセスを許可します。
            </div>
            <div style={{ marginTop: 34, width: "100%", borderRadius: 20, background: "#E8F0FE", color: "#174EA6", padding: "23px 16px", boxSizing: "border-box", fontSize: 27, fontWeight: 700 }}>
              Calendarへのアクセスを許可
            </div>
          </div>

          <div
            style={{
              position: "absolute",
              left: 40,
              right: 40,
              top: 92,
              bottom: 38,
              opacity: trialOffer,
              background: "#0D1826",
              border: "1px solid #31445D",
              borderRadius: 28,
              padding: "42px 30px",
              boxSizing: "border-box",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              textAlign: "center",
              zIndex: 5,
            }}
          >
            <div style={{ color: GREEN, fontSize: 23, fontWeight: 800 }}>Google Calendarに接続しました</div>
            <div style={{ color: FG, fontSize: 35, lineHeight: 1.18, fontWeight: 800, marginTop: 22, whiteSpace: "pre-line" }}>
              対象の予定に
              {"\n"}移動時間を自動で追加します
            </div>
            <div style={{ color: BLUE, fontSize: 32, fontWeight: 800, marginTop: 30 }}>7日間無料トライアル</div>
            <div style={{ color: MUTED, fontSize: 23, lineHeight: 1.4, marginTop: 16 }}>
              今日のお支払いは$0。開始にはカード登録が必要です。
            </div>
            <div style={{ color: FG, fontSize: 25, fontWeight: 700, marginTop: 12 }}>
              7日後から$29/月。以後、解約まで毎月自動更新。
            </div>
            <div style={{ marginTop: 24, width: "100%", borderRadius: 20, background: BLUE, color: INK, padding: "21px 14px", boxSizing: "border-box", fontSize: 24, lineHeight: 1.25, fontWeight: 800 }}>
              7日間の無料トライアルを始める
            </div>
            <div style={{ color: MUTED, fontSize: 19, marginTop: 14 }}>Stripeでカードを登録</div>
          </div>
        </Phone>
      </div>

      <div style={{ position: "absolute", bottom: 94, left: 85, right: 85, textAlign: "center", opacity: outro }}>
        <div style={{ fontSize: 32, fontWeight: 800 }}>Google Calendarに接続</div>
        <div style={{ color: MUTED, fontSize: 27, marginTop: 12 }}>7日間無料 · 7日後から$29/月</div>
      </div>
    </AbsoluteFill>
  );
};
