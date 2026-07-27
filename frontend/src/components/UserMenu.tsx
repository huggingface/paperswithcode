/**
 * Header avatar dropdown shown to signed-in users.
 *
 * Trigger is the user's HF avatar (or initials fallback). The dropdown lists
 * the username, an "Admin" badge if the account is on the allowlist, a link
 * to the HF profile, and a "Log out" item that POSTs `/api/v1/auth/logout`.
 */

import React from "react";
import { Link } from "react-router-dom";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { AuthUser } from "@/lib/authContext";

interface UserMenuProps {
  user: AuthUser;
  onLogout: () => void | Promise<void>;
}

function initialsFor(user: AuthUser): string {
  const source = (user.name || user.username || "?").trim();
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0][0]!.toUpperCase();
  return (parts[0][0]! + parts[parts.length - 1][0]!).toUpperCase();
}

export const UserMenu: React.FC<UserMenuProps> = ({ user, onLogout }) => {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="user-avatar-btn"
          aria-label={`Account menu for ${user.username}`}
        >
          <Avatar className="h-8 w-8">
            {user.avatar_url && <AvatarImage src={user.avatar_url} alt={user.username} />}
            <AvatarFallback className="text-xs">{initialsFor(user)}</AvatarFallback>
          </Avatar>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="flex flex-col gap-0.5 py-2">
          <span className="text-sm font-medium leading-tight">
            {user.name || user.username}
          </span>
          <span className="text-xs font-normal text-muted-foreground">@{user.username}</span>
          {user.is_admin && (
            <span className="mt-1 inline-flex w-fit items-center rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-900">
              Admin
            </span>
          )}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <a
            href={`https://huggingface.co/${encodeURIComponent(user.username)}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            Hugging Face profile
          </a>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to="/frameworks">Frameworks</Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to="/trends">Trends</Link>
        </DropdownMenuItem>
        {user.is_admin && (
          <>
            <DropdownMenuItem asChild>
              <Link to="/admin-dashboard">Admin dashboard</Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link to="/submissions">Review submissions</Link>
            </DropdownMenuItem>
          </>
        )}
        <DropdownMenuItem asChild>
          <Link to="/settings">Settings</Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={(event) => {
            event.preventDefault();
            void onLogout();
          }}
        >
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export default UserMenu;
