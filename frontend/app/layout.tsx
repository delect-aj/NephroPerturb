import type { Metadata } from "next";
import "./globals.css";
import Nav from "@/components/Nav";
import AgentDrawer from "@/components/AgentDrawer";

export const metadata: Metadata = {
  title: "NephroPerturb",
  description: "Kidney-context drug perturbation knowledge base with nephrotoxicity guardrails",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <div className="shell">
          <Nav />
          <main className="main">{children}</main>
        </div>
        <AgentDrawer />
      </body>
    </html>
  );
}
