import Link from "next/link";
import { Logo } from "@/components/ui";

/** A short form on a page of its own, beside the log-in page. */
export function AuthCard({ title, text, children }: { title: string; text: string; children?: React.ReactNode }) {
  return (
    <main className="grid min-h-screen place-items-center bg-muted p-6">
      <div className="w-full max-w-sm space-y-5 rounded-lg border bg-surface p-8 shadow-sm">
        <Logo />
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
          <p className="mt-2 text-sm text-muted-foreground">{text}</p>
        </div>
        {children}
        <p className="text-center text-sm">
          <Link href="/login" className="font-semibold text-primary-text hover:underline">
            Back to log in
          </Link>
        </p>
      </div>
    </main>
  );
}
