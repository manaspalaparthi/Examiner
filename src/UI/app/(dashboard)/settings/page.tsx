import { Copy, KeyRound } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { MOCK_USER } from "@/components/layout/user-profile";

export default function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" description="Manage your account, workspace, and API keys." />

      <Tabs defaultValue="profile">
        <TabsList>
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="workspace">Workspace</TabsTrigger>
          <TabsTrigger value="api">API Keys</TabsTrigger>
          <TabsTrigger value="billing">Billing</TabsTrigger>
        </TabsList>

        <TabsContent value="profile">
          <Card>
            <CardHeader>
              <CardTitle>Profile</CardTitle>
              <CardDescription>Update your personal details.</CardDescription>
            </CardHeader>
            <CardContent className="grid max-w-xl gap-4">
              <div className="grid gap-2">
                <Label htmlFor="full-name">Full name</Label>
                <Input id="full-name" defaultValue={MOCK_USER.name} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" defaultValue={MOCK_USER.email} />
              </div>
              <div className="flex items-center justify-between rounded-lg border border-[var(--border)] p-3">
                <div>
                  <Label>Two-factor authentication</Label>
                  <p className="text-xs text-[var(--muted-foreground)]">Use an authenticator app for extra security.</p>
                </div>
                <Switch />
              </div>
              <div className="flex justify-end">
                <Button>Save changes</Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="workspace">
          <Card>
            <CardHeader>
              <CardTitle>Workspace</CardTitle>
              <CardDescription>Settings shared with your team.</CardDescription>
            </CardHeader>
            <CardContent className="grid max-w-xl gap-4">
              <div className="grid gap-2">
                <Label htmlFor="workspace-name">Workspace name</Label>
                <Input id="workspace-name" defaultValue={MOCK_USER.workspace} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="workspace-slug">Slug</Label>
                <Input id="workspace-slug" defaultValue="acme-voice" />
              </div>
              <div className="flex justify-end">
                <Button>Save changes</Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="api">
          <Card>
            <CardHeader className="flex flex-row items-start justify-between">
              <div>
                <CardTitle>API Keys</CardTitle>
                <CardDescription>Use these keys to call the Voice AI API from your services.</CardDescription>
              </div>
              <Button>
                <KeyRound /> Generate key
              </Button>
            </CardHeader>
            <CardContent className="px-0 pb-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="pl-6">Name</TableHead>
                    <TableHead>Key</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead className="pr-6 text-right">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[
                    { name: "Production", key: "vai_live_••••••••••8a1c", created: "Mar 4, 2026", active: true },
                    { name: "Staging", key: "vai_test_••••••••••44ee", created: "Feb 18, 2026", active: true },
                  ].map((k) => (
                    <TableRow key={k.key}>
                      <TableCell className="pl-6 font-medium">{k.name}</TableCell>
                      <TableCell>
                        <span className="inline-flex items-center gap-2 font-mono text-xs">
                          {k.key}
                          <button className="text-[var(--muted-foreground)] hover:text-[var(--foreground)]" aria-label="Copy key">
                            <Copy className="size-3.5" />
                          </button>
                        </span>
                      </TableCell>
                      <TableCell className="text-sm text-[var(--muted-foreground)]">{k.created}</TableCell>
                      <TableCell className="pr-6 text-right">
                        <Badge variant={k.active ? "success" : "muted"}>{k.active ? "Active" : "Revoked"}</Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="billing">
          <Card>
            <CardHeader>
              <CardTitle>Billing</CardTitle>
              <CardDescription>You&apos;re on the Starter plan.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4">
              <div className="rounded-lg border border-[var(--border)] p-4">
                <div className="text-sm text-[var(--muted-foreground)]">Usage this cycle</div>
                <div className="mt-1 text-2xl font-semibold tabular-nums">1,284 / 5,000 calls</div>
                <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-[var(--muted)]">
                  <div className="h-full bg-[var(--primary)]" style={{ width: "25%" }} />
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button>Upgrade plan</Button>
                <Button variant="outline">Update payment method</Button>
                <Button variant="ghost">View invoices</Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </>
  );
}
