import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

import { beijingDateKey } from "./beijing-time";

export function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)); }

export function localDateKey(value: Date) {
  return beijingDateKey(value);
}
