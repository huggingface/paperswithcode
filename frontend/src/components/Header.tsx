import React from "react";
import { NavLink, useLocation } from "react-router-dom";

import HfSignInButton from "@/components/HfSignInButton";
import UserMenu from "@/components/UserMenu";
import { isAuthDisabled, isChatEnabled } from "@/lib/apiUrl";
import { useAuth } from "@/lib/authContext";

type HeaderIconName = "search" | "bookmark" | "menu" | "close";

const HeaderIcon: React.FC<{ name: HeaderIconName; size?: number }> = ({ name, size = 14 }) => {
  const paths: Record<HeaderIconName, React.ReactNode> = {
    search: <path d="M11 11l3 3M7 12.5a5.5 5.5 0 110-11 5.5 5.5 0 010 11z" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" />,
    bookmark: <path d="M4 2h8v12l-4-3-4 3V2z" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinejoin="round" />,
    menu: <path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />,
    close: <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />,
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

const NAV_LINKS = [
  { to: "/", label: "Trending", end: true },
  { to: "/tasks", label: "Browse state-of-the-art", end: false },
  { to: "/methods", label: "Methods", end: false },
  { to: "/frameworks", label: "Frameworks", end: false },
  { to: "/conferences", label: "Conferences", end: false },
  { to: "/submit", label: "Submit", end: false },
] as const;

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
  const closeMobile = () => setMobileOpen(false);
  const { user, logout } = useAuth();
  const location = useLocation();
  const isChatPage = isChatEnabled()
    && (location.pathname === "/chat" || location.pathname.startsWith("/chat/"));
  const returnTo = `${location.pathname}${location.search}` || "/";
  const authDisabled = isAuthDisabled();

  return (
    <>
      <header className={`app-header${isChatPage ? " app-header-chat" : ""}`}>
        <div className="app-header-inner">
          <NavLink to="/" className="brand" onClick={closeMobile}>
            <span className="brand-mark"></span>
            <span className="brand-name">
              Papers <em>With Code</em>
            </span>
          </NavLink>
          <nav className="nav">
            {NAV_LINKS.map(({ to, label, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
              >
                {label}
              </NavLink>
            ))}
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
          <button
            className="icon-btn mobile-menu-btn"
            aria-label="Open menu"
            onClick={() => setMobileOpen((v) => !v)}
          >
            <HeaderIcon name={mobileOpen ? "close" : "menu"} size={14} />
          </button>
        </div>
      </header>
      {mobileOpen && (
        <div className="mobile-nav-drawer" onClick={closeMobile}>
          <div className="mobile-nav-panel" onClick={(e) => e.stopPropagation()}>
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
            {NAV_LINKS.map(({ to, label, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className="mobile-nav-link"
                onClick={closeMobile}
              >
                {label}
              </NavLink>
            ))}
            <a
              className="mobile-nav-link"
              href={FEEDBACK_URL}
              target="_blank"
              rel="noreferrer"
              onClick={closeMobile}
            >
              Submit feedback
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
          </div>
        </div>
      )}
    </>
  );
};

export default Header;
