"use client";
import { useEffect, useRef, useState } from "react";

export default function Structure({
  smiles,
  width = 360,
  height = 230,
}: {
  smiles?: string | null;
  width?: number;
  height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
    if (!ref.current || !smiles) return;
    ref.current.innerHTML = "";
    let cancelled = false;
    import("smiles-drawer")
      .then((mod: any) => {
        if (cancelled || !ref.current) return;
        const SD = mod.default || mod;
        const drawer = new SD.SvgDrawer({ width, height, bondThickness: 1.2, padding: 14 });
        SD.parse(
          smiles,
          (tree: any) => {
            if (!cancelled && ref.current) drawer.draw(tree, ref.current, "light", false);
          },
          () => {
            if (!cancelled) setFailed(true);
          }
        );
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [smiles, width, height]);

  if (!smiles) return <div className="muted small">No structure available</div>;
  if (failed) return <div className="muted small">Unable to render 2D structure</div>;
  return (
    <div
      ref={ref}
      style={{
        width,
        maxWidth: "100%",
        background: "#ffffff",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: 6,
      }}
    />
  );
}
