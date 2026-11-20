"use client";
import { useEffect, useState } from "react";
import CompoundView from "@/components/CompoundView";

export default function CompoundIndexPage() {
  const [id, setId] = useState("");
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("id") || "";
    setId(q);
  }, []);
  return <CompoundView id={id} />;
}
