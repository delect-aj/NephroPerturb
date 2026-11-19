/** @type {import('next').NextConfig} */
const API_BASE = process.env.API_BASE || "http://127.0.0.1:8091";

module.exports = {

  reactStrictMode: false,
  async rewrites() {
    return [
      { source: "/health", destination: `${API_BASE}/health` },
      { source: "/api/:path*", destination: `${API_BASE}/api/:path*` },
      { source: "/downloads/:path*", destination: `${API_BASE}/downloads/:path*` },
    ];
  },
};
