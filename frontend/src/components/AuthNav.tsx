"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogOut, ShieldCheck, User as UserIcon } from "lucide-react";

import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export function AuthNav() {
  const router = useRouter();
  const { user, isAuthenticated, isLoading, logout } = useAuth();

  if (isLoading) {
    return <div className="size-8 animate-pulse rounded-full bg-muted" aria-hidden="true" />;
  }

  if (!isAuthenticated || !user) {
    return (
      <div className="flex items-center gap-1.5">
        <Button asChild variant="ghost" size="sm" className="h-9">
          <Link href="/login">Log in</Link>
        </Button>
        <Button asChild size="sm" className="hidden h-9 sm:inline-flex">
          <Link href="/register">Create account</Link>
        </Button>
      </div>
    );
  }

  const initial = (user.name || user.email || "U").trim().charAt(0).toUpperCase();

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="grid size-8 place-items-center rounded-full bg-accent-wash text-sm font-bold text-accent-dark outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="User account menu"
        >
          {initial}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="flex items-center gap-2 normal-case">
          <span className="grid size-8 place-items-center rounded-full bg-accent-wash text-sm font-bold text-accent-dark">
            {initial}
          </span>
          <span className="flex min-w-0 flex-col">
            <span className="truncate text-sm font-semibold text-ink">{user.name}</span>
            <span className="truncate text-xs font-normal text-muted-foreground">{user.email}</span>
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {user.is_verified ? (
          <div className="flex items-center gap-2 px-2 py-1.5 text-xs text-green">
            <ShieldCheck size={12} /> Verified account
          </div>
        ) : (
          <DropdownMenuItem asChild>
            <Link href="/verify-email">
              <UserIcon size={14} /> Verify email address
            </Link>
          </DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void handleLogout()} className="text-destructive focus:bg-destructive/10">
          <LogOut size={14} /> Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
