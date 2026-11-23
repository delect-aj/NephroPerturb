import TargetView from "@/components/TargetView";

export function generateStaticParams() {
  return [{ symbol: "_" }];
}

export default function TargetDetailPage({ params }: { params: { symbol: string } }) {
  const symbol = decodeURIComponent(String(params?.symbol || ""));
  return <TargetView symbol={symbol === "_" ? "" : symbol} />;
}
