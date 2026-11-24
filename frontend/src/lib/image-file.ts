/** What the server accepts (backend/whileisleep/images.py), to say no before uploading. */
export const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp"];
export const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

/** Why this file can't be uploaded, or "". */
export function imageProblem(file: { type: string; size: number }): string {
  if (!IMAGE_TYPES.includes(file.type)) return "Use a PNG, JPEG or WebP image.";
  if (file.size > MAX_IMAGE_BYTES) return "That image is too big. The limit is 5 MB.";
  return "";
}

/** A description to start from: "reset-password_2.png" -> "reset password 2". Screenshots are
 * all called something like image.png, which describes nothing. */
export function altFromName(name: string): string {
  const words = name.replace(/\.[^.]*$/, "").replace(/[-_[\]]+/g, " ").trim();
  return /^(image|img|screenshot|untitled|pasted)?[\s\d().:]*$/i.test(words) ? "" : words;
}
