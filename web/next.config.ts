import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit .next/standalone (server.js + only the needed node_modules) for a small Docker image
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
