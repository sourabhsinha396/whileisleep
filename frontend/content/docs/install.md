---
title: Install the chat
description: Put the widget on your site with one line of code.
seo_title: Add AI chat to your website
seo_description: Add the whileisleep chat widget to any website with one script tag. Steps for HTML, WordPress, Shopify, Google Tag Manager and Next.js.
---

## Add the script

1. Open **Settings › Install** and copy your snippet. It has your workspace's key in it.
2. Paste it before `</body>` on every page of your site.
3. Open your site. The chat button is in the corner.

It looks like this:

```html
<script src="https://YOUR_DOMAIN/widget.js" data-workspace="ws_YOUR_KEY" async></script>
```

> [!NOTE]
> The key in the snippet is public. It only says which workspace the chat belongs to.

## Where to paste it

| Your site | Where |
|---|---|
| Plain HTML | Before `</body>` in each page or the shared template |
| WordPress | A plugin that adds code to the footer |
| Shopify | `theme.liquid`, before `</body>` |
| Google Tag Manager | A **Custom HTML** tag on all pages |
| Next.js | The layout, as below |

```js
import Script from "next/script";

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        {children}
        <Script src="https://YOUR_DOMAIN/widget.js" data-workspace="ws_YOUR_KEY" />
      </body>
    </html>
  );
}
```

## Make it yours

**Settings › Appearance** has the color, the logo, the header pattern, the greeting, and light or dark mode.

## If it doesn't show

- Check that `data-workspace` is there and complete.
- If your site has a Content Security Policy, allow your whileisleep domain in `script-src` and `connect-src`.
- Look for a blocked `widget.js` in the browser's developer tools, under **Network**.

## Next

Tell the chat who your signed-in users are, or open it from your own button: see [Widget in code](widget-api.md).
