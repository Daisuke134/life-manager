import { Composition } from "remotion";
import { LifeManagerCalendar } from "./LifeManagerCalendar";

// Silent-first 9:16 product demo: one Calendar connection, then an automatic Travel block.
export const RemotionRoot: React.FC = () => (
  <Composition
    id="LifeManagerCalendar"
    component={LifeManagerCalendar}
    durationInFrames={30 * 15}
    fps={30}
    width={1080}
    height={1920}
  />
);
