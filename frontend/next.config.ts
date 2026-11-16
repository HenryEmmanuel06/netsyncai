import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Cloud backend URL is env-driven; never hardcoded.
  reactStrictMode: true,
};

export default nextConfig;
