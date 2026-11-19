"use client";
import { useEffect, useRef } from "react";

export default function Structure({ smiles, width = 360, height = 230 }: {
  smiles?: string | null; width?: number; height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || !smiles) return;
    ref.current.innerHTML = "";
    let cancelled = false;
    import("smiles-drawer").then((mod: any) => {
      if (cancelled || !ref.current) return;
      const SD = mod.default || mod;
      const drawer = new SD.SvgDrawer({ width, height, bondThickness: 1.1, padding: 12 });
      SD.parse(smiles, (tree: any) => {
        if (!cancelled && ref.current) drawer.draw(tree, ref.current, "light", false);
      });
    });
    return () => { cancelled = true; };
  }, [smiles, width, height]);
  if (!smiles) return <div className="muted small">无可用结构</div>;
  return <div ref={ref} style={{ width, maxWidth: "100%" }} />;
}
