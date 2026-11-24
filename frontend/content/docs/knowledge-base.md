---
title: Knowledge base
description: Write articles that visitors can read and the AI answers from.
seo_title: Build an AI knowledge base
seo_description: Write help articles that visitors read in the chat widget and the AI agent answers from. How to structure them so the right part is found.
---

Articles do two jobs: visitors read them in the widget's **Help** tab, and the AI searches them before it answers.

## Write an article

1. Open **Knowledge base** and add an article.
2. Give it the title a customer would search for, like "How long does shipping take?".
3. Write the body, and save it as published. Drafts are not shown, and the AI doesn't read them.

## Write so that the AI finds it

Articles are split into passages at their headings, and the AI gets the passages that fit the question.

- **One topic per article,** with a heading for each part.
- **Use the words your customers use.** Search matches words, so mention other names for the same thing.
- **Each part should make sense alone.** "It takes 5 days" is lost without its heading; "Shipping to Canada takes 5 days" is not.
- **Write out exceptions and numbers.** The AI doesn't fill gaps.
- **Describe images.** The AI reads the description, not the picture.

## Images

Images in articles are kept in your own storage, so connect a bucket under **Settings › Storage** first. Without one, articles are text. Cloudflare R2, AWS S3 and others that work like S3 fit.

> [!WARNING]
> Files in that bucket can be opened by anyone who has the link. Don't put private documents in it.
