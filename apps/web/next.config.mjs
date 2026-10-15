// Artifact URLs are short-lived and may use a dedicated S3-compatible origin.
// Configure this to the exact public origin exposed to the browser.
const artifactOrigin = new URL(process.env.BG_ARTIFACT_PUBLIC_ORIGIN || 'http://localhost:9000').origin;
const mediaSources = "'self' data: blob: " + artifactOrigin;
const headers=[{key:'X-Content-Type-Options',value:'nosniff'},{key:'X-Frame-Options',value:'DENY'},{key:'Referrer-Policy',value:'strict-origin-when-cross-origin'},{key:'Permissions-Policy',value:'camera=(), microphone=(), geolocation=()'},{key:'Content-Security-Policy',value:`default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src ${mediaSources}; media-src ${mediaSources}; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'`}];
export default {output:'standalone',poweredByHeader:false,async rewrites(){return [{source:'/api/:path*',destination:`${process.env.BG_API_INTERNAL_URL||'http://api:8000'}/api/:path*`}];},async headers(){return [{source:'/:path*',headers}];}};
