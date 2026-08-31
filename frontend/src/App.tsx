/**
 * Root app for the v2 frontend.
 *
 * Replaces the prototype's manual `setView(...)` state machine (App.jsx) with
 * react-router-dom routes (PLAN.md §3). Every page is bookmarkable and the
 * browser back button works as expected.
 */

import React from "react";
import {
  BrowserRouter,
  HashRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
  useParams,
} from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";

import Header from "@/components/Header";
import HfSignInButton from "@/components/HfSignInButton";
import SiteFooter from "@/components/SiteFooter";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as SonnerToaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useScrollToTop } from "@/hooks/useScrollToTop";
import {
  adminDashboardUrl,
  isAuthDisabled,
  isChatEnabled,
  isNativePdfReaderEnabled,
  shouldUseHashRouter,
} from "@/lib/apiUrl";
import { AuthProvider, useAuth } from "@/lib/authContext";
import { PreferencesProvider } from "@/lib/preferencesContext";

// HF Static Spaces (a) boot the iframe at `/index.html` and (b) return a
// hard 404 for any deep link, so on those builds we switch to `HashRouter`.
// See `shouldUseHashRouter` in `lib/apiUrl.ts`.
const useHashRouter = shouldUseHashRouter();
const Router = useHashRouter ? HashRouter : BrowserRouter;

if (!useHashRouter && typeof window !== "undefined") {
  const hashRoute = window.location.hash;
  if (hashRoute.startsWith("#/") && !hashRoute.startsWith("#//")) {
    window.history.replaceState(null, "", hashRoute.slice(1));
  }
}

// Lazy-load route components so visitors only download the chunks for the
// pages they actually navigate to. Saves ~150-200 KB gzipped on first paint
// for visitors landing on a single route. See PLAN.md §4.
const FeedView = React.lazy(() => import("@/views/FeedView"));
const ChatView = React.lazy(() => import("@/views/ChatView"));
const SharedChatView = React.lazy(() => import("@/views/SharedChatView"));
const PapersListView = React.lazy(() => import("@/views/PapersListView"));
const PaperDetailView = React.lazy(() => import("@/views/PaperDetailView"));
const PaperReaderView = React.lazy(() => import("@/views/PaperReaderView"));
const TagsIndexView = React.lazy(() => import("@/views/TagsIndexView"));
const TagBrowseView = React.lazy(() => import("@/views/TagBrowseView"));
const MethodsIndexView = React.lazy(() => import("@/views/MethodsIndexView"));
const FrameworksIndexView = React.lazy(() => import("@/views/FrameworksIndexView"));
const TrendsView = React.lazy(() => import("@/views/TrendsView"));
const ConferencesIndexView = React.lazy(() => import("@/views/ConferencesIndexView"));
const AiDeadlinesView = React.lazy(() => import("@/views/AiDeadlinesView"));
const ConferenceDetailView = React.lazy(() => import("@/views/ConferenceDetailView"));
const ConferenceTaskView = React.lazy(() => import("@/views/ConferenceTaskView"));
const OrganizationsIndexView = React.lazy(() => import("@/views/OrganizationsIndexView"));
const OrganizationDetailView = React.lazy(() => import("@/views/OrganizationDetailView"));
const OrganizationTaskView = React.lazy(() => import("@/views/OrganizationTaskView"));
const AuthorDetailView = React.lazy(() => import("@/views/AuthorDetailView"));
const MethodDetailView = React.lazy(() => import("@/views/MethodDetailView"));
const BenchmarkDetailView = React.lazy(() => import("@/views/BenchmarkDetailView"));
const SavedPapersView = React.lazy(() => import("@/views/SavedPapersView"));
const SettingsView = React.lazy(() => import("@/views/SettingsView"));
const PrivacyView = React.lazy(() => import("@/views/PrivacyView"));
const SubmitView = React.lazy(() => import("@/views/SubmitView"));
const CronDashboard = React.lazy(() => import("@/pages/CronDashboard"));
const AutonomousOperations = React.lazy(() => import("@/pages/AutonomousOperations"));
const SubmissionsDashboard = React.lazy(() => import("@/pages/SubmissionsDashboard"));
const UserProfileView = React.lazy(() => import("@/views/UserProfileView"));
const RateLimitsView = React.lazy(() => import("@/views/RateLimitsView"));
const NotFound = React.lazy(() => import("@/pages/NotFound"));
const SearchOverlay = React.lazy(() => import("@/components/SearchOverlay"));
const StagingAccessRequestView = React.lazy(() => import("@/views/StagingAccessRequestView"));

// Visible page-shape skeleton shown while the route's lazy chunk is
// downloading. A blank `aria-busy` div was confusing visitors on slow
// connections because the previous page's content stayed in their viewport
// until the new chunk arrived. Rendering a structured skeleton makes the
// transition feel intentional and immediate.
const RouteFallback: React.FC = () => (
  <div className="page" aria-busy="true" aria-live="polite">
    <div
      className="animate-pulse rounded-md bg-muted"
      style={{ height: 24, width: "30%", marginBottom: 24 }}
    />
    <div
      className="animate-pulse rounded-md bg-muted"
      style={{ height: 64, width: "60%", marginBottom: 32 }}
    />
    <div className="paper-list" style={{ display: "grid", gap: 16 }}>
      <div className="animate-pulse rounded-md bg-muted" style={{ height: 96 }} />
      <div className="animate-pulse rounded-md bg-muted" style={{ height: 96 }} />
      <div className="animate-pulse rounded-md bg-muted" style={{ height: 96 }} />
    </div>
  </div>
);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const LegacyPaperRedirect: React.FC = () => {
  const { arxivId } = useParams();
  return <Navigate to={arxivId ? `/paper/${arxivId}` : "/papers"} replace />;
};

const LegacyTaskRedirect: React.FC = () => {
  const { taskSlug } = useParams();
  return <Navigate to={taskSlug ? `/tasks/${taskSlug}` : "/tasks"} replace />;
};

// On the Hugging Face Space mirror (`VITE_DISABLE_AUTH=1`) the HF OAuth
// cookie can't follow visitors across origins, so any view that requires
// sign-in (bookmarks, admin dashboard) is a dead-end. Redirect those routes
// home so visitors don't land on empty pages.
const AuthGatedRoute: React.FC<{ element: React.ReactNode }> = ({ element }) => {
  if (isAuthDisabled()) {
    return <Navigate to="/" replace />;
  }
  return <>{element}</>;
};

const AdminGatedRoute: React.FC<{ element: React.ReactNode }> = ({ element }) => {
  const { user, isLoading } = useAuth();
  const authDisabled = isAuthDisabled();

  if (authDisabled) {
    return <Navigate to="/" replace />;
  }

  if (isLoading) {
    return (
      <div className="page">
        <div className="submission-loading">
          <span>Checking admin session...</span>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="page">
        <div className="submission-empty submission-empty-warn">
          <h1>Sign in required</h1>
          <p>Sign in with an allowlisted Hugging Face admin account to view admin operations.</p>
          <HfSignInButton returnTo="/admin-dashboard" />
        </div>
      </div>
    );
  }

  if (!user.is_admin) {
    return (
      <div className="page">
        <div className="submission-empty submission-empty-warn">
          <h1>Admin access required</h1>
          <p>Signed in as @{user.username}. This dashboard is limited to allowlisted admin accounts.</p>
        </div>
      </div>
    );
  }

  return <>{element}</>;
};

const AdminDashboardRoute: React.FC = () => {
  const destination = adminDashboardUrl();
  const externalDestination =
    typeof window !== "undefined" &&
    new URL(destination, window.location.origin).origin !== window.location.origin;

  React.useEffect(() => {
    if (externalDestination) {
      window.location.replace(destination);
    }
  }, [destination, externalDestination]);

  if (externalDestination) {
    return (
      <div className="page">
        <div className="submission-loading">
          <span>Opening the production admin dashboard...</span>
          <a href={destination}>Continue</a>
        </div>
      </div>
    );
  }

  return <AdminGatedRoute element={<CronDashboard />} />;
};

const Shell: React.FC = () => {
  const [searchOpen, setSearchOpen] = React.useState(false);
  const location = useLocation();

  useScrollToTop();
  React.useLayoutEffect(() => {
    document.getElementById("initial-discovery-footer")?.remove();
  }, []);

  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  if (location.pathname === "/request-access") {
    return (
      <React.Suspense fallback={<RouteFallback />}>
        <StagingAccessRequestView />
      </React.Suspense>
    );
  }

  if (location.pathname.startsWith("/pdf/")) {
    return (
      <div className="reader-route-shell">
        <Header onOpenSearch={() => setSearchOpen(true)} />
        <div className="reader-route-content">
          <React.Suspense fallback={<RouteFallback />}>
            <Routes>
              <Route
                path="/pdf/:paperId"
                element={isNativePdfReaderEnabled() ? <PaperReaderView /> : <NotFound />}
              />
            </Routes>
          </React.Suspense>
        </div>
        {searchOpen && (
          <React.Suspense fallback={null}>
            <SearchOverlay open={searchOpen} onClose={() => setSearchOpen(false)} />
          </React.Suspense>
        )}
      </div>
    );
  }

  return (
    <>
      <Header onOpenSearch={() => setSearchOpen(true)} />
      <main>
        <React.Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route path="/" element={<FeedView />} />
            {/* Keep new and persisted chats on the same route instance. A new
                turn replaces /chat with /chat/:sessionId as soon as the server
                allocates it; sibling routes would unmount ChatView and abort
                that turn's active SSE request. */}
            <Route
              path="/chat/:sessionId?"
              element={isChatEnabled() ? <ChatView /> : <Navigate to="/" replace />}
            />
            <Route
              path="/share/:shareId"
              element={isChatEnabled() ? <SharedChatView /> : <NotFound />}
            />
            <Route path="/papers" element={<PapersListView />} />
            <Route path="/papers/:arxivId" element={<LegacyPaperRedirect />} />
            <Route path="/paper/:arxivId" element={<PaperDetailView />} />
            <Route path="/tasks" element={<TagsIndexView />} />
            <Route path="/tasks/:taskSlug" element={<TagBrowseView />} />
            <Route path="/task/:taskSlug" element={<LegacyTaskRedirect />} />
            <Route path="/methods" element={<MethodsIndexView />} />
            <Route path="/methods/:methodSlug" element={<MethodDetailView />} />
            <Route path="/frameworks" element={<FrameworksIndexView />} />
            <Route path="/trends" element={<TrendsView />} />
            <Route path="/conferences" element={<ConferencesIndexView />} />
            <Route path="/ai-deadlines" element={<AiDeadlinesView />} />
            <Route path="/conferences/:confSlug" element={<ConferenceDetailView />} />
            <Route path="/conferences/:confSlug/:taskSlug" element={<ConferenceTaskView />} />
            <Route path="/organizations" element={<OrganizationsIndexView />} />
            <Route path="/orgs/:orgSlug" element={<OrganizationDetailView />} />
            <Route path="/orgs/:orgSlug/:taskSlug" element={<OrganizationTaskView />} />
            <Route path="/authors/:authorId" element={<AuthorDetailView />} />
            <Route path="/benchmark/:datasetSlug" element={<BenchmarkDetailView />} />
            <Route path="/submit" element={<SubmitView />} />
            <Route path="/saved" element={<AuthGatedRoute element={<SavedPapersView />} />} />
            <Route path="/settings" element={<SettingsView />} />
            <Route path="/privacy" element={<PrivacyView />} />
            <Route path="/admin-dashboard" element={<AdminDashboardRoute />} />
            <Route path="/autonomous-operations" element={<AdminGatedRoute element={<AutonomousOperations />} />} />
            <Route path="/cron-dashboard" element={<Navigate to="/admin-dashboard" replace />} />
            <Route path="/submissions" element={<AuthGatedRoute element={<SubmissionsDashboard />} />} />
            <Route path="/rate-limits" element={<RateLimitsView />} />
            <Route path="/:username" element={<UserProfileView />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </React.Suspense>
      </main>
      <SiteFooter />
      {searchOpen && (
        <React.Suspense fallback={null}>
          <SearchOverlay open={searchOpen} onClose={() => setSearchOpen(false)} />
        </React.Suspense>
      )}
    </>
  );
};

const App: React.FC = () => (
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <PreferencesProvider>
        <TooltipProvider>
          <Router>
            <Shell />
          </Router>
          <Toaster />
          <SonnerToaster />
          {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
        </TooltipProvider>
      </PreferencesProvider>
    </AuthProvider>
  </QueryClientProvider>
);

export default App;
