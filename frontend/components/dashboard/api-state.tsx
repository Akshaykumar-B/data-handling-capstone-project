"use client";

import { AlertTriangle, PlugZap } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { isApiConfigured, type ApiError } from "@/lib/api-client";

type ApiStateProps = {
  isLoading: boolean;
  error: unknown;
  isEmpty?: boolean;
  emptyLabel?: string;
  children: React.ReactNode;
  skeletonHeight?: string;
};

/**
 * Shared loading / not-configured / error / empty gate for any page section
 * backed by a react-query call. Never fabricates data when the API can't be
 * reached &mdash; it always shows the real state instead.
 */
export function ApiState({ isLoading, error, isEmpty, emptyLabel, children, skeletonHeight = "h-64" }: ApiStateProps) {
  if (!isApiConfigured()) {
    return (
      <Empty className="border">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <PlugZap />
          </EmptyMedia>
          <EmptyTitle>API not configured</EmptyTitle>
          <EmptyDescription>
            Set <code className="font-mono text-xs">NEXT_PUBLIC_API_BASE_URL</code> to your deployed FastAPI backend to load real
            dashboard data. Nothing is fabricated in its place.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  if (isLoading) {
    return <Skeleton className={`w-full ${skeletonHeight}`} />;
  }

  if (error) {
    const message = (error as ApiError)?.message ?? "The API request failed.";
    return (
      <Empty className="border border-destructive/30">
        <EmptyHeader>
          <EmptyMedia variant="icon" className="bg-destructive/10 text-destructive">
            <AlertTriangle />
          </EmptyMedia>
          <EmptyTitle>API unavailable</EmptyTitle>
          <EmptyDescription>{message}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  if (isEmpty) {
    return (
      <Empty className="border">
        <EmptyHeader>
          <EmptyTitle>No records</EmptyTitle>
          <EmptyDescription>{emptyLabel ?? "The API returned no rows for this selection."}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return <>{children}</>;
}
