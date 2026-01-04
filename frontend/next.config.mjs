/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    serverActions: {
      allowedOrigins: process.env.ALLOWED_SERVER_ACTION_ORIGINS?.split(",") ?? [],
    },
  },
};

export default nextConfig;
