import type { Metadata } from "next";
import { SettingsView } from "@/components/app/settings/settings-view";
import { PageHeader } from "@/components/app/ui";
import { verifySession } from "@/lib/dal";

export const metadata: Metadata = { title: "Settings" };

export default async function SettingsPage() {
  const me = await verifySession();
  return (
    <div className="mx-auto w-full max-w-6xl">
      <PageHeader eyebrow={me.workspace.name} title="Settings" lead="Review threshold, default markup, team and your password." />
      <SettingsView />
    </div>
  );
}
