import { useEffect, useRef, useState, type CSSProperties } from "react";

import { PanelIcon, PlusIcon, TrashIcon } from "./icons";
import { canNavigateAwayFromArtifact } from "./useArtifactPanel";
import { McpShowcase } from "@/components/McpShowcase";
import { type ChatSession, groupSessions } from "@/lib/chatSessions";

const SIDEBAR_WIDTH_KEY = "pwc:chat:sidebar-width";
const DEFAULT_SIDEBAR_WIDTH = 280;
const MIN_SIDEBAR_WIDTH = 200;
const MAX_SIDEBAR_WIDTH = 480;
const COLLAPSED_SESSION_COUNT = 12;

const clampSidebarWidth = (width: number) => (
  Math.max(MIN_SIDEBAR_WIDTH, Math.min(MAX_SIDEBAR_WIDTH, width))
);

const savedSidebarWidth = () => {
  if (typeof window === "undefined") return DEFAULT_SIDEBAR_WIDTH;
  const stored = Number(localStorage.getItem(SIDEBAR_WIDTH_KEY));
  return Number.isFinite(stored) && stored > 0
    ? clampSidebarWidth(stored)
    : DEFAULT_SIDEBAR_WIDTH;
};

interface ChatSessionNavigationProps {
  sessions: ChatSession[];
  activeSessionId?: string;
  loading: boolean;
  error: string;
  open: boolean;
  onClose: () => void;
  onNew: () => void;
  onNavigate: (sessionId: string) => void;
  onRename: (sessionId: string, title: string) => Promise<boolean>;
  onDelete: (sessionId: string) => void;
  /** Delete several chats; resolves true when all of them were deleted. */
  onDeleteMany: (sessionIds: string[]) => Promise<boolean>;
}

export function ChatSessionNavigation({
  sessions,
  activeSessionId,
  loading,
  error,
  open,
  onClose,
  onNew,
  onNavigate,
  onRename,
  onDelete,
  onDeleteMany,
}: ChatSessionNavigationProps) {
  const [sidebarWidth, setSidebarWidth] = useState(savedSidebarWidth);
  const dragStart = useRef<{ x: number; width: number } | null>(null);
  const pendingWidth = useRef(sidebarWidth);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [menu, setMenu] = useState<{ id: string; x: number; y: number } | null>(null);
  const [showAllSessions, setShowAllSessions] = useState(false);
  const [selectedIds, setSelectedIds] = useState<ReadonlySet<string>>(new Set());
  const selectedSessionIds = sessions.filter((session) => selectedIds.has(session.id)).map((session) => session.id);
  const selecting = selectedSessionIds.length > 0;
  const [deleting, setDeleting] = useState(false);
  const recentSessions = [...sessions].sort(
    (a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at),
  );
  const collapsedSessions = recentSessions.filter(
    (session, index) => index < COLLAPSED_SESSION_COUNT || session.id === activeSessionId,
  );
  const visibleSessions = showAllSessions ? recentSessions : collapsedSessions;
  const hiddenSessionCount = sessions.length - collapsedSessions.length;

  useEffect(() => {
    if (!menu) return;
    const close = () => setMenu(null);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("click", close);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("keydown", onKey);
    };
  }, [menu]);

  useEffect(() => {
    if (!selecting) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelectedIds(new Set());
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selecting]);

  const sessionGroups = groupSessions(visibleSessions);
  const orderedSessionIds = sessionGroups.flatMap((group) => group.items.map((session) => session.id));
  /** The chat a Shift-click range starts from: the last one toggled on its own. */
  const selectionAnchor = useRef<string | null>(null);
  const toggleSelected = (sessionId: string) => {
    selectionAnchor.current = sessionId;
    setSelectedIds((previous) => {
      const next = new Set(previous);
      if (next.has(sessionId)) next.delete(sessionId);
      else next.add(sessionId);
      return next;
    });
  };
  /**
   * Shift-click: add every listed chat between the anchor and `sessionId`.
   * With nothing selected yet, the range starts at the open chat.
   */
  const selectRange = (sessionId: string) => {
    const selectedAnchor = selectionAnchor.current && selectedIds.has(selectionAnchor.current)
      ? selectionAnchor.current
      : null;
    const anchor = selectedAnchor ?? (selecting ? null : activeSessionId ?? null);
    if (anchor) selectionAnchor.current = anchor;
    const from = anchor ? orderedSessionIds.indexOf(anchor) : -1;
    const to = orderedSessionIds.indexOf(sessionId);
    if (from < 0 || to < 0) {
      // No range to extend: select this chat and start the next range here.
      selectionAnchor.current = sessionId;
      setSelectedIds((previous) => new Set([...previous, sessionId]));
      return;
    }
    const range = orderedSessionIds.slice(Math.min(from, to), Math.max(from, to) + 1);
    setSelectedIds((previous) => new Set([...previous, ...range]));
  };
  const deleteSelected = async () => {
    if (deleting || !canNavigateAwayFromArtifact()) return;
    setDeleting(true);
    try {
      if (await onDeleteMany(selectedSessionIds)) setSelectedIds(new Set());
    } finally {
      setDeleting(false);
    }
  };
  const beginRename = (session: ChatSession) => {
    setEditingId(session.id);
    setEditingTitle(session.title);
  };
  const saveRename = async (sessionId: string) => {
    const title = editingTitle.trim();
    if (title && await onRename(sessionId, title)) setEditingId(null);
  };
  const openMenu = (id: string, x: number, y: number) => setMenu({ id, x, y });
  const resizeFromPointer = (clientX: number) => {
    if (!dragStart.current) return;
    const next = clampSidebarWidth(
      dragStart.current.width + clientX - dragStart.current.x,
    );
    pendingWidth.current = next;
    setSidebarWidth(next);
  };
  const finishResize = () => {
    if (!dragStart.current) return;
    dragStart.current = null;
    localStorage.setItem(SIDEBAR_WIDTH_KEY, String(pendingWidth.current));
  };
  const saveSidebarWidth = (next: number) => {
    const width = clampSidebarWidth(next);
    pendingWidth.current = width;
    setSidebarWidth(width);
    localStorage.setItem(SIDEBAR_WIDTH_KEY, String(width));
  };

  return (
    <>
    {open && <div className="chat-sidebar-backdrop" aria-hidden="true" onClick={onClose} />}
    <aside
      className={`chat-sidebar${open ? "" : " chat-sidebar-closed"}`}
      style={{ "--chat-sidebar-width": `${sidebarWidth}px` } as CSSProperties}
    >
      <div className="chat-sidebar-top">
        <button type="button" className="chat-new-chat" onClick={() => { if (canNavigateAwayFromArtifact()) onNew(); }}><PlusIcon /> New chat</button>
        <button type="button" className="icon-btn" onClick={onClose} title="Collapse sidebar"><PanelIcon /></button>
      </div>
      {selecting && <div className="chat-sessions-bulk" role="toolbar" aria-label="Selected chats">
        <span className="chat-sessions-bulk-count">{selectedSessionIds.length} selected</span>
        <button type="button" className="chat-sessions-bulk-delete" disabled={deleting} onClick={() => void deleteSelected()}><TrashIcon /> {deleting ? "Deleting…" : "Delete"}</button>
        <button type="button" className="chat-sessions-bulk-cancel" disabled={deleting} onClick={() => setSelectedIds(new Set())}>Cancel</button>
      </div>}
      <nav className="chat-sessions" aria-label="Chat history">
        {loading && <div className="chat-sessions-empty">Loading chats…</div>}
        {!loading && error && <div className="chat-sessions-empty">{error}</div>}
        {!loading && !error && sessions.length === 0 && (
          <div className="chat-sessions-empty">Conversations you start will show up here.</div>
        )}
        {sessionGroups.map((group) => <div className="chat-session-group" key={group.label}>
          <div className="chat-session-group-label">{group.label}</div>
          {group.items.map((session) => <div
            key={session.id}
            className={`chat-session${session.id === activeSessionId ? " chat-session-active" : ""}${selectedIds.has(session.id) ? " chat-session-selected" : ""}`}
            role="button"
            tabIndex={0}
            aria-pressed={selecting ? selectedIds.has(session.id) : undefined}
            title={selecting ? "Shift-click to select every chat up to here" : "Shift-click to select several chats"}
            // Keep Shift-click from extending the page's text selection.
            onMouseDown={(event) => { if (event.shiftKey) event.preventDefault(); }}
            onClick={(event) => {
              if (event.shiftKey) selectRange(session.id);
              else if (selecting) toggleSelected(session.id);
              else if (canNavigateAwayFromArtifact()) onNavigate(session.id);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" && event.shiftKey) selectRange(session.id);
              else if (event.key === "Enter" && selecting) toggleSelected(session.id);
              else if (event.key === "Enter" && canNavigateAwayFromArtifact()) onNavigate(session.id);
              if (event.key === "F2") beginRename(session);
              if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
                event.preventDefault();
                const rect = event.currentTarget.getBoundingClientRect();
                openMenu(session.id, rect.right - 150, rect.bottom);
              }
            }}
            onContextMenu={(event) => {
              event.preventDefault();
              openMenu(session.id, event.clientX, event.clientY);
            }}
          >
            {editingId === session.id ? <input
              className="chat-session-title-input"
              value={editingTitle}
              autoFocus
              maxLength={80}
              onClick={(event) => event.stopPropagation()}
              onChange={(event) => setEditingTitle(event.target.value)}
              onBlur={() => void saveRename(session.id)}
              onKeyDown={(event) => {
                event.stopPropagation();
                if (event.key === "Enter") void saveRename(session.id);
                if (event.key === "Escape") setEditingId(null);
              }}
            /> : <span className="chat-session-title">{session.title}</span>}
            <button
              type="button"
              className="chat-session-menu"
              aria-label="Chat actions"
              aria-haspopup="menu"
              title="Chat actions"
              onClick={(event) => {
                event.stopPropagation();
                const rect = event.currentTarget.getBoundingClientRect();
                openMenu(session.id, rect.right - 150, rect.bottom);
              }}
            >⋯</button>
            <button
              type="button"
              className="chat-session-delete"
              aria-label={selectedIds.has(session.id) ? "Delete selected conversations" : "Delete conversation"}
              onClick={(event) => {
                event.stopPropagation();
                // On a selected chat, the trash acts on the whole selection.
                if (selectedIds.has(session.id)) void deleteSelected();
                else if (canNavigateAwayFromArtifact()) onDelete(session.id);
              }}
            ><TrashIcon /></button>
          </div>)}
        </div>)}
        {hiddenSessionCount > 0 && <button
          type="button"
          className="chat-sessions-toggle"
          aria-expanded={showAllSessions}
          onClick={() => setShowAllSessions((value) => !value)}
        >
          {showAllSessions ? "Show less" : `Show ${hiddenSessionCount} older ${hiddenSessionCount === 1 ? "chat" : "chats"}`}
        </button>}
      </nav>
      <McpShowcase className="chat-sidebar-tools" canNavigate={canNavigateAwayFromArtifact} />
      <div
        className="chat-sidebar-resize-handle"
        role="separator"
        aria-label="Resize chat history"
        aria-orientation="vertical"
        aria-valuemin={MIN_SIDEBAR_WIDTH}
        aria-valuemax={MAX_SIDEBAR_WIDTH}
        aria-valuenow={sidebarWidth}
        title="Drag to resize; double-click to reset"
        tabIndex={0}
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          dragStart.current = { x: event.clientX, width: sidebarWidth };
          pendingWidth.current = sidebarWidth;
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => resizeFromPointer(event.clientX)}
        onPointerUp={finishResize}
        onPointerCancel={finishResize}
        onLostPointerCapture={finishResize}
        onDoubleClick={() => saveSidebarWidth(DEFAULT_SIDEBAR_WIDTH)}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            saveSidebarWidth(sidebarWidth + (event.key === "ArrowRight" ? 10 : -10));
          }
          if (event.key === "Home" || event.key === "End") {
            event.preventDefault();
            saveSidebarWidth(event.key === "Home" ? MIN_SIDEBAR_WIDTH : MAX_SIDEBAR_WIDTH);
          }
        }}
      />
      {menu && <div
        className="chat-session-context-menu"
        role="menu"
        style={{ left: menu.x, top: menu.y }}
        onClick={(event) => event.stopPropagation()}
      >
        <button type="button" role="menuitem" autoFocus onClick={() => {
          const session = sessions.find((item) => item.id === menu.id);
          if (session) beginRename(session);
          setMenu(null);
        }}>Rename chat</button>
        <button type="button" role="menuitem" onClick={() => {
          toggleSelected(menu.id);
          setMenu(null);
        }}>{selectedIds.has(menu.id) ? "Deselect chat" : "Select chat"}</button>
      </div>}
    </aside>
    </>
  );
}
