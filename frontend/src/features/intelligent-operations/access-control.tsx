import type { ReactNode } from "react";
import { Link } from "react-router";

import type { OperationsContext } from "./api";

export function hasOperationsCapability(context: OperationsContext, capability: string): boolean {
  return context.capabilities.includes(capability);
}

export function OperationsCapabilityBoundary({
  context,
  capability,
  children,
}: {
  context: OperationsContext;
  capability: string;
  children: ReactNode;
}) {
  return hasOperationsCapability(context, capability) ? children : null;
}

export function OperationsNavigation({ context }: { context: OperationsContext }) {
  const items = [
    { label: "运营案件", path: "/operations", capability: "operations.case.read" },
    { label: "经营报告", path: "/reports", capability: "operations.report.read" },
    {
      label: "权限与模型设置",
      path: "/operations/settings",
      capability: "operations.model.manage",
    },
  ];
  return (
    <nav aria-label="智能运营">
      {items
        .filter((item) => hasOperationsCapability(context, item.capability))
        .map((item) => (
          <Link key={item.path} to={item.path}>
            {item.label}
          </Link>
        ))}
    </nav>
  );
}

export function DeterministicContent({
  modelEnabled,
  narrativeState,
  narrative,
  children,
}: {
  modelEnabled: boolean;
  narrativeState: "not_requested" | "queued" | "available" | "unavailable" | "failed";
  narrative: ReactNode | null;
  children: ReactNode;
}) {
  return (
    <>
      {children}
      {modelEnabled && narrativeState === "available" ? narrative : null}
      {!modelEnabled || narrativeState === "unavailable" || narrativeState === "failed" ? (
        <p role="status">智能总结暂不可用</p>
      ) : null}
    </>
  );
}
