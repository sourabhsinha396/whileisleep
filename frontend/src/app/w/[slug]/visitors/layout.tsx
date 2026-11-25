/** Other people's conversations and details: kept out of session replays. */
export default function PrivateLayout({ children }: { children: React.ReactNode }) {
  return <div className="ph-no-capture h-full">{children}</div>;
}
