/** Files in chat messages: what the server accepts (backend/apps/conversations/attachments.py),
 * to say no before uploading. Shared by the inbox and the widget. */

export interface ChatFile {
  id: number;
  name: string;
  url: string;
  content_type: string;
  size: number;
  /** Pictures only. */
  width: number | null;
  height: number | null;
}

const IMAGES = ["png", "jpg", "jpeg", "webp"];
const DOCUMENTS = ["pdf", "txt", "log", "csv", "doc", "docx", "xls", "xlsx"];
export const ACCEPT = [...IMAGES, ...DOCUMENTS].map((extension) => `.${extension}`).join(",");
export const MAX_FILE_BYTES = 10 * 1024 * 1024;
export const MAX_FILES = 5;

/** Why this file can't be sent, or "". */
export function fileProblem(file: { name: string; size: number }): string {
  const extension = /\.([^.]+)$/.exec(file.name)?.[1].toLowerCase() ?? "";
  if (![...IMAGES, ...DOCUMENTS].includes(extension)) return "Send a picture, a PDF, a text file, or a Word or Excel file.";
  if (file.size > MAX_FILE_BYTES) return "That file is too big. The limit is 10 MB.";
  if (!file.size) return "That file is empty.";
  return "";
}

export function isPicture(file: Pick<ChatFile, "content_type" | "width" | "height">): boolean {
  return file.content_type.startsWith("image/") && !!file.width && !!file.height;
}

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** The size to show a picture at, so its space is there before it loads. Never bigger than it is. */
export function fitted(width: number, height: number, maxWidth: number, maxHeight: number) {
  const scale = Math.min(1, maxWidth / width, maxHeight / height);
  return { width: Math.round(width * scale), height: Math.round(height * scale) };
}
