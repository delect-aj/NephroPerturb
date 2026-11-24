import type { Metadata } from "next";
import "./globals.css";
import Nav from "@/components/Nav";
import AgentDrawer from "@/components/AgentDrawer";
import { AgentProvider } from "@/components/AgentContext";

export const metadata: Metadata = {
  title: "NephroPerturb · Kidney Drug-Perturbation Knowledge Base",
  description:
    "Kidney-context LINCS perturbation knowledge base with NephroSafe nephrotoxicity guardrails and deterministic SOP Agent/MCP orchestration.",
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AgentProvider>
          <div className="shell">
            <Nav />
            <main className="main">
              <AgentDrawer />
              {children}
            </main>
          </div>
        </AgentProvider>
      </body>
    </html>
  );
}
