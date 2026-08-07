import type { Metadata } from "next";
import { ScoreDashboard } from "./score-dashboard";

export const metadata: Metadata = {
  title: "515450 红利低波评分台",
  description: "基于实时行情、估值与股债利差的双层评分仪表板",
};

export default function Home() {
  return <ScoreDashboard />;
}
