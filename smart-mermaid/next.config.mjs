/** @type {import('next').NextConfig} */
const nextConfig = {
  // 这一步是关键：告诉 Next.js，凡是 /api 开头的请求，都转发给 Python
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://127.0.0.1:8000/api/:path*', 
      },
    ];
  },
  // 保持原有配置（如果有的话），通常不需要动
  reactStrictMode: false, 
};

export default nextConfig;