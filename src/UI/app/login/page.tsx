import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { LoginForm } from "@/components/auth/login-form";
import { AUTH_COOKIE, isValidSession } from "@/lib/auth";

export default async function LoginPage() {
  const session = (await cookies()).get(AUTH_COOKIE)?.value;
  if (isValidSession(session)) {
    redirect("/overview");
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[var(--background)] p-4">
      <LoginForm />
    </main>
  );
}
