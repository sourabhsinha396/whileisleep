import { Home } from "@/components/landing/home";
import { SiteFooter } from "@/components/site-footer";
import { StructuredData } from "@/components/structured-data";
import { siteOrigin } from "@/lib/origin";
import { publicMetadata, softwareData } from "@/lib/seo";

const DESCRIPTION =
  "Open-source customer chat. The AI agent answers from your articles, APIs and MCP servers, and wakes you only for chats that need a human.";

export const generateMetadata = () =>
  publicMetadata({ title: "whileisleep: open-source AI customer support chat", absoluteTitle: true, description: DESCRIPTION, path: "/" });

export default async function HomePage() {
  return (
    <>
      <StructuredData data={softwareData(DESCRIPTION, await siteOrigin())} />
      <Home footer={<SiteFooter />} />
    </>
  );
}
