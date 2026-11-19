"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  ["/", "概览与快速入口"],
  ["/workbench", "签名逆转工作台"],
  ["/pathway-tf", "通路 / TF 寻药"],
  ["/target", "靶基因与遗传印证"],
  ["/cases", "肾病经典案例"],
  ["/downloads", "下载中心"],
  ["/docs", "API / MCP 文档"],
];

export default function Nav() {
  const path = usePathname();
  const active = (href: string) =>
    href === "/" ? path === "/" : path.startsWith(href);
  return (
    <aside className="sidebar">
      <div className="brand">Nephro<span>Perturb</span></div>
      <div className="tagline">肾脏上下文药物扰动知识库<br />21,299 化合物 · 12,328 基因</div>
      <nav className="nav">
        {LINKS.map(([href, label]) => (
          <Link key={href} href={href} className={active(href) ? "active" : ""}>
            {label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
