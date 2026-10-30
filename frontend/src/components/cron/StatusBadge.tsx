import { Badge, type BadgeProps } from "@/components/ui/badge";
import { toneClass, type Tone } from "@/lib/cronStatus";
import { cn } from "@/lib/utils";

export function StatusBadge({ tone, className, ...props }: { tone: Tone } & Omit<BadgeProps, "variant">) {
  return <Badge variant="outline" className={cn(toneClass(tone), className)} {...props} />;
}
