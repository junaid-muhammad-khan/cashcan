/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Local dev: proxy /face-api/* to a face API running elsewhere (e.g. FACE_API_ORIGIN=http://localhost:8000).
  // In production Vercel routes /face-api/* itself (../vercel.json).
  async rewrites() {
    const origin = process.env.FACE_API_ORIGIN;
    return origin ? [{ source: "/face-api/:path*", destination: `${origin.replace(/\/$/, "")}/:path*` }] : [];
  },
};
export default nextConfig;
