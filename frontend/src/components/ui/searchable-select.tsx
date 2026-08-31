import { useEffect, useMemo, useState } from "react";
import { Check, ChevronsUpDown, Loader2 } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { cn } from "@/lib/utils";

const SEARCH_DEBOUNCE_MS = 250;

export interface SearchableSelectOption {
  value: string;
  label: string;
  description?: string;
}

interface SearchableSelectProps {
  value: string;
  onChange: (value: string, option: SearchableSelectOption) => void;
  placeholder?: string;
  searchPlaceholder?: string;
  emptyMessage?: string;
  errorMessage?: string;
  disabled?: boolean;
  /** Shown in the trigger when `value` is set but not in current search results. */
  selectedOption?: SearchableSelectOption | null;
  queryKey: readonly unknown[];
  queryFn: (query: string) => Promise<SearchableSelectOption[]>;
  enabled?: boolean;
  className?: string;
  ariaLabel?: string;
}

export function SearchableSelect({
  value,
  onChange,
  placeholder = "Select...",
  searchPlaceholder = "Search...",
  emptyMessage = "No results found.",
  errorMessage,
  disabled = false,
  selectedOption,
  queryKey,
  queryFn,
  enabled = true,
  className,
  ariaLabel,
}: SearchableSelectProps) {
  const [open, setOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setDebouncedQuery(searchQuery.trim());
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [searchQuery]);

  useEffect(() => {
    if (!open) {
      setSearchQuery("");
      setDebouncedQuery("");
    }
  }, [open]);

  const { data: options = [], isFetching, isError } = useQuery({
    queryKey: [...queryKey, debouncedQuery],
    queryFn: () => queryFn(debouncedQuery),
    enabled: enabled && open,
  });

  const displayedOptions = useMemo(() => {
    if (!value) return options;
    if (options.some((option) => option.value === value)) return options;
    if (selectedOption?.value === value) {
      return [selectedOption, ...options];
    }
    return options;
  }, [options, selectedOption, value]);

  const triggerLabel = useMemo(() => {
    if (!value) return placeholder;
    const match =
      displayedOptions.find((option) => option.value === value) ??
      (selectedOption?.value === value ? selectedOption : null);
    return match?.label ?? placeholder;
  }, [displayedOptions, placeholder, selectedOption, value]);

  return (
    <Popover open={open} onOpenChange={setOpen} modal>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          aria-label={ariaLabel}
          disabled={disabled}
          className={cn(
            "h-8 w-full justify-between px-2 text-sm font-normal",
            !value && "text-muted-foreground",
            className,
          )}
        >
          <span className="truncate">{triggerLabel}</span>
          <ChevronsUpDown className="ml-1 h-3.5 w-3.5 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="z-[60] w-[var(--radix-popover-trigger-width)] max-h-[var(--radix-popover-content-available-height)] overflow-hidden p-0"
        align="start"
        collisionPadding={8}
        onWheel={(e) => e.stopPropagation()}
      >
        <Command shouldFilter={false} className="h-full">
          <CommandInput
            placeholder={searchPlaceholder}
            value={searchQuery}
            onValueChange={setSearchQuery}
          />
          <CommandList className="max-h-[min(300px,calc(var(--radix-popover-content-available-height)-2.75rem))] min-h-0 overscroll-contain">
            {isFetching ? (
              <div className="flex items-center justify-center py-6 text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Loading...
              </div>
            ) : isError && errorMessage ? (
              <div className="px-4 py-6 text-center text-sm text-destructive" role="alert">
                {errorMessage}
              </div>
            ) : displayedOptions.length === 0 ? (
              <CommandEmpty>{emptyMessage}</CommandEmpty>
            ) : (
              <CommandGroup>
                {displayedOptions.map((option) => (
                  <CommandItem
                    key={option.value}
                    value={option.value}
                    onSelect={() => {
                      onChange(option.value, option);
                      setOpen(false);
                    }}
                  >
                    <Check
                      className={cn(
                        "mr-2 h-4 w-4",
                        value === option.value ? "opacity-100" : "opacity-0",
                      )}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="truncate">{option.label}</div>
                      {option.description ? (
                        <div className="truncate text-xs text-muted-foreground">
                          {option.description}
                        </div>
                      ) : null}
                    </div>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
