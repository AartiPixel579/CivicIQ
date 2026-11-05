/**
 * Safely resolves an API, asset, or PDF download URL against the configured backend.
 * If the URL is already absolute (http:// or https://), returns it as-is.
 * If the URL is relative (/api/...) and NEXT_PUBLIC_API_URL is set,
 * it prepends the sanitized backend URL so Vercel deployments connect directly to the backend.
 */
export const resolveBackendUrl = (url) => {
  if (!url || typeof url !== 'string') return '';
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return url;
  }
  const rawApiBase = process.env.NEXT_PUBLIC_API_URL || '';
  const cleanApiBase = rawApiBase.replace(/\/+$/, '');
  if (cleanApiBase && url.startsWith('/')) {
    return `${cleanApiBase}${url}`;
  }
  return url;
};
