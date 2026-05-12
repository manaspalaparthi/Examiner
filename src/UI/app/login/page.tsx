import { redirect } from "next/navigation";
import { LoginForm } from "@/components/auth/login-form";
import { getUser } from "@/lib/supabase/server";

export default async function LoginPage() {
  const user = await getUser();
  if (user) {
    redirect("/overview");
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[var(--background)] p-4">
      <LoginForm />
    </main>
  );
}
