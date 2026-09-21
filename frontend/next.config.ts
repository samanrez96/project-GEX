import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        // Trailing slash is REQUIRED — Django's URL conf uses it on every endpoint
        // and APPEND_SLASH cannot redirect POST requests.
        destination: "http://localhost:8001/api/:path*/",
      },
    ];
  },
  skipTrailingSlashRedirect: true,
};

export default nextConfig;