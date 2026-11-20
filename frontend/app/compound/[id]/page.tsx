import CompoundView from "@/components/CompoundView";

export function generateStaticParams() {
  return [{ id: "_" }];
}

export default function CompoundDetailPage({ params }: { params: { id: string } }) {
  const id = decodeURIComponent(String(params?.id || ""));
  return <CompoundView id={id === "_" ? "" : id} />;
}
