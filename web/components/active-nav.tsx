"use client";

import { usePathname } from "next/navigation";

import { NavList } from "@/components/nav";

export function ActiveNav() {
  return <NavList activePath={usePathname()} />;
}
