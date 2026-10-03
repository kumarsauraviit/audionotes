import Link from "next/link";
import { AudioLines } from "lucide-react";

import { cn } from "@/lib/utils";

export function Brand({ href = "/", size = 19, className }: { href?: string; size?: number; className?: string }) {
  return (
    <Link
      href={href}
      className={cn(
        "inline-flex items-center gap-2.5 font-bold tracking-tight text-ink no-underline",
        className
      )}
    >
      <span className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground [border-bottom-left-radius:3px]">
        <AudioLines size={size} />
      </span>
      <span className="text-[19px] leading-none">
        audio<span className="font-normal text-muted-foreground">notes</span>
      </span>
    </Link>
  );
}
