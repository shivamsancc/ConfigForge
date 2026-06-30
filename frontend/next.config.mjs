const isProd = process.env.NODE_ENV === 'production'

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export for production — FastAPI serves frontend/out/ at /
  // In dev the Next.js server (port 3001) proxies /api/* to FastAPI (port 8420)
  output: isProd ? 'export' : undefined,
  trailingSlash: true,

  // rewrites() is incompatible with output:'export', so only used in dev
  ...(isProd
    ? {}
    : {
        async rewrites() {
          return [
            {
              source: '/api/:path*',
              destination: `http://localhost:${process.env.FASTAPI_PORT ?? 8420}/api/:path*`,
            },
          ]
        },
      }),
}

export default nextConfig
