"use client";

/** Pick the right agent installer for the visitor's OS.
 *
 * The env URL always points at the Windows exe (GitHub "latest" link); the
 * macOS binary ships alongside it in the same release. Overridable with
 * NEXT_PUBLIC_AGENT_DOWNLOAD_URL_MAC if the asset name ever changes.
 */
const WIN_URL = process.env.NEXT_PUBLIC_AGENT_DOWNLOAD_URL ?? "";
const MAC_URL =
  process.env.NEXT_PUBLIC_AGENT_DOWNLOAD_URL_MAC ??
  WIN_URL.replace(/netsync-agent\.exe$/, "netsync-agent-macos");

export function isMac(): boolean {
  if (typeof navigator === "undefined") return false;
  // iPads masquerade as Macs; both get the macOS build either way
  const s = `${navigator.platform} ${navigator.userAgent}`;
  return /Mac|iPhone|iPad|iPod/i.test(s);
}

export function agentDownload(): { url: string; label: string } {
  if (isMac()) return { url: MAC_URL, label: "Download for macOS" };
  return { url: WIN_URL, label: "Download for Windows" };
}
