import TargetView from "@/components/TargetView";

export function generateStaticParams() {
  return [{ symbol: "_" }];
}

export default function TargetDetailPage({ params }: { params: { symbol: string } }) {
  const sym = decodeURIComponent(String(params?.symbol || ""));
  return sym && sym !== "_" ? <TargetView symbol={sym} /> : null;
}
