import { publicMetadata } from "@/lib/seo";

export const generateMetadata = () =>
  publicMetadata({
    title: "Log in or sign up",
    description: "Log in to your whileisleep inbox, or make an account and add an AI agent that answers your website's visitors from your own data.",
    path: "/login",
  });

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return children;
}
