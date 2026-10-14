import React, { useState } from "react";

import "./AuthorAvatar.css";

// Only uploaded avatars are served from HF's CDN. Default avatars are
// site-relative `/avatars/*.svg` paths that fail to load when embedded here,
// so those (and any image that errors) fall back to the author's initials.
const uploadedAvatar = (url: string | null | undefined) =>
  url?.startsWith("https://") && !url.startsWith("https://huggingface.co/avatars/") ? url : null;

const initials = (name: string) => {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const letters = words.length > 1 ? [words[0], words[words.length - 1]] : words;
  return letters.map((word) => word[0]).join("").toUpperCase();
};

interface AuthorAvatarProps {
  name: string;
  url?: string | null;
  className: string;
}

export const AuthorAvatar: React.FC<AuthorAvatarProps> = ({ name, url, className }) => {
  const [failed, setFailed] = useState(false);
  const src = failed ? null : uploadedAvatar(url);
  if (src) {
    return (
      <img
        className={`author-avatar-base ${className}`}
        src={src}
        alt=""
        loading="lazy"
        onError={() => setFailed(true)}
      />
    );
  }
  return (
    <span className={`author-avatar-base author-avatar-initials ${className}`} aria-hidden="true">
      {initials(name)}
    </span>
  );
};
