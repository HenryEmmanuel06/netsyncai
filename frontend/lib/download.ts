"use client";

import { useEffect, useState } from "react";

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

const WIN_ASSET = "netsync-agent.exe";
const MAC_ASSET = "netsync-agent-macos";

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

function repoFrom(url: string): string | null {
  const m = url.match(/github\.com\/([^/]+\/[^/]+)\/releases\//);
  return m ? m[1] : null;
}

/** Resolved download URL for this visitor's OS.
 *
 * Probes the latest release's asset list first. If the OS binary isn't on
 * the release yet (e.g. a not-yet-built macOS asset), the button downloads
 * the source bundle of that release instead of landing on a 404 or a bare
 * release page — `python3 main.py` runs it, no build step needed.
 */
export function useAgentDownload(): { url: string; label: string; note?: string } {
  const fallback = agentDownload();
  const [resolved, setResolved] = useState<{ url: string; note?: string }>({
    url: fallback.url,
  });
  useEffect(() => {
    const repo = repoFrom(WIN_URL);
    if (!repo) return;
    const want = isMac() ? MAC_ASSET : WIN_ASSET;
    let alive = true;
    fetch(`https://api.github.com/repos/${repo}/releases/latest`)
      .then((r) => (r.ok ? r.json() : null))
      .then((rel) => {
        if (!alive || !rel) return;
        const assets: { name?: string; browser_download_url?: string }[] =
          rel.assets ?? [];
        const hit = assets.find((a) => a.name === want
          || (isMac() && a.name?.startsWith(MAC_ASSET)));
        if (hit?.browser_download_url) {
          setResolved({
            url: hit.browser_download_url,
            note: isMac()
              ? "Unzip the download, then right-click → Open “NetSync Agent.command” " +
                "(Gatekeeper asks once — the app isn't signed yet). First run unpacks " +
                "its bundled Python and installs components — needs internet once, then " +
                "the NetSync window opens and stays connected while it runs."
              : undefined,
          });
        } else if (isMac() && rel.tag_name) {
          setResolved({
            url: `https://github.com/${repo}/archive/refs/tags/${rel.tag_name}.zip`,
            note: "No packaged macOS app yet — this downloads the source. " +
                  "Unzip it, open Terminal inside the folder, then run:\n" +
                  "cd desktop_agent && pip install -r requirements.txt\n" +
                  "python3 main.py pair <your-code>   then   python3 main.py run",
          });
        } else {
          setResolved({ url: rel.html_url ?? fallback.url });
        }
      })
      .catch(() => {});
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return { url: resolved.url, label: fallback.label, note: resolved.note };
}
