import { formatBeijingDateTime } from "@/lib/beijing-time";

export function DateTime({ value }: { value: string | Date }) {
  return <time>{formatBeijingDateTime(value)}</time>;
}
