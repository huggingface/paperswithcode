import React, { useState } from "react";

import "./AuthorAvatar.css";

// Show only faces: uploaded avatars are served from HF's CDN, while default
// avatars are generic `/avatars/*.svg` placeholders (which also fail to load
// when embedded here). Defaults, missing URLs and failed loads render nothing.
const uploadedAvatar = (url: string | null | undefined) =>
  url?.startsWith("https://") && !url.startsWith("https://huggingface.co/avatars/") ? url : null;

interface AuthorAvatarProps {
  url?: string | null;
  className: string;
  /** Wraps the avatar in a link, e.g. to the author's HF profile. */
  href?: string;
  label?: string;
}

export const AuthorAvatar: React.FC<AuthorAvatarProps> = ({ url, className, href, label }) => {
  const [failed, setFailed] = useState(false);
  const src = failed ? null : uploadedAvatar(url);
  if (!src) return null;
  const image = (
    <img
      className={`author-avatar-base ${className}`}
      src={src}
      alt=""
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
  return href ? (
    <a href={href} target="_blank" rel="noopener noreferrer" aria-label={label}>
      {image}
    </a>
  ) : (
    image
  );
};
