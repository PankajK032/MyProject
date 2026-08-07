/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'export',            // static HTML/CSS/JS only - no Node.js server needed
  basePath: '/MyProject',      // GitHub Pages project sites are served from a subpath
  images: { unoptimized: true }, // Next.js image optimization needs a server; static export can't do it
};

module.exports = nextConfig;
