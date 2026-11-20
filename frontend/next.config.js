/** @type {import(next).NextConfig} */
const API_BASE = process.env.API_BASE || "http://127.0.0.1:8091";
const IS_EXPORT = process.env.NEXT_EXPORT === "1";

const config = {
  reactStrictMode: false,
  trailingSlash: true,
  images: { unoptimized: true },
};

if (IS_EXPORT) {
  config.output = "export";
} else {
  config.rewrites = async () => [
    { source: "/health", destination: `${API_BASE}/health` },
    { source: "/api/:path*", destination: `${API_BASE}/api/:path*` },
    { source: "/downloads/:path*", destination: `${API_BASE}/downloads/:path*` },
  ];
}

module.exports = config;
