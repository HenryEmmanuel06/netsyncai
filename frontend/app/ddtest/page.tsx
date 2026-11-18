"use client";

import { useState } from "react";
import { Dropdown } from "@/components/ui";

export default function DDTest() {
  const [v, setV] = useState("");
  return (
    <div className="mx-auto max-w-md p-10">
      <div className="pop-in relative overflow-hidden rounded-2xl bg-gradient-to-r from-[rgba(139,92,246,0.55)] to-[rgba(255,154,61,0.45)] p-px">
        <div className="rounded-[15px] bg-[var(--color-surface)] p-4">
          <Dropdown className="w-48 text-xs" value={v}
            placeholder="Your computer…"
            onChange={setV}
            options={[
              { value: "a", label: "Henry PC", hint: "online" },
              { value: "b", label: "Other", hint: "offline" },
            ]} />
        </div>
      </div>
      <div className="mt-4 text-xs text-white">value: {v}</div>
    </div>
  );
}
