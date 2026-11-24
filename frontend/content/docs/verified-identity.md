---
title: Verified identity
description: Prove who a signed-in visitor is, so the agent can look up their own data.
---

A web page can claim anything. So a tool that returns personal data only trusts details your **server** has signed.

## How it works

1. A user is signed in on your site.
2. Your server signs a short token that says who they are, with your workspace's secret.
3. The page gives the token to the widget.
4. The agent's [tools](tools.md) can now use `{visitor.external_id}` and `{visitor.email}`.

## Get the secret

Open **Settings › Verified identity** and press **Show the secret**. Only workspace owners can. Keep it on your server as an environment variable.

> [!WARNING]
> Never put the secret in a page or an app. Whoever has it can pose as any of your users. If it leaks, press **Replace the secret**: tokens signed with the old one stop working at once.

## Sign a token

It is a JWT signed with HS256. Install `jsonwebtoken` for Node.js, `pyjwt` for Python or `firebase/php-jwt` for PHP.

```js
import jwt from "jsonwebtoken";

export function chatToken(user) {
  return jwt.sign(
    { email: user.email, name: user.name, plan: user.plan },
    process.env.WHILEISLEEP_IDENTITY_SECRET,
    { algorithm: "HS256", subject: String(user.id), expiresIn: "1h" },
  );
}
```

```python
import os
import time

import jwt


def chat_token(user):
    return jwt.encode(
        {
            "sub": str(user.id),
            "exp": int(time.time()) + 3600,
            "email": user.email,
            "name": user.name,
            "plan": user.plan,
        },
        os.environ["WHILEISLEEP_IDENTITY_SECRET"],
        algorithm="HS256",
    )
```

```php
<?php
use Firebase\JWT\JWT;

function chatToken($user): string
{
    return JWT::encode([
        'sub' => (string) $user->id,
        'exp' => time() + 3600,
        'email' => $user->email,
        'name' => $user->name,
        'plan' => $user->plan,
    ], getenv('WHILEISLEEP_IDENTITY_SECRET'), 'HS256');
}
```

| Claim | Meaning |
|---|---|
| `sub` | Required. Your user's id, as text. They keep their conversations on every device. |
| `exp` | Required. When the token ends. An hour is plenty. |
| anything else | Becomes a verified attribute: `email`, `name`, `plan` and so on |

## Pass it to the widget

Print the token into the page for signed-in users only, and sign a new one on each page load:

```js
function signIn() {
  window.whileisleep.identify({ token: "THE_TOKEN_FROM_YOUR_SERVER" });
}

if (window.whileisleep) signIn();
else window.addEventListener("whileisleep:ready", signIn, { once: true });
```

When your user signs out, call `window.whileisleep.reset()`.

## If it isn't accepted

| Message | Fix |
|---|---|
| The identity token has expired | Sign one per page load, and check your server's clock |
| The identity token isn't valid for this workspace | Check that the secret belongs to this workspace, and that the algorithm is HS256 |
| The identity token needs a `sub` claim | Send your user's id as text, not as a number |
