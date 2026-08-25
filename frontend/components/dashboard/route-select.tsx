"use client";

import { useState } from "react";
import { Check, ChevronsUpDown, RouteIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { useKnownRoutes } from "@/lib/queries";

export function RouteSelect({ value, onChange }: { value: string | null; onChange: (route: string | null) => void }) {
  const [open, setOpen] = useState(false);
  const { routes, isLoading } = useKnownRoutes();

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" role="combobox" aria-expanded={open} className="w-[220px] justify-between font-normal">
          <span className="flex items-center gap-2 truncate">
            <RouteIcon className="size-4 text-muted-foreground" data-icon="inline-start" />
            {value ? <span className="route-chip">{value}</span> : <span className="text-muted-foreground">All project routes</span>}
          </span>
          <ChevronsUpDown className="size-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[220px] p-0" align="start">
        <Command>
          <CommandInput placeholder={isLoading ? "Loading routes…" : "Search route…"} />
          <CommandList>
            <CommandEmpty>No route found.</CommandEmpty>
            <CommandGroup>
              <CommandItem
                value="__all__"
                onSelect={() => {
                  onChange(null);
                  setOpen(false);
                }}
              >
                <Check className={cn("size-4", value === null ? "opacity-100" : "opacity-0")} />
                All project routes
              </CommandItem>
            </CommandGroup>
            <CommandGroup heading="Routes observed in the data">
              {routes.map((route) => (
                <CommandItem
                  key={route}
                  value={route}
                  onSelect={() => {
                    onChange(route);
                    setOpen(false);
                  }}
                >
                  <Check className={cn("size-4", value === route ? "opacity-100" : "opacity-0")} />
                  {route}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
