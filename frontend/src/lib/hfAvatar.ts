// HF returns default avatars as site-relative paths and uploads as CDN URLs.
export const hfAvatarSrc = (url: string) =>
  url.startsWith("/") ? `https://huggingface.co${url}` : url;
