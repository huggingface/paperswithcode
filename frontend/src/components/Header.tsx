import React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { Link, NavLink, useLocation } from "react-router-dom";

import HfSignInButton from "@/components/HfSignInButton";
import UserMenu from "@/components/UserMenu";
import {
  CANONICAL_CHAT_URL,
  isAuthDisabled,
  isChatEnabled,
  isChatMirror,
} from "@/lib/apiUrl";
import { useAuth } from "@/lib/authContext";

type HeaderIconName = "search" | "bookmark" | "menu" | "close" | "github";

const HeaderIcon: React.FC<{ name: HeaderIconName; size?: number }> = ({ name, size = 14 }) => {
  const paths: Record<HeaderIconName, React.ReactNode> = {
    search: <path d="M11 11l3 3M7 12.5a5.5 5.5 0 110-11 5.5 5.5 0 010 11z" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" />,
    bookmark: <path d="M4 2h8v12l-4-3-4 3V2z" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinejoin="round" />,
    menu: <path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />,
    close: <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />,
    github: <path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />,
  };

  return (
    <svg className={size === 11 ? "icon-sm" : "icon"} viewBox="0 0 16 16" width={size} height={size}>
      {paths[name]}
    </svg>
  );
};

interface HeaderProps {
  onOpenSearch: () => void;
}

const FEEDBACK_URL =
  "https://github.com/huggingface/paperswithcode-feedback/issues";
const GITHUB_URL = "https://github.com/huggingface/paperswithcode";
const CANONICAL_FOLLOWING_URL = "https://paperswithcode.co/following";
// A new key per announcement, so readers who closed an earlier one still see it.
const ANNOUNCEMENT_DISMISSED_KEY = "pwc:announcement:following-feed:v1:dismissed";

type HeaderNavLink = {
  to: string;
  label: string;
  end: boolean;
  badge?: string;
  href?: string;
};

const NAV_LINKS: readonly HeaderNavLink[] = [
  { to: "/", label: "Trending", end: true },
  { to: "/tasks", label: "Browse state-of-the-art", end: false },
  { to: "/methods", label: "Methods", end: false },
  { to: "/conferences", label: "Conferences", end: false },
  { to: "/organizations", label: "Organizations", end: false },
  { to: "/submit", label: "Submit", end: false },
];

// Apple devices use Cmd as the primary modifier; everyone else (Windows,
// Linux, ChromeOS, …) uses Ctrl. `navigator.userAgentData` is the modern
// signal but isn't available on Safari, so fall back to the legacy
// `navigator.platform` / `userAgent` strings.
const isApplePlatform = (): boolean => {
  if (typeof navigator === "undefined") return false;
  const uaData = (navigator as Navigator & {
    userAgentData?: { platform?: string };
  }).userAgentData;
  const platform =
    uaData?.platform || navigator.platform || navigator.userAgent || "";
  return /Mac|iPhone|iPad|iPod/i.test(platform);
};

const SearchShortcutHint: React.FC = () => {
  const [isMac, setIsMac] = React.useState(false);
  React.useEffect(() => {
    setIsMac(isApplePlatform());
  }, []);
  return <kbd>{isMac ? "⌘K" : "Ctrl K"}</kbd>;
};

const Header: React.FC<HeaderProps> = ({ onOpenSearch }) => {
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [showAnnouncement, setShowAnnouncement] = React.useState(
    () => localStorage.getItem(ANNOUNCEMENT_DISMISSED_KEY) !== "1",
  );
  const navRef = React.useRef<HTMLElement>(null);
  const navIndicatorRef = React.useRef<HTMLSpanElement>(null);
  const closeMobile = () => setMobileOpen(false);
  const { user, logout } = useAuth();
  const location = useLocation();
  const isReaderRoute = location.pathname.startsWith("/pdf/");
  const returnTo = `${location.pathname}${location.search}` || "/";
  const authDisabled = isAuthDisabled();
  const chatLink: HeaderNavLink | null = isChatEnabled()
    ? { to: "/chat", label: "Chat", end: false, badge: "New" }
    : isChatMirror()
      ? { to: "/chat", label: "Chat", end: false, badge: "New", href: CANONICAL_CHAT_URL }
      : null;
  const navLinks: readonly HeaderNavLink[] = chatLink
    ? [NAV_LINKS[0], chatLink, ...NAV_LINKS.slice(1)]
    : NAV_LINKS;

  React.useLayoutEffect(() => {
    const nav = navRef.current;
    const indicator = navIndicatorRef.current;
    if (!nav || !indicator) return;

    let disposed = false;
    const updateIndicator = () => {
      if (disposed) return;
      const activeLink = nav.querySelector<HTMLElement>(".nav-item.active");
      const width = activeLink?.offsetWidth ?? 0;
      indicator.style.width = `${width}px`;
      indicator.style.transform = `translateX(${activeLink?.offsetLeft ?? 0}px)`;
      indicator.style.opacity = width > 0 ? "1" : "0";
    };

    updateIndicator();
    const readyFrame = window.requestAnimationFrame(() => {
      indicator.classList.add("nav-indicator-ready");
    });
    const resizeObserver = typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(updateIndicator);
    resizeObserver?.observe(nav);
    window.addEventListener("resize", updateIndicator);
    void document.fonts?.ready.then(updateIndicator);

    return () => {
      disposed = true;
      window.cancelAnimationFrame(readyFrame);
      resizeObserver?.disconnect();
      window.removeEventListener("resize", updateIndicator);
    };
  }, [location.pathname, navLinks.length]);

  return (
    <Dialog.Root open={mobileOpen} onOpenChange={setMobileOpen}>
      <header className="app-header">
        <div className="app-header-inner">
          <NavLink to="/" className="brand" onClick={closeMobile}>
            <span className="brand-mark"></span>
            <span className="brand-name">
              Papers <em>With Code</em>
            </span>
          </NavLink>
          <nav className="nav" ref={navRef}>
            {navLinks.map(({ to, label, end, badge, href }) => {
              const content = (
                <>
                  <span>{label}</span>
                  {badge && <span className="nav-new-badge" aria-hidden="true">{badge}</span>}
                </>
              );
              return href ? (
                <a
                  key={to}
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  className={`nav-item${badge ? " nav-item-with-badge" : ""}`}
                >
                  {content}
                </a>
              ) : (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  className={({ isActive }) => `nav-item${badge ? " nav-item-with-badge" : ""}${isActive ? " active" : ""}`}
                >
                  {content}
                </NavLink>
              );
            })}
            <span
              ref={navIndicatorRef}
              className="nav-indicator"
              aria-hidden="true"
            />
          </nav>
          <div className="header-spacer"></div>
          <a
            className="feedback-link header-feedback-link"
            href={FEEDBACK_URL}
            target="_blank"
            rel="noreferrer"
          >
            Submit feedback
          </a>
          <a
            className="icon-btn header-github-btn"
            href={GITHUB_URL}
            target="_blank"
            rel="noreferrer"
            aria-label="GitHub repository"
            title="GitHub repository"
          >
            <HeaderIcon name="github" size={14} />
          </a>
          <button className="search-trigger" onClick={onOpenSearch}>
            <HeaderIcon name="search" size={13} />
            <span>Search papers, authors, domains…</span>
            <SearchShortcutHint />
          </button>
          <button
            className="icon-btn mobile-search-btn"
            aria-label="Search"
            onClick={onOpenSearch}
          >
            <HeaderIcon name="search" size={14} />
          </button>
          {!authDisabled && (
            <NavLink
              to="/saved"
              className="icon-btn header-bookmark-btn"
              aria-label="Saved papers"
              title="Saved papers"
            >
              <HeaderIcon name="bookmark" size={13} />
            </NavLink>
          )}
          {authDisabled ? null : user ? (
            <UserMenu user={user} onLogout={logout} />
          ) : (
            <HfSignInButton returnTo={returnTo} />
          )}
          <Dialog.Trigger asChild>
            <button
              className="icon-btn mobile-menu-btn"
              aria-label="Open menu"
            >
              <HeaderIcon name="menu" size={14} />
            </button>
          </Dialog.Trigger>
        </div>
        {!isReaderRoute && showAnnouncement && (
          <div className="site-announcement" role="status">
            <span>New: </span>
            {authDisabled ? (
              // The Space renders in a cross-origin iframe that the canonical site refuses to frame.
              <a href={CANONICAL_FOLLOWING_URL} target="_blank" rel="noreferrer">following feed</a>
            ) : (
              <Link to="/following">following feed</Link>
            )}
            <span>, follow your favorite tasks, benchmarks, authors or organizations</span>
            <button
              type="button"
              className="site-announcement-close"
              aria-label="Dismiss announcement"
              onClick={() => {
                localStorage.setItem(ANNOUNCEMENT_DISMISSED_KEY, "1");
                setShowAnnouncement(false);
              }}
            >
              <HeaderIcon name="close" size={11} />
            </button>
          </div>
        )}
      </header>
      <Dialog.Portal>
        <Dialog.Overlay className="mobile-nav-drawer">
          <Dialog.Content className="mobile-nav-panel" aria-describedby={undefined}>
            <Dialog.Title className="sr-only">Navigation menu</Dialog.Title>
            <Dialog.Close className="icon-btn mobile-nav-close" aria-label="Close menu">
              <HeaderIcon name="close" size={14} />
            </Dialog.Close>
            <button
              type="button"
              className="mobile-nav-link mobile-nav-search"
              onClick={() => {
                closeMobile();
                onOpenSearch();
              }}
            >
              <HeaderIcon name="search" size={14} />
              <span>Search papers, authors, domains…</span>
            </button>
            {navLinks.map(({ to, label, end, badge, href }) => {
              const className = `mobile-nav-link${badge ? " mobile-nav-link-with-badge" : ""}`;
              const content = (
                <>
                  <span>{label}</span>
                  {badge && <span className="nav-new-badge" aria-hidden="true">{badge}</span>}
                </>
              );
              return href ? (
                <a key={to} href={href} target="_blank" rel="noreferrer" className={className} onClick={closeMobile}>
                  {content}
                </a>
              ) : (
                <NavLink key={to} to={to} end={end} className={className} onClick={closeMobile}>
                  {content}
                </NavLink>
              );
            })}
            <a
              className="mobile-nav-link"
              href={FEEDBACK_URL}
              target="_blank"
              rel="noreferrer"
              onClick={closeMobile}
            >
              Submit feedback
            </a>
            <a
              className="mobile-nav-link"
              href={GITHUB_URL}
              target="_blank"
              rel="noreferrer"
              onClick={closeMobile}
            >
              GitHub
            </a>
            {!authDisabled && (
              <NavLink to="/saved" className="mobile-nav-link" onClick={closeMobile}>
                Saved papers
              </NavLink>
            )}
            {!authDisabled && user?.is_admin && (
              <NavLink to="/admin-dashboard" className="mobile-nav-link" onClick={closeMobile}>
                Admin dashboard
              </NavLink>
            )}
          </Dialog.Content>
        </Dialog.Overlay>
      </Dialog.Portal>
    </Dialog.Root>
  );
};

export default Header;
