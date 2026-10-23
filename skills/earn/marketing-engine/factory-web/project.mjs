// Shared by the public draft workspace and the local execution boundary.
const limits = { project_id: 64, language: 2, avatar_id: 128, voice_id: 128, platform: 9,
  integration_id: 128, native_handle: 64, product_name: 200, product_url: 2048, brief: 4000, script: 5000, cta: 500 };

export function validateProject(value, { ready = false } = {}) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
    || Object.keys(value).length !== Object.keys(limits).length
    || Object.keys(value).some(key => !Object.hasOwn(limits, key))) throw new Error('Project fields are invalid.');
  const result = {};
  for (const [key, max] of Object.entries(limits)) {
    if (typeof value[key] !== 'string' || value[key].length > max || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/u.test(value[key])) {
      throw new Error(`Invalid project field: ${key}`);
    }
    result[key] = value[key].trim();
    if ((key === 'project_id' || key === 'brief' || (ready && key !== 'script')) && !result[key]) throw new Error(`Required project field: ${key}`);
  }
  if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(result.project_id)) throw new Error('Invalid project ID.');
  if (!['en', 'ja'].includes(result.language) || !['tiktok', 'instagram'].includes(result.platform)) throw new Error('Invalid language or platform.');
  for (const key of ['avatar_id', 'voice_id']) {
    if (result[key] && !/^[A-Za-z0-9_-]{8,128}$/.test(result[key])) throw new Error(`Invalid project field: ${key}`);
  }
  if (result.integration_id && /\s/u.test(result.integration_id)) throw new Error('Invalid integration ID.');
  if (result.native_handle && !/^[A-Za-z0-9_][A-Za-z0-9._]{0,63}$/.test(result.native_handle)) throw new Error('Invalid native handle.');
  if (result.product_url) {
    let url;
    try { url = new URL(result.product_url); } catch { throw new Error('Invalid product URL.'); }
    if (url.protocol !== 'https:' || !url.hostname || url.username || url.password || /[\s\\]/u.test(result.product_url)) throw new Error('Invalid product URL.');
  }
  return result;
}
